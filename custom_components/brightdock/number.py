import logging

from homeassistant.components.number import NumberEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass, entry, async_add_entities):
    """Set up Number entities for each supported control."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    entities = []

    for ctrl, values in coordinator.data["controls"].items():
        for mon_id, val in values.items():
            _LOGGER.info("Registering Number entity: Monitor %s %s", mon_id, ctrl)
            entities.append(DDCNumber(coordinator, entry.entry_id, mon_id, ctrl))

    async_add_entities(entities, update_before_add=True)

class DDCNumber(CoordinatorEntity, NumberEntity):
    """Representation of a DDC/CI control (brightness, contrast, input)."""

    def __init__(self, coordinator, entry_id: str, mon_id: int, control: str):
        super().__init__(coordinator)
        self._entry_id = entry_id
        self._mon_id = mon_id
        self._control = control

        self._attr_name = f"Monitor {mon_id} {control.replace('_', ' ').title()}"
        self._attr_unique_id = f"{entry_id}_{mon_id}_{control}"

        # brightness/contrast: 0–100%, input_source: raw code 0–255
        if control in ("brightness", "contrast"):
            self._attr_min_value = 0
            self._attr_max_value = 100
            self._attr_step = 1
            self._attr_mode = "slider"
            self._attr_unit_of_measurement = "%"
        else:
            self._attr_min_value = 0
            self._attr_max_value = 255
            self._attr_step = 1
            self._attr_mode = "box"

    @property
    def value(self) -> float | None:
        """Return the current value from the coordinator."""
        return self.coordinator.data["controls"][self._control].get(self._mon_id)

    async def async_set_value(self, value: float) -> None:
        """Handle user changing the value; POST back to the REST server."""
        url = f"http://{self.coordinator.host}:{self.coordinator.port}"
        payload = {self._control: int(value)}
        _LOGGER.info(
            "Writing %s for monitor %s → %s",
            self._control, self._mon_id, value
        )
        await self.coordinator.session.post(
            f"{url}/monitors/{self._mon_id}/{self._control}",
            json=payload
        )
        await self.coordinator.async_request_refresh()
