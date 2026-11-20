"""Personal development prototype: Samsung Health Data SDK to Home Assistant.

Uses only authenticated POST requests. Stores raw SDK records with provenance in
/config/samsung_health_bridge/records.sqlite3. Does not alter existing HA dashboards.
"""
from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo
import hashlib
from contextlib import closing, contextmanager
import json
import logging
from pathlib import Path
import sqlite3
from typing import Any

from aiohttp import web
from homeassistant.components.http import HomeAssistantView, require_admin
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.const import Platform
from homeassistant.helpers.dispatcher import async_dispatcher_send

DOMAIN = "samsung_health_bridge"
LOGGER = logging.getLogger(__name__)
MAX_BODY = 512_000
REGISTERED_MODE_KEY = f"{DOMAIN}_registered_mode"
ENTITY_VALUES_KEY = f"{DOMAIN}_entity_values"
UPDATE_SIGNAL = f"{DOMAIN}_entity_values_updated"
# HTTP views remain registered until HA restarts; disable their handlers on UI unload.
RECEIVER_ACTIVE_KEY = f"{DOMAIN}_receiver_active"
PLATFORMS = [Platform.SENSOR]
ALLOWED = {
    "heart_rate", "blood_oxygen", "blood_pressure", "blood_glucose",
    "body_composition", "body_temperature", "skin_temperature", "exercise",
    "floors_climbed", "sleep", "nutrition", "water_intake", "energy_score",
    "irregular_heart_rhythm_notification", "sleep_apnea",
}


# Samsung SDK v1.1.0 aggregate-only results (including other SDK aggregates).
# Record types use synthetic stable IDs for (aggregation, local calendar day).
AGGREGATE_NAMES = {
    "STEPS_TOTAL",
    "STEPS_GOAL_LAST",
    "ACTIVITY_SUMMARY_TOTAL_ACTIVE_CALORIES_BURNED",
    "ACTIVITY_SUMMARY_TOTAL_ACTIVE_TIME",
    "ACTIVITY_SUMMARY_TOTAL_CALORIES_BURNED",
    "ACTIVITY_SUMMARY_TOTAL_DISTANCE",
    "ACTIVE_CALORIES_BURNED_GOAL_LAST",
    "ACTIVE_TIME_GOAL_LAST",
    "EXERCISE_TOTAL_CALORIES",
    "EXERCISE_TOTAL_DURATION",
    "FLOORS_CLIMBED_TOTAL",
    "HEART_RATE_MAX",
    "HEART_RATE_MIN",
    "NUTRITION_TOTAL_CALORIES",
    "NUTRITION_GOAL_LAST_CALORIES",
    "SLEEP_TOTAL_DURATION",
    "SLEEP_GOAL_LAST_BED_TIME",
    "SLEEP_GOAL_LAST_WAKE_UP_TIME",
    "WATER_INTAKE_TOTAL",
    "WATER_INTAKE_GOAL_LAST",
}
AGGREGATE_KEYS = {"aggregate_" + a.lower() for a in AGGREGATE_NAMES}
ALLOWED |= AGGREGATE_KEYS | {"user_profile"}

class BridgeStorage:
    """Current source records plus an append-only change history.

    `records` retains the v0.3.3 schema, keys and query behavior so current
    dashboards continue working. `record_events` preserves each distinct
    received version and deletion. No rows are automatically purged.
    """
    def __init__(self, path: Path) -> None:
        self.path = path

    def _connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path, timeout=10)
        connection.execute("PRAGMA busy_timeout=10000")
        connection.execute("""CREATE TABLE IF NOT EXISTS records (
            record_type TEXT NOT NULL, uid TEXT NOT NULL,
            sample_ts INTEGER NOT NULL, end_ts INTEGER,
            source_app TEXT, source_device TEXT,
            data_json TEXT NOT NULL, deleted INTEGER NOT NULL DEFAULT 0,
            received_at TEXT NOT NULL,
            PRIMARY KEY (record_type, uid)
        )""")
        connection.execute("CREATE INDEX IF NOT EXISTS by_time ON records (record_type, sample_ts)")
        return connection

    @contextmanager
    def connection(self):
        with closing(self._connect()) as conn:
            with conn:
                yield conn

    @staticmethod
    def _fingerprint(raw: str | None) -> str | None:
        if raw is None:
            return None
        # Ignore JSON object key order and whitespace for replay/deduplication.
        canonical = json.dumps(json.loads(raw), sort_keys=True, ensure_ascii=False,
                               separators=(",", ":"), allow_nan=False)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    @staticmethod
    def _log_event(conn: sqlite3.Connection, kind: str, uid: str, event: str,
                   ts: int | None, end: int | None, app: str | None,
                   device: str | None, raw: str | None, deleted: int,
                   observed: str) -> None:
        conn.execute("""INSERT INTO record_events
            (record_type, uid, event_kind, sample_ts, end_ts, source_app,
             source_device, data_json, content_sha256, deleted, observed_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (kind, uid, event, ts, end, app, device, raw,
             BridgeStorage._fingerprint(raw), deleted, observed))

    def initialize(self) -> None:
        with self.connection() as conn:
            conn.execute("""CREATE TABLE IF NOT EXISTS record_events (
                event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                record_type TEXT NOT NULL,
                uid TEXT NOT NULL,
                event_kind TEXT NOT NULL,
                sample_ts INTEGER,
                end_ts INTEGER,
                source_app TEXT,
                source_device TEXT,
                data_json TEXT,
                content_sha256 TEXT,
                deleted INTEGER NOT NULL,
                observed_at TEXT NOT NULL
            )""")
            conn.execute("""CREATE INDEX IF NOT EXISTS events_by_source
                ON record_events (record_type, uid, event_id)""")
            conn.execute("""CREATE TABLE IF NOT EXISTS archive_meta (
                key TEXT PRIMARY KEY, value TEXT NOT NULL
            )""")
            # Guard against accidental changes to the append-only audit log.
            conn.execute("""CREATE TRIGGER IF NOT EXISTS record_events_no_update
                BEFORE UPDATE ON record_events BEGIN
                SELECT RAISE(ABORT, 'record_events history is immutable'); END""")
            conn.execute("""CREATE TRIGGER IF NOT EXISTS record_events_no_delete
                BEFORE DELETE ON record_events BEGIN
                SELECT RAISE(ABORT, 'record_events history is immutable'); END""")
            done = conn.execute("SELECT value FROM archive_meta WHERE key='baseline_complete'").fetchone()
            if done is None:
                # Atomic, one-time baseline of EVERYTHING already present,
                # including records previously marked deleted. Older revisions
                # already overwritten by prior receiver versions cannot be recovered.
                existing = conn.execute("""SELECT record_type,uid,sample_ts,end_ts,
                    source_app,source_device,data_json,deleted FROM records""")
                observed = datetime.now(timezone.utc).isoformat()
                for kind, uid, ts, end, app, device, raw, deleted in existing:
                    self._log_event(conn, kind, uid, "BASELINE", ts, end, app,
                                    device, raw, int(deleted), observed)
                conn.execute("INSERT INTO archive_meta(key,value) VALUES ('baseline_complete',?)",
                             (observed,))

    def put_batch(self, kind: str, samples: list[dict], deleted: list[str]) -> dict:
        # Also initialize in direct/local test usage; migration is idempotent.
        self.initialize()
        now = datetime.now(timezone.utc).isoformat()
        count, changes, deletion_changes = 0, 0, 0
        with self.connection() as conn:
            for entry in samples:
                uid = entry.get("uid")
                if not isinstance(uid, str) or not 1 <= len(uid) <= 200:
                    raise ValueError("Each record must include a Samsung source uid")
                timestamp = entry.get("startTimestamp")
                if not isinstance(timestamp, int) or isinstance(timestamp, bool) or timestamp < 946684800000 or timestamp > 4102444800000:
                    raise ValueError("Invalid epoch-millisecond source timestamp")
                source = entry.get("dataSource") or {}
                if not isinstance(source, dict):
                    source = {}
                raw = json.dumps(entry, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
                if len(raw) > 200_000:
                    raise ValueError("Individual record too large")
                end = entry.get("endTimestamp")
                end = end if isinstance(end, int) and not isinstance(end, bool) else None
                app, device = source.get("appId"), source.get("deviceId")
                old = conn.execute("""SELECT sample_ts,end_ts,source_app,source_device,
                    data_json,deleted FROM records WHERE record_type=? AND uid=?""",
                    (kind, uid)).fetchone()
                changed = (old is None or old[5] != 0 or old[:4] != (timestamp, end, app, device)
                           or self._fingerprint(old[4]) != self._fingerprint(raw))
                if changed:
                    conn.execute("""INSERT INTO records (
                        record_type,uid,sample_ts,end_ts,source_app,source_device,data_json,deleted,received_at
                    ) VALUES (?,?,?,?,?,?,?,0,?)
                    ON CONFLICT(record_type,uid) DO UPDATE SET
                        sample_ts=excluded.sample_ts, end_ts=excluded.end_ts,
                        source_app=excluded.source_app,source_device=excluded.source_device,
                        data_json=excluded.data_json,deleted=0,received_at=excluded.received_at""",
                        (kind, uid, timestamp, end, app, device, raw, now))
                    event = "INSERT" if old is None else ("RESTORE" if old[5] else "UPDATE")
                    self._log_event(conn, kind, uid, event, timestamp, end, app,
                                    device, raw, 0, now)
                    changes += 1
                count += 1
            for uid in deleted:
                if not isinstance(uid, str) or not 1 <= len(uid) <= 200:
                    raise ValueError("Invalid deleted uid")
                old = conn.execute("""SELECT sample_ts,end_ts,source_app,source_device,
                    data_json,deleted FROM records WHERE record_type=? AND uid=?""",
                    (kind, uid)).fetchone()
                if old is not None and old[5] == 0:
                    conn.execute("UPDATE records SET deleted=1, received_at=? WHERE record_type=? AND uid=?",
                                 (now, kind, uid))
                    self._log_event(conn, kind, uid, "DELETE", old[0], old[1],
                                    old[2], old[3], old[4], 1, now)
                    deletion_changes += 1
                elif old is None:
                    # Record unseen deletion once rather than on every poll.
                    unseen = conn.execute("""SELECT 1 FROM record_events
                        WHERE record_type=? AND uid=? AND event_kind='DELETE_UNSEEN' LIMIT 1""",
                        (kind, uid)).fetchone()
                    if unseen is None:
                        self._log_event(conn, kind, uid, "DELETE_UNSEEN", None,
                                        None, None, None, None, 1, now)
                        deletion_changes += 1
        return {"accepted": count, "deletions_seen": len(deleted)}

    def statistics(self) -> dict[str, Any]:
        with self.connection() as conn:
            counts = dict(conn.execute("SELECT record_type,COUNT(*) FROM records WHERE deleted=0 GROUP BY record_type"))
            summaries = {}
            for kind in ALLOWED:
                watch_only = " AND source_app='com.samsung.android.shealthmonitor'" if kind == "blood_pressure" else ""
                row = conn.execute(
                    "SELECT data_json,source_app FROM records WHERE deleted=0 AND record_type=?" + watch_only +
                    " ORDER BY COALESCE(end_ts,sample_ts) DESC LIMIT 1", (kind,)).fetchone()
                if row:
                    summaries[kind] = (json.loads(row[0]), row[1])
            return {"counts": counts, "latest": summaries}


def _source_attributes(entry: dict, app: str | None) -> dict:
    ts = entry.get("startTimestamp")
    end = entry.get("endTimestamp")
    return {
        "source_app": app, "samsung_uid": entry.get("uid"),
        "measured_at": datetime.fromtimestamp(ts / 1000, timezone.utc).isoformat() if isinstance(ts, int) else None,
        "ended_at": datetime.fromtimestamp(end / 1000, timezone.utc).isoformat() if isinstance(end, int) else None,
        "source_device_id": (entry.get("dataSource") or {}).get("deviceId"),
        "test_build": True,
    }


def refresh_states(hass: HomeAssistant, snapshot: dict) -> None:
    """Temporary proof sensors, restored from database at HA startup.

    They are intentionally not entity-registry-backed; a later ConfigEntry sensor
    platform is required before treating this as a production HA integration.
    """
    counts = snapshot["counts"]
    for kind in sorted(ALLOWED):
        hass.states.async_set(f"sensor.samsung_bridge_{kind}_record_count", counts.get(kind, 0),
                              {"friendly_name": f"Samsung Bridge {kind.replace('_',' ').title()} Records", "test_build": True})
    latest = snapshot["latest"]
    # Preserve the complete aggregate result in SQLite; these are convenient
    # *latest bucket* sensors, not a reconstructed per-day HA statistics series.
    # Original bucket timestamps are attached so users can distinguish older data.
    for kind in sorted(AGGREGATE_KEYS):
        if kind not in latest:
            continue
        entry, app = latest[kind]
        values = entry.get("harmonized") or {}
        value = values.get("value")
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            continue
        attrs = _source_attributes(entry, app)
        attrs["bucket_end"] = attrs.get("ended_at")
        attrs["aggregation"] = values.get("aggregation")
        unit = values.get("unit")
        if unit:
            attrs["unit_of_measurement"] = unit
        hass.states.async_set(
            f"sensor.samsung_bridge_{kind}_latest",
            round(float(value), 3),
            {"friendly_name": "Samsung " + kind.replace("aggregate_", "").replace("_", " ").title()
             + " (Latest Day)", **attrs},
        )
    if "blood_pressure" in latest:
        point, app = latest["blood_pressure"]
        vals = point.get("harmonized") or {}
        attrs = _source_attributes(point, app)
        for key, suffix, unit in [("systolic", "systolic", "mmHg"),
                                   ("diastolic", "diastolic", "mmHg"),
                                   ("pulseRate", "pulse", "bpm")]:
            value = vals.get(key)
            if value is not None:
                hass.states.async_set(f"sensor.samsung_bridge_watch_bp_{suffix}", value,
                                      {"friendly_name": f"Watch BP {suffix.title()}",
                                       "unit_of_measurement": unit, **attrs})
    if "energy_score" in latest:
        point, app = latest["energy_score"]
        value = (point.get("harmonized") or {}).get("score")
        if value is not None:
            hass.states.async_set("sensor.samsung_bridge_energy_score", round(float(value), 1),
                                  {"friendly_name": "Samsung Energy Score",
                                   **_source_attributes(point, app)})
    if "sleep" in latest:
        point, app = latest["sleep"]
        values = point.get("harmonized") or {}
        attrs = _source_attributes(point, app)
        score = values.get("sleepScore")
        if score is not None:
            hass.states.async_set("sensor.samsung_bridge_sleep_score", score,
                                  {"friendly_name": "Samsung Last Sleep Session Score", **attrs})
        duration = values.get("durationMillis")
        if isinstance(duration, int):
            hass.states.async_set("sensor.samsung_bridge_sleep_duration", round(duration / 60000),
                                  {"friendly_name": "Samsung Last Sleep Session Duration",
                                   "unit_of_measurement": "min", **attrs})



# ---- v0.3.3 additive dashboard projection (does not alter the record store) ----
# The receiver persists the complete Samsung payload; these projections merely
# make already-imported values available to Lovelace. They are intentionally
# proof entities, not yet ConfigEntry/EntityRegistry-backed sensors.
import math
from datetime import timedelta

# These units/field names are defined by the MIT SamsungHealthReporter models.
# A missing/null field is never fabricated. Weight is kg; temperatures are °C.
BRIDGE_EXTRAS = {
    "blood_oxygen": {
        "oxygen_saturation": ("oxygenSaturation", "%"),
        "oxygen_min": ("min", "%"),
        "oxygen_max": ("max", "%"),
    },
    "skin_temperature": {
        "skin_temperature": ("skinTemperature", "°C"),
        "skin_temperature_min": ("min", "°C"),
        "skin_temperature_max": ("max", "°C"),
    },
    "heart_rate": {
        "heart_rate": ("heartRate", "bpm"),
        "heart_rate_min": ("min", "bpm"),
        "heart_rate_max": ("max", "bpm"),
    },
    "body_composition": {
        "body_weight": ("weight", "kg"),
        "body_height": ("height", "cm"),
        "body_fat": ("bodyFat", "%"),
        "body_fat_mass": ("bodyFatMass", "kg"),
        "body_bmi": ("bodyMassIndex", None),
        "body_muscle_mass_percent": ("muscleMass", "%"),
        "body_skeletal_muscle": ("skeletalMuscle", "%"),
        "body_skeletal_muscle_mass": ("skeletalMuscleMass", "kg"),
        "body_water": ("totalBodyWater", "L"),
        "body_bmr": ("basalMetabolicRate", "kcal/day"),
    },
    "nutrition": {
        "nutrition_calories": ("calories", "kcal"),
        "nutrition_carbohydrate": ("carbohydrate", "g"),
        "nutrition_protein": ("protein", "g"),
        "nutrition_fat": ("totalFat", "g"),
        "nutrition_fiber": ("dietaryFiber", "g"),
        "nutrition_sugar": ("sugar", "g"),
        "nutrition_sodium": ("sodium", "mg"),
    },
}

# Each timeline is independent, contains actual SDK timestamps (epoch ms),
# and is capped so HA state attributes remain far under its 16 KiB limit.
BRIDGE_HISTORIES = {
    "watch_bp_systolic": ("blood_pressure", "systolic"),
    "watch_bp_diastolic": ("blood_pressure", "diastolic"),
    "watch_bp_pulse": ("blood_pressure", "pulseRate"),
    "energy_score": ("energy_score", "score"),
    "sleep_score": ("sleep", "sleepScore"),
    "sleep_duration_minutes": ("sleep", "durationMillis"),
    "spo2": ("blood_oxygen", "oxygenSaturation"),
    "skin_temperature": ("skin_temperature", "skinTemperature"),
    "body_weight": ("body_composition", "weight"),
    "body_fat": ("body_composition", "bodyFat"),
    "heart_rate": ("heart_rate", "heartRate"),
    "steps": ("aggregate_steps_total", "value"),
    "active_calories": ("aggregate_activity_summary_total_active_calories_burned", "value"),
    "distance": ("aggregate_activity_summary_total_distance", "value"),
}


def bridge_sensor_suffixes() -> tuple[str, ...]:
    """Stable one-to-one catalog of legacy `sensor.samsung_bridge_*` IDs.

    Keep this derived from the v0.3 receiver mappings so old dashboards and
    unique IDs do not drift when new measurements are added.
    """
    names = {f"{kind}_record_count" for kind in ALLOWED}
    names |= {f"{kind}_latest" for kind in AGGREGATE_KEYS}
    names |= {"watch_bp_systolic", "watch_bp_diastolic", "watch_bp_pulse",
              "energy_score", "sleep_score", "sleep_duration", "last_received"}
    names |= {suffix for defs in BRIDGE_EXTRAS.values() for suffix in defs}
    names |= {f"history_{suffix}" for suffix in BRIDGE_HISTORIES}
    return tuple(sorted(names))


class _ProjectionStates:
    """Capture the exact legacy projected values without publishing raw states."""

    def __init__(self) -> None:
        self.values: dict[str, tuple[Any, dict[str, Any]]] = {}

    def async_set(self, entity_id: str, state: Any, attributes: dict | None = None) -> None:
        if not entity_id.startswith("sensor.samsung_bridge_"):
            raise ValueError(f"Unexpected bridge entity ID: {entity_id}")
        self.values[entity_id] = (state, dict(attributes or {}))


class _ProjectionHass:
    """Forward executor work but capture all sensor projection writes."""

    def __init__(self, hass: HomeAssistant) -> None:
        self._hass = hass
        self.states = _ProjectionStates()

    async def async_add_executor_job(self, method, *args):
        return await self._hass.async_add_executor_job(method, *args)


async def _refresh_registered_states(
    hass: HomeAssistant, storage: BridgeStorage, snapshot: dict,
    *, received: bool = False,
) -> None:
    """Publish legacy-equivalent values to registered SensorEntity instances."""
    projection = _ProjectionHass(hass)
    refresh_states(projection, snapshot)
    await _bridge_refresh_extended(projection, storage, snapshot)
    if received:
        projection.states.async_set(
            "sensor.samsung_bridge_last_received",
            datetime.now(timezone.utc).isoformat(),
            {"friendly_name": "Samsung Bridge Last Received", "test_build": True},
        )
    cache = hass.data.setdefault(ENTITY_VALUES_KEY, {})
    cache.update(projection.states.values)
    async_dispatcher_send(hass, UPDATE_SIGNAL)


def _bridge_number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        return None
    return round(float(value), 3)


def _bridge_extras_from_snapshot(hass: HomeAssistant, snapshot: dict) -> None:
    for kind, definitions in BRIDGE_EXTRAS.items():
        found = snapshot["latest"].get(kind)
        if not found:
            continue
        point, app = found
        fields = point.get("harmonized") or {}
        if not isinstance(fields, dict):
            continue
        attrs = _source_attributes(point, app)
        for suffix, (key, unit) in definitions.items():
            val = _bridge_number(fields.get(key))
            if val is None:
                continue
            attributes = {"friendly_name": "Samsung " + suffix.replace("_", " ").title(), **attrs}
            if unit:
                attributes["unit_of_measurement"] = unit
            hass.states.async_set(f"sensor.samsung_bridge_{suffix}", val, attributes)


def _bridge_history_snapshot(storage: BridgeStorage) -> dict:
    # Only historical time series needed by dashboards; does not change SQLite.
    horizon = int((datetime.now(timezone.utc) - timedelta(days=180)).timestamp() * 1000)
    kinds = {kind for kind, _ in BRIDGE_HISTORIES.values()}
    by_kind = {}
    with storage.connection() as conn:
        for kind in kinds:
            rows = conn.execute(
                "SELECT sample_ts,end_ts,source_app,data_json FROM records "
                "WHERE deleted=0 AND record_type=? AND sample_ts>=? "
                "ORDER BY sample_ts DESC LIMIT 150", (kind, horizon),
            ).fetchall()
            by_kind[kind] = rows

    out = {}
    for series_name, (kind, field) in BRIDGE_HISTORIES.items():
        pairs = []
        for start_ts, end_ts, app, raw in reversed(by_kind[kind]):
            if kind == "blood_pressure" and app != "com.samsung.android.shealthmonitor":
                continue  # Never combine manually entered BP with watch BP.
            try:
                d = json.loads(raw)
                val = _bridge_number((d.get("harmonized") or {}).get(field))
                ts = end_ts if kind == "sleep" and isinstance(end_ts, int) else start_ts
                if val is None or not isinstance(ts, int):
                    continue
                if series_name == "sleep_duration_minutes":
                    val = round(val / 60_000, 2)
                pairs.append([ts, val])
            except (ValueError, TypeError, AttributeError):
                continue
        # Limit to most recent 120 records and keep the original timestamps.
        out[series_name] = sorted(pairs[-120:], key=lambda pair: pair[0])
    return out


def _bridge_publish_history(hass: HomeAssistant, histories: dict) -> None:
    for name, points in histories.items():
        hass.states.async_set(
            "sensor.samsung_bridge_history_" + name,
            len(points),
            {
                "friendly_name": "Samsung Source History " + name.replace("_", " ").title(),
                "points": points,
                "source_timestamp_basis": "Samsung Health source measurement timestamp",
                "lookback_days": 180,
                "max_points": 120,
                "test_build": True,
            },
        )


async def _bridge_refresh_extended(hass: HomeAssistant, storage: BridgeStorage, snapshot: dict) -> None:
    _bridge_extras_from_snapshot(hass, snapshot)
    histories = await hass.async_add_executor_job(_bridge_history_snapshot, storage)
    _bridge_publish_history(hass, histories)
# ---- End v0.3.3 extension ----


# ---- v0.3.5: full-range, read-only history for the Lovelace explorer ----
# This is intentionally separate from the legacy 90-day/120-point attribute
# sensors so that existing dashboards remain unchanged and HA state attributes
# never grow with the long-term archive.
HISTORY_LABELS = {
    "watch_bp_systolic": ("Watch systolic BP", "mmHg"),
    "watch_bp_diastolic": ("Watch diastolic BP", "mmHg"),
    "watch_bp_pulse": ("Watch pulse", "bpm"),
    "energy_score": ("Energy Score", "score"),
    "sleep_score": ("Sleep Score", "score"),
    "sleep_duration_minutes": ("Sleep duration", "minutes"),
    "spo2": ("Blood oxygen", "%"),
    "skin_temperature": ("Skin temperature", "°C"),
    "body_weight": ("Body weight", "kg"),
    "body_fat": ("Body fat", "%"),
    "heart_rate": ("Heart rate", "bpm"),
    "steps": ("Steps", "steps"),
    "active_calories": ("Active calories", "SDK units"),
    "distance": ("Activity distance", "SDK units"),
}


def _bridge_full_history(storage: BridgeStorage, series: str,
                         start: int | None, end: int | None) -> dict:
    """Query every active, dated record in any requested window.

    Dense charts are visualized with first/last/min/max points per time bucket.
    All qualifying records are scanned; no 90-day or 120-row query limit exists.
    Audit events remain in record_events, but deleted or superseded readings
    are deliberately not plotted as if they were current measurements.
    """
    kind, field = BRIDGE_HISTORIES[series]  # Whitelist, never SQL from input.
    # Sleep timestamps are session-end based, just like the legacy charts.
    ts_expr = "COALESCE(end_ts,sample_ts)" if kind == "sleep" else "sample_ts"
    conditions = ["deleted=0", "record_type=?"]
    args: list[Any] = [kind]
    if kind == "blood_pressure":
        conditions.append("source_app=?")
        args.append("com.samsung.android.shealthmonitor")
    if start is not None:
        conditions.append(f"{ts_expr}>=?")
        args.append(start)
    if end is not None:
        conditions.append(f"{ts_expr}<=?")
        args.append(end)
    condition_sql = " AND ".join(conditions)
    with storage.connection() as conn:
        bounds = conn.execute(
            f"SELECT MIN({ts_expr}),MAX({ts_expr}) FROM records WHERE {condition_sql}",
            args,
        ).fetchone()
        low, high = bounds
        if low is None:
            return {"series": series, "label": HISTORY_LABELS[series][0],
                    "unit": HISTORY_LABELS[series][1], "count": 0,
                    "plotted": 0, "sampled": False, "first": None,
                    "last": None, "points": []}
        cursor = conn.execute(
            f"SELECT {ts_expr},data_json FROM records WHERE {condition_sql} "
            f"ORDER BY {ts_expr},uid", args,
        )
        # Store raw up to 2400 points; for larger queries keep at most 4 points
        # per one of 1000 time buckets. All raw records remain in SQLite.
        raw_points: list[tuple[int, float]] = []
        buckets: dict[int, dict[str, tuple[int, float]]] = {}
        sampled = False
        count = 0
        first = last = None

        def add_to_bucket(pair: tuple[int, float]) -> None:
            ix = min(999, max(0, int((pair[0] - low) * 999 / max(1, high - low))))
            old = buckets.get(ix)
            if old is None:
                buckets[ix] = {"first": pair, "last": pair, "min": pair, "max": pair}
                return
            old["last"] = pair
            if pair[1] < old["min"][1]:
                old["min"] = pair
            if pair[1] > old["max"][1]:
                old["max"] = pair

        while chunk := cursor.fetchmany(500):
            for timestamp, raw in chunk:
                try:
                    obj = json.loads(raw)
                    value = _bridge_number((obj.get("harmonized") or {}).get(field))
                except (TypeError, ValueError, AttributeError):
                    continue
                if value is None or timestamp is None:
                    continue
                if series == "sleep_duration_minutes":
                    value = round(value / 60000, 2)
                pair = (int(timestamp), value)
                count += 1
                if first is None:
                    first = pair[0]
                last = pair[0]
                if not sampled and len(raw_points) < 2400:
                    raw_points.append(pair)
                else:
                    if not sampled:
                        sampled = True
                        for existing in raw_points:
                            add_to_bucket(existing)
                        raw_points.clear()
                    add_to_bucket(pair)

        if sampled:
            points = sorted({p for b in buckets.values() for p in b.values()},
                            key=lambda item: (item[0], item[1]))
        else:
            points = raw_points
    return {"series": series, "label": HISTORY_LABELS[series][0],
            "unit": HISTORY_LABELS[series][1], "count": count,
            "plotted": len(points), "sampled": sampled, "first": first,
            "last": last, "points": [[x, y] for x, y in points]}



# ---- Calorie/weight correlation: read-only calendar-day measurements ----
# The endpoint exposes daily summaries only. It never changes records, audit
# events, retention, the Android sync endpoint, or HA Recorder state.
def _bridge_calorie_weight_days(storage: BridgeStorage, tz_name: str) -> dict:
    """Read actual food and weigh-ins in the HA local timezone.

    Aggregate nutrition calories are preferred, with entry sums as a fallback.
    Both are included only as a consistency diagnostic, never added together.
    For each day, use the earliest reading between 05:00 and 10:59, otherwise
    the earliest available reading (flagged as outside the preferred window).
    """
    tz = ZoneInfo(tz_name)
    daily: dict[str, dict] = {}

    def bucket(day: str) -> dict:
        if day not in daily:
            daily[day] = {"day": day, "entries": 0, "entry_calories": 0.0,
                          "aggregate_calories": None, "weights": []}
        return daily[day]

    # Open the existing database in SQLite's *strict* read-only mode; do not
    # call BridgeStorage.connection(), whose initializer creates tables.
    with closing(sqlite3.connect(f"file:{storage.path}?mode=ro", uri=True, timeout=10)) as conn:
        cursor = conn.execute("""SELECT record_type,sample_ts,data_json
            FROM records WHERE deleted=0 AND record_type IN
            ('nutrition','aggregate_nutrition_total_calories','body_composition')
            ORDER BY sample_ts,uid""")
        for kind, ts, raw in cursor:
            if not isinstance(ts, int) or ts < 946684800000:
                continue
            try:
                source = json.loads(raw)
                fields = source.get("harmonized") or {}
                if not isinstance(fields, dict):
                    continue
            except (TypeError, ValueError, AttributeError):
                continue
            time = datetime.fromtimestamp(ts / 1000.0, tz)
            item = bucket(time.date().isoformat())
            if kind == "nutrition":
                value = _bridge_number(fields.get("calories"))
                if value is not None and 0 <= value <= 20000:
                    item["entries"] += 1
                    item["entry_calories"] += value
            elif kind == "aggregate_nutrition_total_calories":
                value = _bridge_number(fields.get("value"))
                if value is not None and 0 <= value <= 20000:
                    # Aggregate rows are a single daily total. If duplicates
                    # occur, the last observed source timestamp wins.
                    item["aggregate_calories"] = value
            else:
                kg = _bridge_number(fields.get("weight"))
                if kg is not None and 2 < kg < 600:
                    item["weights"].append((ts, time, kg * 2.20462262185))

    result = []
    for day in sorted(daily):
        item = daily[day]
        measured = item["weights"]
        mornings = [m for m in measured if 5 <= m[1].hour < 11]
        selected = min(mornings or measured, key=lambda v: v[0]) if measured else None
        aggregate = item["aggregate_calories"]
        entries = item["entries"]
        entry_total = item["entry_calories"] if entries else None
        calories = aggregate if aggregate is not None else entry_total
        # An empty aggregate without any actual food entry is not evidence of
        # a day with zero intake. Treat it as absent rather than fasting.
        if calories == 0 and not entries:
            calories = None
        # Do not return unnecessary days (only contains malformed source JSON).
        if calories is None and selected is None:
            continue
        result.append({
            "day": day,
            "calories": round(calories, 1) if calories is not None else None,
            "calorie_source": ("aggregate" if aggregate is not None else "entries") if calories is not None else None,
            "food_entries": entries,
            "calorie_disagreement": aggregate is not None and entry_total is not None
                and abs(aggregate - entry_total) > 1.0,
            "weight_lb": round(selected[2], 2) if selected else None,
            "weight_time": selected[1].strftime("%H:%M") if selected else None,
            "weight_morning": bool(mornings),
            "weight_readings": len(measured),
        })
    return {"time_zone": tz_name, "today": datetime.now(tz).date().isoformat(),
            "days": result}


class CalorieWeightDailyView(HomeAssistantView):
    """Admin-only aggregate daily data for the calorie/weight dashboard."""
    url = "/api/samsung_health_bridge/calorie_weight_daily"
    name = "api:samsung_health_bridge:calorie_weight_daily"
    requires_auth = True

    def __init__(self, hass: HomeAssistant, storage: BridgeStorage) -> None:
        self.hass = hass
        self.storage = storage

    @require_admin
    async def get(self, request: web.Request) -> web.Response:
        if not self.hass.data.get(RECEIVER_ACTIVE_KEY, False):
            return web.json_response({"error": "Samsung Health Bridge is unloaded"},
                                     status=503, headers={"Cache-Control": "no-store"})
        try:
            result = await self.hass.async_add_executor_job(
                _bridge_calorie_weight_days, self.storage, self.hass.config.time_zone)
            return web.json_response(result, headers={"Cache-Control": "no-store"})
        except (sqlite3.Error, ValueError, OSError) as exc:
            LOGGER.warning("Calorie/weight daily read failed: %s", type(exc).__name__)
            return web.json_response({"error": "Unable to read daily measurements"}, status=500,
                                     headers={"Cache-Control": "no-store"})
# ---- End calorie/weight endpoint ----


class HistoryView(HomeAssistantView):
    """Authenticated read-only historical values, never record payloads."""
    url = "/api/samsung_health_bridge/history"
    name = "api:samsung_health_bridge:history"
    requires_auth = True

    def __init__(self, hass: HomeAssistant, storage: BridgeStorage) -> None:
        self.hass = hass
        self.storage = storage

    @require_admin
    async def get(self, request: web.Request) -> web.Response:
        if not self.hass.data.get(RECEIVER_ACTIVE_KEY, False):
            return web.json_response({"error": "Samsung Health Bridge is unloaded"},
                                     status=503, headers={"Cache-Control": "no-store"})
        try:
            series = request.query.get("series", "")
            if series not in BRIDGE_HISTORIES:
                raise ValueError("Unknown history series")
            def epoch(name: str) -> int | None:
                text = request.query.get(name)
                if text is None or text == "":
                    return None
                if len(text) > 16 or not text.isascii() or not text.isdigit():
                    raise ValueError("Invalid time range")
                stamp = int(text)
                if stamp > 4102444800000:
                    raise ValueError("Time out of range")
                return stamp
            start, end = epoch("start"), epoch("end")
            if start is not None and end is not None and end < start:
                raise ValueError("End precedes start")
            result = await self.hass.async_add_executor_job(
                _bridge_full_history, self.storage, series, start, end)
            return web.json_response(result, headers={"Cache-Control": "no-store"})
        except ValueError as exc:
            return web.json_response({"error": str(exc)}, status=400,
                                     headers={"Cache-Control": "no-store"})
# ---- End v0.3.5 extension ----


class SyncView(HomeAssistantView):
    """Bearer-authenticated HA endpoint. Requires a valid Home Assistant user token."""
    url = "/api/samsung_health_bridge/sync"
    name = "api:samsung_health_bridge:sync"
    requires_auth = True

    def __init__(self, hass: HomeAssistant, storage: BridgeStorage) -> None:
        self.hass = hass
        self.storage = storage

    async def post(self, request: web.Request) -> web.Response:
        if not self.hass.data.get(RECEIVER_ACTIVE_KEY, False):
            return web.json_response({"error": "Samsung Health Bridge is unloaded"},
                                     status=503, headers={"Cache-Control": "no-store"})
        if request.content_length and request.content_length > MAX_BODY:
            raise web.HTTPRequestEntityTooLarge(max_size=MAX_BODY, actual_size=request.content_length)
        try:
            data = await request.json()
            if not isinstance(data, dict) or data.get("schema") != 1:
                raise ValueError("Invalid bridge envelope schema")
            kind = data.get("type")
            if kind not in ALLOWED:
                raise ValueError("Unsupported source record type")
            records = data.get("records", [])
            deleted = data.get("deleted_uids", [])
            if not isinstance(records, list) or not isinstance(deleted, list) or len(records) > 100 or len(deleted) > 200:
                raise ValueError("Invalid or oversized batch")
            if any(not isinstance(s, dict) for s in records):
                raise ValueError("Invalid record JSON")
            result = await self.hass.async_add_executor_job(self.storage.put_batch, kind, records, deleted)
        except (ValueError, TypeError, json.JSONDecodeError) as err:
            return web.json_response({"error": str(err)}, status=400)
        snapshot = await self.hass.async_add_executor_job(self.storage.statistics)
        if self.hass.data.get(REGISTERED_MODE_KEY):
            await _refresh_registered_states(self.hass, self.storage, snapshot, received=True)
        else:
            # Original YAML behavior, unchanged until the explicit UI migration.
            refresh_states(self.hass, snapshot)
            await _bridge_refresh_extended(self.hass, self.storage, snapshot)
            self.hass.states.async_set(
                "sensor.samsung_bridge_last_received", datetime.now(timezone.utc).isoformat(),
                {"friendly_name": "Samsung Bridge Last Received", "test_build": True},
            )
        return web.json_response({"ok": True, **result})


async def _async_start_receiver(hass: HomeAssistant, *, registered: bool = False) -> None:
    """Start once, with legacy YAML or registered-entity publishing selected.

    Switching modes during an active HA process is deliberately forbidden.
    Remove the legacy YAML key and restart HA before enabling the UI entry.
    """
    if isinstance(hass.data.get(DOMAIN), BridgeStorage):
        if bool(hass.data.get(REGISTERED_MODE_KEY)) != registered:
            raise ConfigEntryNotReady(
                "Restart Home Assistant without the legacy samsung_health_bridge "
                "YAML configuration before enabling registered sensors"
            )
        # A UI entry reload reactivates the existing views without re-registering routes.
        hass.data[RECEIVER_ACTIVE_KEY] = True
        return
    storage = BridgeStorage(Path(hass.config.config_dir) / "samsung_health_bridge" / "records.sqlite3")
    await hass.async_add_executor_job(storage.initialize)
    snapshot = await hass.async_add_executor_job(storage.statistics)
    hass.data[REGISTERED_MODE_KEY] = registered
    if registered:
        await _refresh_registered_states(hass, storage, snapshot)
    else:
        refresh_states(hass, snapshot)
        await _bridge_refresh_extended(hass, storage, snapshot)
    hass.http.register_view(SyncView(hass, storage))
    hass.http.register_view(HistoryView(hass, storage))
    hass.http.register_view(CalorieWeightDailyView(hass, storage))
    hass.data[DOMAIN] = storage
    hass.data[RECEIVER_ACTIVE_KEY] = True
    LOGGER.info("Samsung Health Bridge receiver ready (registered=%s)", registered)


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Preserve the existing YAML installation without adding duplicate views.

    When no YAML key is present, the receiver starts through a config entry.
    """
    if DOMAIN in config:
        await _async_start_receiver(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Activate UI-managed sensors only after legacy YAML is removed."""
    if isinstance(hass.data.get(DOMAIN), BridgeStorage) and not hass.data.get(REGISTERED_MODE_KEY):
        raise ConfigEntryNotReady(
            "Legacy YAML receiver is still running; remove its YAML key and restart first"
        )
    await _async_start_receiver(hass, registered=True)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload entities and disable HTTP handlers until UI reload/restart.

    Home Assistant currently has no supported unregister_view() counterpart
    for HTTP views. Handlers therefore remain bound but reject requests while
    the integration is unloaded; they are not re-registered on UI reload.
    """
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        hass.data[RECEIVER_ACTIVE_KEY] = False
    return unloaded
