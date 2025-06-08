import voluptuous as vol
from homeassistant import config_entries

from .const import DOMAIN, CONF_HOST, CONF_PORT, DEFAULT_PORT

class DDCConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle the config flow for DDC CI Assistant."""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        errors = {}
        if user_input:
            return self.async_create_entry(
                title=f"DDC CI Assistant @ {user_input[CONF_HOST]}",
                data=user_input
            )

        data_schema = vol.Schema({
            vol.Required(CONF_HOST): str,
            vol.Optional(CONF_PORT, default=DEFAULT_PORT): int,
        })
        return self.async_show_form(
            step_id="user",
            data_schema=data_schema,
            errors=errors
        )
