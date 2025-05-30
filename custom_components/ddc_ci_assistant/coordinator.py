import logging
from datetime import timedelta

import aiohttp
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)

from .const import DOMAIN, UPDATE_INTERVAL

_LOGGER = logging.getLogger(__name__)

class DDCDataUpdateCoordinator(DataUpdateCoordinator):
    """Fetch data from the DDC CI REST server and update listeners."""

    def __init__(self, hass, host: str, port: int):
        self.host = host
        self.port = port
        self.session = aiohttp.ClientSession()

        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=UPDATE_INTERVAL),
        )

    async def _async_update_data(self):
        """Fetch data from REST endpoints and return a dict used by entities."""
        url_base = f"http://{self.host}:{self.port}"
        try:
            # 1) Get the list of monitors
            async with self.session.get(f"{url_base}/monitors") as resp:
                resp.raise_for_status()
                monitors = await resp.json()

            data = {
                "monitors": monitors,
                "brightness": {},
                "contrast": {},
                "input_source": {},
            }

            # 2) For each monitor, fetch brightness, contrast, input_source
            for mon in monitors:
                mid = mon["id"]
                for ctrl in ("brightness", "contrast", "input_source"):
                    async with self.session.get(f"{url_base}/monitors/{mid}/{ctrl}") as resp:
                        resp.raise_for_status()
                        ctrl_data = await resp.json()
                        data[ctrl][mid] = ctrl_data.get(ctrl)

            return data

        except Exception as err:
            _LOGGER.error("Error fetching DDC data: %s", err)
            raise UpdateFailed(f"Error fetching DDC data: {err}")
