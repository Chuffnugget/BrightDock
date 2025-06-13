# File: config_flow.py
# Description: Python file for managing the BrightDock devices and integration setup.
# Author: Chuffnugget

from __future__ import annotations
import voluptuous as vol
import logging

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.const import CONF_HOST, CONF_PORT

from .const import DOMAIN, DEFAULT_PORT

_LOGGER = logging.getLogger(__name__)


class BrightDockConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for BrightDock."""

    VERSION = 1
    CONNECTION_CLASS = config_entries.CONN_CLASS_LOCAL_POLL

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """User-initiated setup (manually enter host/port)."""
        errors: dict[str, str] = {}

        if user_input is not None:
            return self.async_create_entry(
                title=f"BrightDock @ {user_input[CONF_HOST]}",
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
        self, discovery_info: dict[str, Any]
    ) -> FlowResult:
        """Automatically configure discovered BrightDock Core via mDNS/zeroconf."""
        host = discovery_info.get("host")
        port = discovery_info.get("port", DEFAULT_PORT)
        _LOGGER.debug("Zeroconf discovered BrightDock Core at %s:%s", host, port)

        return self.async_create_entry(
            title=f"BrightDock @ {host}",
            data={CONF_HOST: host, CONF_PORT: port},
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """If you later add options, return an OptionsFlow here."""
        return None

