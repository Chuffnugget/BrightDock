# File: sensor.py
# Description: Manages sensor entities (model name + connection status) for HDMI Assistant.
# Author: Chuffnugget

import logging
from homeassistant.components.sensor import SensorEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.helpers.entity import DeviceInfo

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass, entry, async_add_entities):
    """Set up Sensor entities for each monitor model and connection status."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    entities = []

    # Connection status sensor
    entities.append(AssistantConnectionSensor(coordinator, entry))

    # One model‐name sensor per detected monitor
    for mon in coordinator.data["monitors"]:
        mon_id = mon["id"]
        model = mon.get("model")
        _LOGGER.info("Registering Sensor entity: Monitor %s Model", mon_id)
        entities.append(ModelSensor(coordinator, entry.entry_id, mon_id, model))

    async_add_entities(entities)

class AssistantConnectionSensor(CoordinatorEntity, SensorEntity):
    """Reports connection status to the HDMI Assistant Node."""

    def __init__(self, coordinator, entry):
        super().__init__(coordinator)
        self._entry_id = entry.entry_id
        host = entry.data["host"]
        port = entry.data["port"]
        self._attr_name = f"HDMI Assistant Connection @ {host}:{port}"
        self._attr_unique_id = f"{entry.entry_id}_connection_status"

    @property
    def native_value(self) -> str:
        """Return 'connected' or 'error: ...' based on last update."""
        success = getattr(self.coordinator, "last_update_success", False)
        if success:
            return "connected"
        err = self.coordinator.last_exception or "unknown"
        return f"error: {err}"

    @property
    def extra_state_attributes(self) -> dict:
        """Expose last exception, success flag, and last update time."""
        last_time = getattr(self.coordinator, "last_update_time", None)
        return {
            "last_exception": str(self.coordinator.last_exception),
            "last_update_success": getattr(self.coordinator, "last_update_success", False),
            "last_update_time": last_time.isoformat() if last_time else None,
        }

    @property
    def device_info(self) -> DeviceInfo:
        """Tie this sensor to the HDMI Assistant Node device."""
        host = self.coordinator.host
        port = self.coordinator.port
        return DeviceInfo(
            identifiers={(DOMAIN, self._entry_id)},
            name=f"HDMI Assistant Node @ {host}:{port}",
            manufacturer="Chuffnugget",
            model="HDMI Assistant Node",
        )

class ModelSensor(CoordinatorEntity, SensorEntity):
    """Represents a monitor’s model name."""

    def __init__(self, coordinator, entry_id: str, mon_id: int, model: str):
        super().__init__(coordinator)
        self._entry_id = entry_id
        self._mon_id = mon_id
        self._model = model

        self._attr_name = f"Monitor {mon_id} Model"
        self._attr_unique_id = f"{entry_id}_{mon_id}_model"

    @property
    def native_value(self) -> str:
        return self._model

    @property
    def device_info(self) -> DeviceInfo:
        host = self.coordinator.host
        port = self.coordinator.port
        return DeviceInfo(
            identifiers={(DOMAIN, self._entry_id)},
            name=f"HDMI Assistant Node @ {host}:{port}",
            manufacturer="Chuffnugget",
            model="HDMI Assistant Node",
        )
