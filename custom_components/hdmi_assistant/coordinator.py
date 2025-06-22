# File: coordinator.py
# Description: Python file fetching HDMI Assistant Node values and handling discovery.
# Author: Chuffnugget

import logging
from datetime import timedelta

import aiohttp
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN, UPDATE_INTERVAL

_LOGGER = logging.getLogger(__name__)

class HDMIDataUpdateCoordinator(DataUpdateCoordinator):
    """
    Coordinator that:
     1. Discovers which monitors and which controls (brightness, contrast, input)
     2. Periodically fetches their values via the HDMI Assistant Node REST API
    """

    CONTROLS = ["brightness", "contrast", "input_source"]

    def __init__(self, hass, host: str, port: int):
        self.host = host
        self.port = port
        self.session = aiohttp.ClientSession()
        # track last exception for the connection-status sensor
        self.last_exception: Exception | None = None

        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=UPDATE_INTERVAL),
        )

    async def _async_update_data(self):
        """Fetch monitor list and control values from the HDMI Assistant Node."""
        base_url = f"http://{self.host}:{self.port}"
        try:
            # clear any previous error
            self.last_exception = None

            # 1) Discover monitors
            async with self.session.get(f"{base_url}/monitors") as resp:
                resp.raise_for_status()
                monitors = await resp.json()
            _LOGGER.info("Found monitors: %s", monitors)

            data = {
                "monitors": monitors,
                "controls": {ctrl: {} for ctrl in self.CONTROLS},
            }

            # 2) Probe each control on each monitor
            for mon in monitors:
                mid = mon["id"]
                for ctrl in self.CONTROLS:
                    url = f"{base_url}/monitors/{mid}/{ctrl}"
                    try:
                        async with self.session.get(url) as r2:
                            r2.raise_for_status()
                            val = (await r2.json()).get(ctrl)
                        data["controls"][ctrl][mid] = val
                        _LOGGER.info(
                            "Monitor %s supports %s: initial value %s",
                            mid, ctrl, val
                        )
                    except Exception as err:
                        _LOGGER.debug(
                            "Monitor %s does NOT support %s (%s)", mid, ctrl, err
                        )

            return data

        except Exception as err:
            _LOGGER.error("Failed fetching HDMI Assistant data: %s", err, exc_info=True)
            # store for connection-status sensor
            self.last_exception = err
            raise UpdateFailed(err)
