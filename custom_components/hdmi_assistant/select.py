import logging
from homeassistant.components.select import SelectEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass, entry, async_add_entities):
    """Set up Input Select entities for each monitor’s input_source."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    entities = []

    for mon in coordinator.data["monitors"]:
        mid = mon["id"]
        if mid in coordinator.data["input_source_options"]:
            _LOGGER.info("Registering Select entity: Monitor %s Input Source", mid)
            entities.append(AssistantInputSelect(coordinator, entry.entry_id, mid))

    async_add_entities(entities, update_before_add=True)


class AssistantInputSelect(CoordinatorEntity, SelectEntity):
    """Dropdown for a monitor’s input‐source feature."""

    def __init__(self, coordinator, entry_id: str, mon_id: int):
        super().__init__(coordinator)
        self._entry_id = entry_id
        self._mon_id = mon_id

        self._attr_name = f"Monitor {mon_id} Input Source"
        self._attr_unique_id = f"{entry_id}_{mon_id}_input_source"

        # friendly options are the dict values
        opts = coordinator.data["input_source_options"].get(mon_id, {})
        self._attr_options = list(opts.values())

    @property
    def current_option(self) -> str | None:
        """Return the currently selected label."""
        val = self.coordinator.data["controls"]["input_source"].get(self._mon_id)
        opts = self.coordinator.data["input_source_options"].get(self._mon_id, {})
        return opts.get(f"{val:02x}")

    async def async_select_option(self, option: str) -> None:
        """Push the selected label back to the monitor."""
        opts = self.coordinator.data["input_source_options"].get(self._mon_id, {})
        rev = {v: k for k, v in opts.items()}
        hex_key = rev.get(option)
        if hex_key is None:
            _LOGGER.error("Unknown input source '%s' for monitor %s", option, self._mon_id)
            return

        value = int(hex_key, 16)
        url = f"http://{self.coordinator.host}:{self.coordinator.port}"
        _LOGGER.info("Setting input_source for monitor %s → %s (%d)", self._mon_id, option, value)
        try:
            await self.coordinator.session.post(
                f"{url}/monitors/{self._mon_id}/input_source",
                json={"input_source": value},
            )
        except Exception as err:
            _LOGGER.error("Failed to set input_source on monitor %s: %s", self._mon_id, err)
        finally:
            await self.coordinator.async_request_refresh()

    @property
    def device_info(self) -> dict:
        """Tie this select entity to the HDMI Assistant Node device."""
        host = self.coordinator.host
        port = self.coordinator.port
        return {
            "identifiers": {(DOMAIN, self._entry_id)},
            "name": f"HDMI Assistant Node @ {host}:{port}",
            "manufacturer": "Chuffnugget",
            "model": "HDMI Assistant Node",
        }
