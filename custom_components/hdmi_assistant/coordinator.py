# File: custom_components/hdmi_assistant/coordinator.py
# Description: Python file fetching HDMI Assistant Node values and handling discovery.
# Author: Chuffnugget

import asyncio
import logging
from copy import deepcopy
from datetime import timedelta

import aiohttp
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN, UPDATE_INTERVAL

_LOGGER = logging.getLogger(__name__)


class HDMIDataUpdateCoordinator(DataUpdateCoordinator):
    """Coordinator that fetches and writes monitor settings, serialized."""

    CONTROLS = ["brightness", "contrast", "input_source"]

    def __init__(self, hass, host: str, port: int):
        self.host = host
        self.port = port
        self.session = aiohttp.ClientSession()
        self.last_exception: Exception | None = None

        # queue for write requests: tuples of (mon_id, control, value)
        self._write_queue: asyncio.Queue[tuple[int, str, int]] = asyncio.Queue()
        # lock to serialize all HTTP traffic (both reads & writes)
        self._write_lock = asyncio.Lock()

        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=UPDATE_INTERVAL),
        )

        # start background write worker
        hass.loop.create_task(self._write_worker())

    async def _write_worker(self):
        """Process queued writes in the order received, one at a time."""
        while True:
            mon_id, control, value = await self._write_queue.get()
            try:
                async with self._write_lock:  # ensure no reads overlap
                    url = f"http://{self.host}:{self.port}/monitors/{mon_id}/{control}"
                    payload = {control: value}
                    _LOGGER.debug("⏳ Write: %s → %s", url, payload)
                    async with self.session.post(url, json=payload) as resp:
                        resp.raise_for_status()
                    _LOGGER.info("✅ Write complete: monitor %s %s=%s", mon_id, control, value)
                    # short pause for DDC stability
                    await asyncio.sleep(0.05)
            except Exception as err:
                _LOGGER.error("⚠️ Write error on monitor %s %s=%s: %s", mon_id, control, value, err)
            finally:
                self._write_queue.task_done()

    async def _async_update_data(self):
        """Fetch monitor list and control values, preserving last known on failure."""
        base = f"http://{self.host}:{self.port}"
        try:
            self.last_exception = None

            # reuse previous data so failed reads don't clear old values
            old = deepcopy(self.data) if self.data else {}
            data = {
                "monitors": [],
                "controls": old.get("controls", {ctrl: {} for ctrl in self.CONTROLS}),
                "input_source_options": old.get("input_source_options", {}),
            }

            # serialize reads with the same lock as writes
            async with self._write_lock:
                # 1) get monitor list
                async with self.session.get(f"{base}/monitors") as resp:
                    resp.raise_for_status()
                    monitors = await resp.json()
                _LOGGER.info("Found monitors: %s", monitors)
                data["monitors"] = monitors

                # 2) for each monitor, fetch options & current values
                for mon in monitors:
                    mid = mon["id"]

                    # fetch friendly labels for input_source
                    try:
                        async with self.session.get(
                            f"{base}/monitors/{mid}/input_source_options"
                        ) as r_opts:
                            r_opts.raise_for_status()
                            opts = (await r_opts.json()).get("input_source_options", {})
                            data["input_source_options"][mid] = opts
                            _LOGGER.info("Monitor %s input_source options: %s", mid, opts)
                    except Exception as err:
                        _LOGGER.debug("Monitor %s input_source_options fetch failed: %s", mid, err)

                    # now fetch each control’s current value
                    for ctrl in self.CONTROLS:
                        try:
                            async with self.session.get(
                                f"{base}/monitors/{mid}/{ctrl}"
                            ) as r2:
                                r2.raise_for_status()
                                val = (await r2.json()).get(ctrl)
                            if val is not None:
                                data["controls"][ctrl][mid] = val
                                _LOGGER.info("Monitor %s supports %s: %s", mid, ctrl, val)
                            else:
                                _LOGGER.debug(
                                    "Monitor %s read %s returned null, keeping previous", mid, ctrl
                                )
                        except Exception as err:
                            _LOGGER.debug("Monitor %s does NOT support %s: %s", mid, ctrl, err)

            return data

        except Exception as err:
            _LOGGER.error("Failed fetching HDMI Assistant data: %s", err, exc_info=True)
            self.last_exception = err
            raise UpdateFailed(err)

    def enqueue_write(self, mon_id: int, control: str, value: int) -> None:
        """Queue a write to be executed by the background worker."""
        self._write_queue.put_nowait((mon_id, control, value))
