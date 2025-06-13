# File: __init__.py
# Description: Python file for initialising the BrightDock integration.
# Author: Chuffnugget

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr

from .const import DOMAIN
from .coordinator import DDCDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)
PLATFORMS = ["sensor", "number"]

async def async_setup(hass: HomeAssistant, config: dict):
    """Set up the integration (no-op - all config via UI)."""
    hass.data.setdefault(DOMAIN, {})
    return True

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Set up a config entry and start the DataUpdateCoordinator."""
    host = entry.data["host"]
    port = entry.data["port"]

    # 1) Register this BrightDock Core as a device
    dev_reg = dr.async_get(hass)
    dev_reg.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, f"{host}:{port}")},
        name=f"BrightDock Core @ {host}",
        manufacturer="Chuffnugget",
        model="BrightDock Core",
    )

    # 2) Start the coordinator
    coordinator = DDCDataUpdateCoordinator(hass, host, port)
    await coordinator.async_config_entry_first_refresh()
    hass.data[DOMAIN][entry.entry_id] = coordinator

    _LOGGER.info(
        "Forwarding BrightDock entry to platforms @ %s:%s", host, port
    )
    # 3) Forward to sensor & number platforms
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Unload a config entry and its platforms."""
    unload_ok = await hass.config_entries.async_unload_platforms(
        entry, PLATFORMS
    )
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok

