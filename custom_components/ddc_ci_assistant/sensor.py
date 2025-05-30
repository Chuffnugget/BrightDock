from homeassistant.components.sensor import SensorEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import DDCDataUpdateCoordinator

async def async_setup_entry(hass, entry, async_add_entities):
    """Set up Sensor entities for monitor model names."""
    coordinator: DDCDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities = []

    for mon in coordinator.data["monitors"]:
        mon_id = mon["id"]
        model = mon.get("model")
        entities.append(DDCSensor(coordinator, entry.entry_id, mon_id, model))

    async_add_entities(entities)

class DDCSensor(CoordinatorEntity, SensorEntity):
    """Representation of a monitor’s model name as a read‐only Sensor."""

    def __init__(self, coordinator, entry_id: str, mon_id: int, model: str):
        super().__init__(coordinator)
        self._entry_id = entry_id
        self._mon_id = mon_id
        self._model = model

        # e.g. "Monitor 0 Model"
        self._attr_name = f"Monitor {mon_id} Model"
        self._attr_unique_id = f"{entry_id}_{mon_id}_model"

    @property
    def native_value(self) -> str:
        """Return the model name as the sensor’s state."""
        return self._model
