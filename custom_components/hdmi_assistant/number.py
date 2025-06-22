# File: custom_components/hdmi_assistant/number.py
# Description: Manages number entities (brightness, contrast) for HDMI Assistant.
# Author: Chuffnugget

import logging
from homeassistant.components.number import NumberEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass, entry, async_add_entities):
    """Set up Number entities for each supported control (brightness, contrast)."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    entities = []

    # Only brightness & contrast get NumberEntities. input_source is handled by select.py.
    for ctrl, values in coordinator.data["controls"].items():
        if ctrl not in ("brightness", "contrast"):
            continue
        for mon_id in values.keys():
            _LOGGER.info("Registering Number entity: Monitor %s %s", mon_id, ctrl)
            entities.append(AssistantNumber(coordinator, entry.entry_id, mon_id, ctrl))

    async_add_entities(entities, update_before_add=True)

class AssistantNumber(CoordinatorEntity, NumberEntity):
    """Representation of a DDC/CI control (brightness, contrast) under HDMI Assistant."""

    def __init__(self, coordinator, entry_id: str, mon_id: int, control: str):
        super().__init__(coordinator)
        self._entry_id = entry_id
        self._mon_id = mon_id
        self._control = control

        self._attr_name = f"Monitor {mon_id} {control.replace('_',' ').title()}"
        self._attr_unique_id = f"{entry_id}_{mon_id}_{control}"

        # brightness & contrast range 0–100%
        self._attr_min_value = 0
        self._attr_max_value = 100
        self._attr_step = 1
        self._attr_mode = "slider"
        self._attr_unit_of_measurement = "%"

    @property
    def native_value(self) -> float | None:
        return self.coordinator.data["controls"][self._control].get(self._mon_id)

    async def async_set_native_value(self, value: float) -> None:
        url = f"http://{self.coordinator.host}:{self.coordinator.port}"
        payload = {self._control: int(value)}
        _LOGGER.info("Writing %s for monitor %s → %s", self._control, self._mon_id, value)

        # 1) POST to the node
        await self.coordinator.session.post(
            f"{url}/monitors/{self._mon_id}/{self._control}", json=payload
        )

        # 2) Optimistically update our local state & push immediately to HA
        self.coordinator.data["controls"][self._control][self._mon_id] = int(value)
        self.async_write_ha_state()

        # 3) Then schedule a full refresh in background
        await self.coordinator.async_request_refresh()

        # 4) Fire user-action event
        self.coordinator.hass.bus.async_fire(
            f"{DOMAIN}_control_changed",
            {"monitor_id": self._mon_id, "control": self._control, "value": int(value)},
        )

    @property
    def device_info(self) -> dict:
        """Tie this entity to the HDMI Assistant Node device."""
        return {
            "identifiers": {(DOMAIN, self._entry_id)},
            "name": f"HDMI Assistant Node @ {self.coordinator.host}:{self.coordinator.port}",
            "manufacturer": "Chuffnugget",
            "model": "HDMI Assistant Node",
        }
