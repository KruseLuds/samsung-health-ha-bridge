package com.kvs.samsunghealthreporter.example.bridge

import com.kvs.samsunghealthreporter.SamsungHealthException
import com.kvs.samsunghealthreporter.SamsungHealthReporter
import com.kvs.samsunghealthreporter.model.TimeGroup
import com.kvs.samsunghealthreporter.model.TimeRange
import com.kvs.samsunghealthreporter.model.type.Aggregation
import com.kvs.samsunghealthreporter.model.type.HealthType
import com.kvs.samsunghealthreporter.model.type.TimeGroupUnit
import com.kvs.samsunghealthreporter.service.aggregate
import org.json.JSONObject
import java.security.MessageDigest

/** Extra SDK capabilities not supported by the raw sample/changes endpoints in Bridge v0.2. */
internal object BridgeExtras {
    // Exercise location is NOT a separate sample/aggregate; it is permission to read
    // GPS routes nested inside exercise records. Leave it excluded by default.
    val additionalReadTypes: Set<HealthType> = HealthType.entries
        .filter { it.aggregations.isNotEmpty() || it == HealthType.USER_PROFILE }
        .toSet()

    val allReadTypes: Set<HealthType> = HealthType.entries
        .filter { it.isReadable || it in additionalReadTypes }
        .toSet()

    const val AGGREGATE_REFRESH_MS: Long = 15 * 60 * 1000L

    internal data class Outcome(val transmitted: Int, val skipped: List<String>)

    /**
     * Read every SDK aggregate (20 operations) in daily buckets for the last 7 local days.
     * Each record has a stable synthetic UID and only changed values are uploaded.
     * No SDK write, wake lock, or continuous listener.
     */
    suspend fun sync(
        reporter: SamsungHealthReporter,
        prefs: BridgePrefs,
        grants: Set<HealthType>,
        forced: Boolean,
        deliver: suspend (String, List<JSONObject>) -> Unit,
        stage: (String) -> Unit,
        note: (String) -> Unit,
    ): Outcome {
        val now = System.currentTimeMillis()
        if (!forced && now - prefs.lastAggregateCheck < AGGREGATE_REFRESH_MS) {
            note("aggregate check skipped: 15-minute throttle")
            return Outcome(0, emptyList())
        }
        val skipped = mutableListOf<String>()
        var sent = 0
        // One calendar-week lookback, with local-day grouping, catches edits to recent data.
        val range = TimeRange.lastDays(7)
        val dayGroup = TimeGroup(TimeGroupUnit.DAILY)
        for (aggregation in Aggregation.entries) {
            if (aggregation.healthType !in grants) continue
            try {
                stage("SDK aggregate: ${aggregation.name}")
                val kind = "aggregate_${aggregation.name.lowercase()}"
                val rows = reporter.reader.aggregate(aggregation, range, group = dayGroup)
                for (bucket in rows) {
                    val value = bucket.value ?: continue // null means no measurement; never turn it into zero
                    if (!value.isFinite()) continue
                    val uid = "${aggregation.name}:${bucket.startTimestamp}"
                    val payload = JSONObject()
                        .put("uid", uid)
                        .put("startTimestamp", bucket.startTimestamp)
                        .put("endTimestamp", bucket.endTimestamp)
                        .put("dataSource", JSONObject().put("appId", "com.sec.android.app.shealth"))
                        .put("harmonized", JSONObject()
                            .put("aggregation", aggregation.name)
                            .put("value", value)
                            .put("unit", bucket.unit))
                    val hash = sha(payload.toString())
                    if (prefs.payloadDigest(kind, uid) == hash) continue
                    // Acknowledgment before checkpoint: retries are idempotent by (type, uid).
                    deliver(kind, listOf(payload))
                    prefs.setPayloadDigest(kind, uid, hash)
                    sent++
                }
            } catch (e: SamsungHealthException) {
                // Some aggregate operations may not be offered for the device/account.
                // This must not suppress the other independently readable categories.
                skipped += "${aggregation.name}: ${e.javaClass.simpleName}"
                note("SDK aggregate skipped: ${aggregation.name} (${e.javaClass.simpleName})")
            }
        }
        if (HealthType.USER_PROFILE in grants) {
            try {
                stage("SDK: user profile")
                reporter.reader.userProfile()?.let { profile ->
                    val kind = "user_profile"
                    val uid = "samsung_user_profile"
                    val hash = sha(profile.json)
                    if (prefs.payloadDigest(kind, uid) != hash) {
                        val payload = JSONObject()
                            .put("uid", uid)
                            .put("startTimestamp", now)
                            .put("dataSource", JSONObject().put("appId", "com.sec.android.app.shealth"))
                            .put("harmonized", JSONObject(profile.json))
                        deliver(kind, listOf(payload))
                        prefs.setPayloadDigest(kind, uid, hash)
                        sent++
                    }
                }
            } catch (e: SamsungHealthException) {
                skipped += "USER_PROFILE: ${e.javaClass.simpleName}"
                note("SDK user profile skipped: ${e.javaClass.simpleName}")
            }
        }
        // If Samsung rejects an operation, retry its investigation later, not every minute.
        prefs.lastAggregateCheck = now
        return Outcome(sent, skipped)
    }

    private fun sha(s: String): String = MessageDigest.getInstance("SHA-256")
        .digest(s.toByteArray(Charsets.UTF_8))
        .joinToString("") { "%02x".format(it) }
}
