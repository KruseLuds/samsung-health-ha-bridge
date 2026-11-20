"""Home Assistant UI configuration for the Samsung Health Bridge receiver.

This creates one local receiver entry, not a Samsung account connection.
The phone app obtains its own Samsung permissions and is configured separately.
"""
from __future__ import annotations

from typing import Any

from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult

from . import DOMAIN


class SamsungHealthBridgeConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """One local, authenticated Home Assistant receiver per HA instance."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Confirm that the user wants to enable the receiver."""
        if user_input is not None:
            await self.async_set_unique_id("local_receiver")
            self._abort_if_unique_id_configured()
            return self.async_create_entry(title="Samsung Health Bridge", data={})

        self._set_confirm_only()
        return self.async_show_form(step_id="user")
