import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .coordinator import DDCDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

async def async_setup(hass: HomeAssistant, config: dict):
    """Set up the integration (no-op - all config via UI)."""
    hass.data.setdefault(DOMAIN, {})
    return True

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Set up a config entry and start the DataUpdateCoordinator."""
    host = entry.data["host"]
    port = entry.data["port"]

    coordinator = DDCDataUpdateCoordinator(hass, host, port)
    await coordinator.async_config_entry_first_refresh()

    hass.data[DOMAIN][entry.entry_id] = coordinator

    _LOGGER.info(
        "Forwarding DDC CI Assistant entry to platforms @ %s:%s", host, port
    )
    # Forward the entry to sensor and number platforms
    await hass.config_entries.async_forward_entry_setup(entry, "sensor")
    await hass.config_entries.async_forward_entry_setup(entry, "number")

    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Unload a config entry and its platforms."""
    unload_ok = await hass.config_entries.async_unload_platforms(
        entry, ["sensor", "number"]
    )
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok
