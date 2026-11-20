"""Registry-backed sensors preserving the Samsung Bridge legacy entity IDs.

Never install this staged file over a running YAML-based receiver. Its activation
requires a controlled restart with the old `samsung_health_bridge:` YAML key
removed; see docs/STEP4B_ENTITY_MIGRATION.md.
"""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import DOMAIN, ENTITY_VALUES_KEY, UPDATE_SIGNAL, bridge_sensor_suffixes

_LOGGER = logging.getLogger(__name__)


class SamsungBridgeSensor(SensorEntity):
    """One stable entity corresponding to an existing legacy sensor."""

    _attr_has_entity_name = False
    _attr_should_poll = False

    def __init__(self, suffix: str) -> None:
        self._legacy_id = f"sensor.samsung_bridge_{suffix}"
        self.entity_id = self._legacy_id
        self._attr_unique_id = f"samsung_bridge_{suffix}"
        self._attr_name = "Samsung Bridge " + suffix.replace("_", " ").title()
        self._attr_native_value = None
        self._attr_extra_state_attributes: dict[str, Any] = {}

    async def async_added_to_hass(self) -> None:
        """Subscribe to receiver pushes and load initial cached values."""
        await super().async_added_to_hass()
        if self.entity_id != self._legacy_id:
            _LOGGER.error("Entity ID migration mismatch: expected %s; got %s",
                          self._legacy_id, self.entity_id)
        self.async_on_remove(async_dispatcher_connect(self.hass, UPDATE_SIGNAL, self._refresh))
        self._refresh()

    @callback
    def _refresh(self) -> None:
        values = self.hass.data.get(ENTITY_VALUES_KEY, {})
        data = values.get(self._legacy_id)
        if data is None:
            return
        value, attrs = data
        self._attr_native_value = value
        attrs = dict(attrs)
        name = attrs.pop("friendly_name", None)
        if name:
            self._attr_name = str(name)
        self._attr_native_unit_of_measurement = attrs.pop("unit_of_measurement", None)
        self._attr_extra_state_attributes = attrs
        self.async_write_ha_state()


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Fail closed if registry or runtime names could be taken by other entities."""
    registry = er.async_get(hass)
    suffixes = bridge_sensor_suffixes()
    if len(suffixes) != 103:
        raise ConfigEntryNotReady("Unexpected Samsung Health Bridge entity catalog")
    for suffix in suffixes:
        eid = f"sensor.samsung_bridge_{suffix}"
        reg = registry.async_get(eid)
        if reg is not None and (reg.platform != DOMAIN or reg.unique_id != f"samsung_bridge_{suffix}"):
            raise ConfigEntryNotReady(f"Entity ID collision: {eid}")
        # An unregistered legacy raw state can still exist when a user enables
        # the config flow without restarting the YAML receiver. Do not steal it.
        if reg is None and hass.states.get(eid) is not None:
            raise ConfigEntryNotReady(f"Legacy state still active: {eid}. Restart without YAML receiver")
    async_add_entities([SamsungBridgeSensor(suffix) for suffix in suffixes])
