from homeassistant.components.number import NumberEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import DDCDataUpdateCoordinator

async def async_setup_entry(hass, entry, async_add_entities):
    """Set up Number entities for brightness, contrast, and input_source."""
    coordinator: DDCDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities = []

    for control in ("brightness", "contrast", "input_source"):
        for mon_id, value in coordinator.data[control].items():
            entities.append(DDCNumber(coordinator, entry.entry_id, mon_id, control))

    async_add_entities(entities, update_before_add=True)

class DDCNumber(CoordinatorEntity, NumberEntity):
    """Representation of a single DDC/CI control as a Number entity."""

    def __init__(self, coordinator, entry_id: str, mon_id: int, control: str):
        super().__init__(coordinator)
        self._entry_id = entry_id
        self._mon_id = mon_id
        self._control = control  # "brightness", "contrast", or "input_source"

        # e.g. "Monitor 0 Brightness", "Monitor 1 Contrast"
        self._attr_name = f"Monitor {mon_id} {control.replace('_', ' ').title()}"
        self._attr_unique_id = f"{entry_id}_{mon_id}_{control}"

        # Input range: brightness & contrast 0–100; input_source 0–255 (raw code)
        self._attr_min_value = 0
        self._attr_max_value = 100 if control != "input_source" else 255
        self._attr_step = 1
        self._attr_mode = "slider"  # Use a slider in the UI

    @property
    def value(self) -> float | None:
        """Return the current control value from coordinator data."""
        return self.coordinator.data[self._control].get(self._mon_id)

    async def async_set_value(self, value: float) -> None:
        """Handle user changing the value in the UI; POST to REST server."""
        url = f"http://{self.coordinator.host}:{self.coordinator.port}"
        payload = {self._control: int(value)}
        await self.coordinator.session.post(
            f"{url}/monitors/{self._mon_id}/{self._control}",
            json=payload
        )
        # After setting the value, request an immediate refresh
        await self.coordinator.async_request_refresh()
