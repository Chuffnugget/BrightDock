# File: custom_components/HDMI-Control/__init__.py
# Description: Python file for initialising the HDMI-Control integration.
# Author: Chuffnugget

import logging
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback, Event
from homeassistant.const import EVENT_STATE_CHANGED
from homeassistant.helpers.entity_registry import async_get as async_get_registry

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
        "Forwarding HDMI-Control Core entry to platforms @ %s:%s", host, port
    )
    await hass.config_entries.async_forward_entry_setups(entry, ["sensor", "number"])

    @callback
    def _log_state_changes(event: Event):
        """Log any brightness/contrast/input changes done by the user."""
        entity_id = event.data.get("entity_id")
        if not entity_id:
            return
        # Only log events for entities owned by this integration
        registry = async_get_registry(hass)
        reg_entry = registry.async_get(entity_id)
        if not reg_entry or reg_entry.domain != DOMAIN:
            return
        old = event.data.get("old_state")
        new = event.data.get("new_state")
        old_val = old.state if old else None
        new_val = new.state if new else None
        _LOGGER.info("User changed %s: %s → %s", entity_id, old_val, new_val)

    hass.bus.async_listen(EVENT_STATE_CHANGED, _log_state_changes)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Unload a config entry and its platforms."""
    unload_ok = await hass.config_entries.async_unload_platforms(
        entry, ["sensor", "number"]
    )
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok
