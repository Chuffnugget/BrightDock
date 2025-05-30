import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN, CONF_HOST, CONF_PORT
from .coordinator import DDCDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

async def async_setup(hass: HomeAssistant, config: dict):
    """Set up the integration."""
    # Create a data dictionary keyed by config_entry_id
    hass.data.setdefault(DOMAIN, {})
    return True

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Set up a config entry for DDC CI Assistant."""
    host = entry.data[CONF_HOST]
    port = entry.data[CONF_PORT]

    # Create the coordinator and perform the first data fetch
    coordinator = DDCDataUpdateCoordinator(hass, host, port)
    await coordinator.async_config_entry_first_refresh()

    # Store coordinator under this entry_id
    hass.data[DOMAIN][entry.entry_id] = coordinator

    # Set up the platforms: number (for brightness/contrast/input) and sensor (for monitor model)
    hass.config_entries.async_setup_platforms(entry, ["number", "sensor"])
    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Unload a config entry."""
    # Unload platforms
    unload_ok = await hass.config_entries.async_unload_platforms(
        entry, ["number", "sensor"]
    )
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok
