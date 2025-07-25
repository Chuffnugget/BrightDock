# File: custom_components/hdmi_assistant/select.py
# Description: Manages select entities (input_source) for HDMI Assistant.
# Author: Chuffnugget

import logging
from homeassistant.components.select import SelectEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.helpers.entity import DeviceInfo

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, entry, async_add_entities):
    """Set up Input Select entities for each monitor’s input_source."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    entities = []

    for mon in coordinator.data.get("monitors", []):
        mid = mon["id"]
        if mid in coordinator.data.get("input_source_options", {}):
            entities.append(AssistantInputSelect(coordinator, entry.entry_id, mid))

    async_add_entities(entities, update_before_add=True)


class AssistantInputSelect(CoordinatorEntity, SelectEntity):
    """Dropdown for a monitor’s input-source feature."""

    def __init__(self, coordinator, entry_id: str, mon_id: int):
        super().__init__(coordinator)
        self._entry_id = entry_id
        self._mon_id = mon_id

        self._attr_name = f"Monitor {mon_id} Input Source"
        self._attr_unique_id = f"{entry_id}_{mon_id}_input_source"

        opts = coordinator.data.get("input_source_options", {}).get(mon_id, {})
        self._attr_options = list(opts.values())

    @property
    def current_option(self) -> str | None:
        raw = self.coordinator.data.get("controls", {}).get("input_source", {}).get(self._mon_id)
        if raw is None:
            return None
        key = f"{raw:02x}"
        return self.coordinator.data.get("input_source_options", {}).get(self._mon_id, {}).get(key)

    async def async_select_option(self, option: str) -> None:
        """Handle user selecting a new input source."""
        opts = self.coordinator.data.get("input_source_options", {}).get(self._mon_id, {})
        rev = {v: k for k, v in opts.items()}
        hex_key = rev.get(option)
        if hex_key is None:
            _LOGGER.warning("Invalid input_source option %s for monitor %s", option, self._mon_id)
            return

        value = int(hex_key, 16)
        _LOGGER.info("Queuing input_source write for monitor %s → %s (%s)", self._mon_id, option, hex_key)
        # 1) enqueue the write
        self.coordinator.enqueue_write(self._mon_id, "input_source", value)

        # 2) Optimistic update in UI
        self.coordinator.data.setdefault("controls", {}).setdefault("input_source", {})[self._mon_id] = value
        self.async_write_ha_state()

        # 3) schedule a refresh to reconcile
        await self.coordinator.async_request_refresh()

    @property
    def device_info(self) -> DeviceInfo:
        """Tie this select entity back to the HDMI Assistant Node device."""
        host = self.coordinator.host
        port = self.coordinator.port
        return DeviceInfo(
            identifiers={(DOMAIN, self._entry_id)},
            name=f"HDMI Assistant Node @ {host}:{port}",
            manufacturer="Chuffnugget",
            model="HDMI Assistant Node",
        )
