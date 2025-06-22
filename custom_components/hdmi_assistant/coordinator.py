# File: coordinator.py
import logging
from datetime import timedelta

import aiohttp
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN, UPDATE_INTERVAL

_LOGGER = logging.getLogger(__name__)

class HDMIDataUpdateCoordinator(DataUpdateCoordinator):
    CONTROLS = ["brightness", "contrast", "input_source"]

    def __init__(self, hass, host: str, port: int):
        self.host = host
        self.port = port
        self.session = aiohttp.ClientSession()
        self.last_exception: Exception | None = None

        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=UPDATE_INTERVAL),
        )

    async def _async_update_data(self):
        base = f"http://{self.host}:{self.port}"
        try:
            self.last_exception = None

            # 1) get monitor list
            async with self.session.get(f"{base}/monitors") as resp:
                resp.raise_for_status()
                monitors = await resp.json()
            _LOGGER.info("Found monitors: %s", monitors)

            data = {
                "monitors": monitors,
                "controls": {ctrl: {} for ctrl in self.CONTROLS},
                "input_source_options": {},    # ← new
            }

            # 2) for each monitor, fetch options & current values
            for mon in monitors:
                mid = mon["id"]

                # fetch friendly labels for input_source
                try:
                    async with self.session.get(f"{base}/monitors/{mid}/input_source_options") as r_opts:
                        r_opts.raise_for_status()
                        opts = (await r_opts.json()).get("input_source_options", {})
                        data["input_source_options"][mid] = opts
                        _LOGGER.info("Monitor %s input_source options: %s", mid, opts)
                except Exception as err:
                    _LOGGER.debug(
                        "Monitor %s input_source_options fetch failed: %s", mid, err
                    )

                # now fetch each control’s current value
                for ctrl in self.CONTROLS:
                    try:
                        async with self.session.get(f"{base}/monitors/{mid}/{ctrl}") as r2:
                            r2.raise_for_status()
                            val = (await r2.json()).get(ctrl)
                        data["controls"][ctrl][mid] = val
                        _LOGGER.info("Monitor %s supports %s: %s", mid, ctrl, val)
                    except Exception as err:
                        _LOGGER.debug(
                            "Monitor %s does NOT support %s: %s", mid, ctrl, err
                        )

            return data

        except Exception as err:
            _LOGGER.error("Failed fetching HDMI Assistant data: %s", err, exc_info=True)
            self.last_exception = err
            raise UpdateFailed(err)
