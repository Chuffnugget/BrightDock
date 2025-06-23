#!/usr/bin/env python3
# File: hdmi-assistant-node.py
# Description: Python file for HDMI Assistant Node with mDNS advertisement.
# Author: Chuffnugget

import os
import re
import sys
import glob
import asyncio
import logging
import platform
import socket
import struct
import fcntl

import aiohttp
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel
import uvicorn
from zeroconf import Zeroconf, ServiceInfo

# ── Configuration ─────────────────────────────────────────────────────────────

HA_URL        = os.getenv("HA_URL")
HA_TOKEN      = os.getenv("HA_TOKEN")
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "30"))
SERVICE_TYPE  = "_hdmi-assistant._tcp.local."
SERVICE_NAME  = "HDMI Assistant Node"

if not HA_URL or not HA_TOKEN:
    print("Error: HA_URL and HA_TOKEN environment variables are required", file=sys.stderr)
    sys.exit(1)

HEADERS = {
    "Authorization": f"Bearer {HA_TOKEN}",
    "Content-Type":  "application/json",
}

_LOGGER = logging.getLogger("hdmiassistant_node")
logging.basicConfig(level=logging.INFO, format="%(message)s")

# Only these three codes will be exposed
VCP_CODES = {
    "brightness":   "10",
    "contrast":     "12",
    "input_source": "60",
}

# ── FastAPI HTTP API ──────────────────────────────────────────────────────────

app = FastAPI(title="HDMI Assistant Node")


class BrightnessPayload(BaseModel):
    brightness: int


class ContrastPayload(BaseModel):
    contrast: int


class InputPayload(BaseModel):
    input_source: int


@app.middleware("http")
async def log_requests(request: Request, call_next):
    _LOGGER.info(f"HTTP {request.method} {request.url.path}")
    response = await call_next(request)
    _LOGGER.info(f"→ {response.status_code} {request.url.path}")
    return response


@app.get("/monitors")
async def api_list_monitors():
    return [
        {"id": idx, "model": mon["model"], "bus": mon["bus"]}
        for idx, mon in MONITORS.items()
    ]


@app.get("/monitors/{mon_id}/brightness")
async def api_get_brightness(mon_id: int):
    try:
        bus = MONITORS[mon_id]["bus"]
        val = await read_vcp(bus, VCP_CODES["brightness"])
        return {"brightness": val}
    except KeyError:
        raise HTTPException(status_code=404, detail="Monitor not found")


@app.post("/monitors/{mon_id}/brightness")
async def api_set_brightness(mon_id: int, payload: BrightnessPayload):
    try:
        bus = MONITORS[mon_id]["bus"]
    except KeyError:
        raise HTTPException(status_code=404, detail="Monitor not found")
    await write_vcp(bus, VCP_CODES["brightness"], payload.brightness)
    return {"status": "ok", "brightness": payload.brightness}


@app.get("/monitors/{mon_id}/contrast")
async def api_get_contrast(mon_id: int):
    try:
        bus = MONITORS[mon_id]["bus"]
        val = await read_vcp(bus, VCP_CODES["contrast"])
        return {"contrast": val}
    except KeyError:
        raise HTTPException(status_code=404, detail="Monitor not found")


@app.post("/monitors/{mon_id}/contrast")
async def api_set_contrast(mon_id: int, payload: ContrastPayload):
    try:
        bus = MONITORS[mon_id]["bus"]
    except KeyError:
        raise HTTPException(status_code=404, detail="Monitor not found")
    await write_vcp(bus, VCP_CODES["contrast"], payload.contrast)
    return {"status": "ok", "contrast": payload.contrast}


@app.get("/monitors/{mon_id}/input_source")
async def api_get_input(mon_id: int):
    try:
        bus = MONITORS[mon_id]["bus"]
        val = await read_vcp(bus, VCP_CODES["input_source"])
        return {"input_source": val}
    except KeyError:
        raise HTTPException(status_code=404, detail="Monitor not found")


@app.post("/monitors/{mon_id}/input_source")
async def api_set_input(mon_id: int, payload: InputPayload):
    try:
        bus = MONITORS[mon_id]["bus"]
    except KeyError:
        raise HTTPException(status_code=404, detail="Monitor not found")
    await write_vcp(bus, VCP_CODES["input_source"], payload.input_source)
    return {"status": "ok", "input_source": payload.input_source}


@app.get("/monitors/{mon_id}/input_source_options")
async def api_input_options(mon_id: int):
    try:
        feats = MONITORS[mon_id]["features"]
    except KeyError:
        raise HTTPException(status_code=404, detail="Monitor not found")

    code = VCP_CODES["input_source"]
    for feat in feats:
        if feat["code"] == code and feat.get("values"):
            _LOGGER.info(
                f"Monitor {mon_id} input options (raw→friendly): {feat['values']}"
            )
            return {"input_source_options": feat["values"]}
    return {"input_source_options": {}}


# ── Startup Banner, mDNS, etc. ────────────────────────────────────────────────

def get_ip_address(ifname: str) -> str | None:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        packed = struct.pack("256s", ifname[:15].encode())
        addr = fcntl.ioctl(sock.fileno(), 0x8915, packed)[20:24]
        return socket.inet_ntoa(addr)
    except OSError:
        return None


async def print_startup_info():
    _LOGGER.info("┌─────────────────────────────────────────────")
    _LOGGER.info("│ HDMI Assistant Node Debug Info on Startup")
    _LOGGER.info("├─────────────────────────────────────────────")
    _LOGGER.info(f"│ Python:    {platform.python_version()} ({sys.executable})")
    _LOGGER.info(f"│ Platform:  {platform.system()} {platform.release()}")
    _LOGGER.info(f"│ CWD:       {os.getcwd()}")
    _LOGGER.info("├─────────────────────────────────────────────")
    _LOGGER.info("│ Network interfaces:")
    for path in glob.glob("/sys/class/net/*"):
        ifname = os.path.basename(path)
        if ifname == "lo":
            continue
        ip = get_ip_address(ifname) or "no IPv4"
        typ = "wireless" if os.path.isdir(f"/sys/class/net/{ifname}/wireless") else "ethernet"
        _LOGGER.info(f"│   • {ifname:10s} [{typ:8s}] → {ip}")
    _LOGGER.info("├─────────────────────────────────────────────")
    try:
        async with aiohttp.ClientSession() as sess:
            async with sess.get(f"{HA_URL.rstrip('/')}/api/", headers=HEADERS, timeout=5) as resp:
                _LOGGER.info(f"│ HA URL:    {HA_URL} → {resp.status} {resp.reason}")
    except Exception as e:
        _LOGGER.warning(f"│ HA check failed: {e}")
    _LOGGER.info("└─────────────────────────────────────────────")


# ── DDC/CI via ddcutil ────────────────────────────────────────────────────────

async def run_ddc(cmd: str) -> str:
    _LOGGER.debug(f"▶️  CMD: {cmd}")
    proc = await asyncio.create_subprocess_shell(
        cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    out, err = await proc.communicate()
    stdout = out.decode().strip()
    stderr = err.decode().strip()
    if stderr:
        _LOGGER.warning(f"⚠️  STDERR: {stderr}")
    _LOGGER.debug(f"🔹 OUTPUT: {stdout!r}")
    return stdout


async def detect_monitors() -> list[dict]:
    text = await run_ddc("ddcutil detect")
    monitors = []
    current = {}
    for line in text.splitlines():
        if line.startswith("Display"):
            if current:
                monitors.append(current)
            current = {}
        elif "I2C bus:" in line:
            m = re.search(r"/dev/i2c-(\d+)", line)
            if m:
                current["bus"] = m.group(1)
        elif "Model:" in line:
            current["model"] = line.split("Model:", 1)[1].strip()
    if current:
        monitors.append(current)
    _LOGGER.info(f"Detected monitors: {monitors}")
    return monitors


async def get_capabilities(bus: str) -> list[dict]:
    text = await run_ddc(f"ddcutil --bus {bus} capabilities")
    feats = []
    current = None
    for line in text.splitlines():
        m = re.match(r"\s*Feature:\s*([0-9A-Fa-f]+)\s*\((.+?)\)", line)
        if m:
            current = {"code": m.group(1), "name": m.group(2), "values": None}
            feats.append(current)
        elif current and "Values:" in line:
            current["values"] = {}
        elif current and current["values"] is not None:
            m2 = re.match(r"\s*([0-9A-Fa-f]+):\s*(.+)", line)
            if m2:
                current["values"][m2.group(1).lower()] = m2.group(2)
    _LOGGER.info(f"Capabilities on bus {bus}: {len(feats)} features")
    return feats


async def read_vcp(bus: str, code: str) -> int | None:
    try:
        out = await run_ddc(f"ddcutil --bus {bus} getvcp {code}")
    except Exception as e:
        _LOGGER.error(f"Failed to read VCP {code} on bus {bus}: {e}")
        return None
    m = re.search(r"current value\s*=\s*(\d+)", out)
    if m:
        return int(m.group(1))
    m = re.search(r"current value\s*=\s*0x([0-9A-Fa-f]+)", out)
    if m:
        return int(m.group(1), 16)
    return None


async def write_vcp(bus: str, code: str, val: int):
    try:
        await run_ddc(f"ddcutil --bus {bus} setvcp {code} {val}")
    except Exception as e:
        _LOGGER.error(f"Failed to write VCP {code}={val} on bus {bus}: {e}")
    else:
        _LOGGER.info(f"🔧 setvcp bus={bus} code={code} → {val}")


# ── Home Assistant Registration ──────────────────────────────────────────────

async def post_state(entity: str, state, attrs: dict | None = None):
    url = f"{HA_URL}/api/states/{entity}"
    body = {"state": str(state)}
    if attrs:
        body["attributes"] = attrs
    async with aiohttp.ClientSession() as sess:
        async with sess.post(url, headers=HEADERS, json=body) as resp:
            if resp.status not in (200, 201):
                text = await resp.text()
                _LOGGER.error(f"POST {url} → {resp.status}: {text}")
            else:
                _LOGGER.info(f"Registered {entity} = {state}")


# ── Main Setup & Tasks ────────────────────────────────────────────────────────

MONITORS: dict[int, dict] = {}
_zc: Zeroconf | None     = None
_info: ServiceInfo | None = None


async def init_monitors_and_register():
    """Detect monitors and register only brightness, contrast & input_source."""
    raw = await detect_monitors()
    for idx, mon in enumerate(raw):
        bus   = mon["bus"]
        model = mon.get("model", f"monitor_{idx}")
        feats = await get_capabilities(bus)
        MONITORS[idx] = {"bus": bus, "model": model, "features": feats}

        for feat in feats:
            code = feat["code"]
            # only register our three codes
            if code not in VCP_CODES.values():
                continue

            # read current
            val = await read_vcp(bus, code)
            if val is None:
                _LOGGER.warning(f"Feature {code} ({feat['name']}) unreadable; skipping")
                continue

            # brightness / contrast
            if code in (VCP_CODES["brightness"], VCP_CODES["contrast"]):
                ent   = f"number.hdmiassistant_node_{idx}_{feat['name'].lower().replace(' ','_')}_{code}"
                attrs = {
                    "friendly_name": f"{model} {feat['name']}",
                    "min": 0, "max": 100, "step": 1, "unit_of_measurement": "%"
                }
                await post_state(ent, val, attrs)
                continue

            # input_source
            if code == VCP_CODES["input_source"] and feat.get("values"):
                options = list(feat["values"].values())
                ent     = f"input_select.hdmiassistant_node_{idx}_{feat['name'].lower().replace(' ','_')}_{code}"
                attrs   = {"friendly_name": f"{model} {feat['name']}", "options": options}
                # lookup human label for current
                state   = feat["values"].get(f"{val:02x}", options[0])
                await post_state(ent, state, attrs)
                continue

    _LOGGER.info("Initialization and HA registration complete.")


async def ws_listener():
    url = HA_URL.replace("http", "ws") + "/api/websocket"
    _LOGGER.info(f"WS listener connecting to {url}")
    session = aiohttp.ClientSession()
    async with session.ws_connect(url, headers=HEADERS) as ws:
        init = await ws.receive_json()
        if init.get("type") != "auth_required":
            _LOGGER.error(f"Unexpected WS init: {init}")
            await session.close()
            return

        await ws.send_json({"type": "auth", "access_token": HA_TOKEN})
        resp = await ws.receive_json()
        if resp.get("type") != "auth_ok":
            _LOGGER.error(f"WebSocket auth failed: {resp}")
            await session.close()
            return

        _LOGGER.info("WebSocket authenticated; listening for state_changed…")
        async for msg in ws:
            if msg.type != aiohttp.WSMsgType.TEXT:
                continue
            j = msg.json()
            if j.get("event", {}).get("event_type") != "state_changed":
                continue
            data = j["event"]["data"]
            ent  = data["entity_id"]
            new  = data["new_state"]["state"]
            for idx, mon in MONITORS.items():
                bus = mon["bus"]
                for feat in mon["features"]:
                    code = feat["code"]
                    # same filtering
                    if code not in VCP_CODES.values():
                        continue
                    name = feat["name"].lower().replace(" ", "_")
                    base = f"hdmiassistant_node_{idx}_{name}_{code}"

                    # handle select
                    if code == VCP_CODES["input_source"] and ent == f"input_select.{base}":
                        rev = {v: k for k, v in feat["values"].items()}
                        he  = rev.get(new)
                        if he:
                            _LOGGER.info(f"WS change: {ent} → {new} ({he})")
                            await write_vcp(bus, code, int(he, 16))

                    # handle numbers
                    if code in (VCP_CODES["brightness"], VCP_CODES["contrast"]) and ent == f"number.{base}":
                        _LOGGER.info(f"WS change: {ent} → {new}")
                        await write_vcp(bus, code, int(new))

    await session.close()


async def poll_loop():
    while True:
        for idx, mon in MONITORS.items():
            bus = mon["bus"]
            for feat in mon["features"]:
                code = feat["code"]
                if code not in VCP_CODES.values():
                    continue
                val = await read_vcp(bus, code)
                if val is None:
                    continue
                name = feat["name"].lower().replace(" ", "_")
                base = f"hdmiassistant_node_{idx}_{name}_{code}"

                if code in (VCP_CODES["brightness"], VCP_CODES["contrast"]):
                    ent, state = f"number.{base}", val
                else:
                    ent, state = f"input_select.{base}", feat["values"].get(f"{val:02x}")

                await post_state(ent, state)
        await asyncio.sleep(POLL_INTERVAL)


async def main():
    global _zc, _info
    await print_startup_info()

    hostname = socket.gethostname()
    ip_addr  = get_ip_address("eth0") or get_ip_address("wlan0") or "127.0.0.1"
    port     = 8000
    props    = {"version": SERVICE_NAME}
    info     = ServiceInfo(
        SERVICE_TYPE,
        f"{hostname}.{SERVICE_TYPE}",
        addresses=[socket.inet_aton(ip_addr)],
        port=port,
        properties=props,
        server=f"{hostname}.local."
    )
    _zc = Zeroconf()
    await asyncio.to_thread(_zc.register_service, info)
    _LOGGER.info(f"Registered mDNS service on {ip_addr}:{port}")

    await init_monitors_and_register()

    config    = uvicorn.Config(app, host="0.0.0.0", port=port, log_level="info")
    server    = uvicorn.Server(config)
    http_task = asyncio.create_task(server.serve())
    ws_task   = asyncio.create_task(ws_listener())
    poll_task = asyncio.create_task(poll_loop())

    await asyncio.wait(
        [http_task, ws_task, poll_task],
        return_when=asyncio.FIRST_COMPLETED
    )

    await asyncio.to_thread(_zc.unregister_service, info)
    _zc.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        _LOGGER.info("Shutting down…")
