# File: config_flow.py
# Description: Python file for managing the BrightDock devices and integration setup.
# Author: Chuffnugget
from __future__ import annotations

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import callback
from homeassistant.helpers.typing import DiscoveryInfoType

from .const import DOMAIN, DEFAULT_PORT

class DDCCIConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for BrightDock integration."""

    VERSION = 1
    CONNECTION_CLASS = config_entries.CONN_CLASS_LOCAL_POLL

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Handle the initial step where the user provides host/port."""
        errors: dict[str, str] = {}

        if user_input is not None:
            # Prevent duplicates by host:port
            await self.async_set_unique_id(f"{user_input[CONF_HOST]}:{user_input[CONF_PORT]}")
            self._abort_if_unique_id_configured()

            return self.async_create_entry(
                title=f"BrightDock @ {user_input[CONF_HOST]}:{user_input[CONF_PORT]}",
                data=user_input,
            )

        data_schema = vol.Schema(
            {
                vol.Required(CONF_HOST): str,
                vol.Optional(CONF_PORT, default=DEFAULT_PORT): int,
            }
        )
        return self.async_show_form(
            step_id="user", data_schema=data_schema, errors=errors
        )

    async def async_step_zeroconf(
        self, discovery_info: DiscoveryInfoType
    ) -> config_entries.FlowResult:
        """Handle zeroconf discovery of a BrightDock Core HTTP server."""
        host = discovery_info["host"]
        port = discovery_info["port"]

        # Prevent duplicates
        await self.async_set_unique_id(f"{host}:{port}")
        self._abort_if_unique_id_configured()

        return self.async_create_entry(
            title=f"BrightDock @ {host}:{port}",
            data={CONF_HOST: host, CONF_PORT: port},
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """If you later add options, return an OptionsFlow here."""
        return None
