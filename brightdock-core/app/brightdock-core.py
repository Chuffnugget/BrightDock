#!/usr/bin/env python3
# File: brightdock-core.py
# Description: Python file for BrightDock Core with mDNS advertisement.
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
SERVICE_TYPE  = "_brightdock-core._tcp.local."
SERVICE_NAME  = "BrightDock Core"

# Validate config early
_config = {
    "HA_URL": HA_URL,
    "HA_TOKEN_set": bool(HA_TOKEN),
    "POLL_INTERVAL": POLL_INTERVAL,
}
logging.basicConfig(level=logging.INFO, format="%(message)s")
_LOGGER = logging.getLogger("brightdock_core")
_LOGGER.info("Starting BrightDock Core with config: %s", _config)

if not HA_URL or not HA_TOKEN:
    _LOGGER.error(
        "Configuration error: HA_URL and HA_TOKEN environment variables are required. "
        "Current config: %s", _config
    )
    sys.exit(1)

if not HA_URL.startswith(("http://", "https://")):
    _LOGGER.error(
        "Configuration error: HA_URL must start with http:// or https://. "
        "Current config: %s", _config
    )
    sys.exit(1)

HEADERS = {
    "Authorization": f"Bearer {HA_TOKEN}",
    "Content-Type":  "application/json",
}

# VCP codes we expose via HTTP
VCP_CODES = {
    "brightness":   "10",
    "contrast":     "12",
    "input_source": "60",
}

# ── FastAPI HTTP API ──────────────────────────────────────────────────────────

app = FastAPI(title="BrightDock Core")

class BrightnessPayload(BaseModel):
    brightness: int

class ContrastPayload(BaseModel):
    contrast: int

class InputPayload(BaseModel):
    input_source: int

@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Log every incoming HTTP request and its response code."""
    _LOGGER.info(f"HTTP {request.method} {request.url.path}")
    response = await call_next(request)
    _LOGGER.info(f"→ {response.status_code} {request.url.path}")
    return response

@app.get("/monitors")
async def api_list_monitors():
    """Return list of detected monitors."""
    return [
        {"id": idx, "model": mon["model"], "bus": mon["bus"]}
        for idx, mon in MONITORS.items()
    ]

@app.get("/monitors/{mon_id}/brightness")
async def api_get_brightness(mon_id: int):
    """Get brightness for the given monitor."""
    try:
        bus = MONITORS[mon_id]["bus"]
        val = await read_vcp(bus, VCP_CODES["brightness"])
        return {"brightness": val}
    except KeyError:
        raise HTTPException(status_code=404, detail="Monitor not found")

@app.post("/monitors/{mon_id}/brightness")
async def api_set_brightness(mon_id: int, payload: BrightnessPayload):
    """Set brightness for the given monitor."""
    try:
        bus = MONITORS[mon_id]["bus"]
    except KeyError:
        raise HTTPException(status_code=404, detail="Monitor not found")
    await write_vcp(bus, VCP_CODES["brightness"], payload.brightness)
    return {"status": "ok", "brightness": payload.brightness}

@app.get("/monitors/{mon_id}/contrast")
async def api_get_contrast(mon_id: int):
    """Get contrast for the given monitor."""
    try:
        bus = MONITORS[mon_id]["bus"]
        val = await read_vcp(bus, VCP_CODES["contrast"])
        return {"contrast": val}
    except KeyError:
        raise HTTPException(status_code=404, detail="Monitor not found")

@app.post("/monitors/{mon_id}/contrast")
async def api_set_contrast(mon_id: int, payload: ContrastPayload):
    """Set contrast for the given monitor."""
    try:
        bus = MONITORS[mon_id]["bus"]
    except KeyError:
        raise HTTPException(status_code=404, detail="Monitor not found")
    await write_vcp(bus, VCP_CODES["contrast"], payload.contrast)
    return {"status": "ok", "contrast": payload.contrast}

@app.get("/monitors/{mon_id}/input_source")
async def api_get_input(mon_id: int):
    """Get input source for the given monitor."""
    try:
        bus = MONITORS[mon_id]["bus"]
        val = await read_vcp(bus, VCP_CODES["input_source"])
        return {"input_source": val}
    except KeyError:
        raise HTTPException(status_code=404, detail="Monitor not found")

@app.post("/monitors/{mon_id}/input_source")
async def api_set_input(mon_id: int, payload: InputPayload):
    """Set input source for the given monitor."""
    try:
        bus = MONITORS[mon_id]["bus"]
    except KeyError:
        raise HTTPException(status_code=404, detail="Monitor not found")
    await write_vcp(bus, VCP_CODES["input_source"], payload.input_source)
    return {"status": "ok", "input_source": payload.input_source}

# ── Startup Banner + mDNS Advertisement ───────────────────────────────────────

def get_ip_address(ifname: str) -> str | None:
    """Return IPv4 address for an interface, or None."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        packed = struct.pack("256s", ifname[:15].encode())
        addr = fcntl.ioctl(sock.fileno(), 0x8915, packed)[20:24]
        return socket.inet_ntoa(addr)
    except OSError:
        return None

async def print_startup_info():
    """Print debug info and HA connectivity check."""
    _LOGGER.info("┌─────────────────────────────────────────────")
    _LOGGER.info("│ BrightDock Core Debug Info on Startup")
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
    """Run a ddcutil command asynchronously and return its stdout."""
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
    """Detect all DDC/CI-capable monitors via ddcutil."""
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
            current["model"] = line.split("Model:",1)[1].strip()
    if current:
        monitors.append(current)
    _LOGGER.info(f"Detected monitors: {monitors}")
    return monitors

async def get_capabilities(bus: str) -> list[dict]:
    """Fetch all VCP features for a given I²C bus."""
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
    """Read a single VCP feature value."""
    out = await run_ddc(f"ddcutil --bus {bus} getvcp {code}")
    m = re.search(r"current value\s*=\s*(\d+)", out)
    if m: return int(m.group(1))
    m = re.search(r"current value\s*=\s*0x([0-9A-Fa-f]+)", out)
    if m: return int(m.group(1), 16)
    return None

async def write_vcp(bus: str, code: str, val: int):
    """Write a single VCP feature value."""
    await run_ddc(f"ddcutil --bus {bus} setvcp {code} {val}")
    _LOGGER.info(f"🔧 setvcp bus={bus} code={code} → {val}")

# ── Home Assistant Registration ──────────────────────────────────────────────

async def post_state(entity: str, state, attrs: dict | None = None):
    """POST the current state and attributes to Home Assistant."""
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
    """Detect monitors, fetch features, and register entities in HA."""
    raw = await detect_monitors()
    for idx, mon in enumerate(raw):
        bus   = mon["bus"]
        model = mon.get("model", f"monitor_{idx}")
        feats = await get_capabilities(bus)
        MONITORS[idx] = {"bus": bus, "model": model, "features": feats}
        for feat in feats:
            code = feat["code"]
            name = re.sub(r"\W+", "_", feat["name"].lower()).strip("_")
            base = f"brightdock_{idx}_{name}_{code}"
            val  = await read_vcp(bus, code)
            if val is None:
                _LOGGER.warning(f"Feature {code} ({feat['name']}) unreadable; skipping")
                continue
            if feat["values"]:
                options = list(feat["values"].values())
                ent     = f"input_select.{base}"
                attrs   = {"friendly_name": f"{model} {feat['name']}", "options": options}
                state   = feat["values"].get(f"{val:02x}", options[0])
            else:
                if name in ("brightness", "contrast"):
                    ent   = f"number.{base}"
                    attrs = {
                        "friendly_name": f"{model} {feat['name']}",
                        "min": 0, "max": 100, "step": 1, "unit_of_measurement": "%"
                    }
                    state = val
                else:
                    ent   = f"sensor.{base}"
                    attrs = {"friendly_name": f"{model} {feat['name']}"}
                    state = val
            await post_state(ent, state, attrs)
    _LOGGER.info("Initialization and HA registration complete.")

async def ws_listener():
    """Listen for state_changed events from HA and push to monitor."""
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
                    name = re.sub(r"\W+", "_", feat["name"].lower()).strip("_")
                    base = f"brightdock_{idx}_{name}_{code}"
                    if feat["values"] and ent == f"input_select.{base}":
                        rev = {v: k for k, v in feat["values"].items()}
                        he  = rev.get(new)
                        if he:
                            _LOGGER.info(f"WS change: {ent} → {new} ({he})")
                            await write_vcp(bus, code, int(he, 16))
                    elif not feat["values"] and ent == f"number.{base}":
                        _LOGGER.info(f"WS change: {ent} → {new}")
                        await write_vcp(bus, code, int(new))
    await session.close()

async def poll_loop():
    """Poll all controls periodically to update HA states."""
    while True:
        for idx, mon in MONITORS.items():
            bus = mon["bus"]
            for feat in mon["features"]:
                code = feat["code"]
                name = re.sub(r"\W+", "_", feat["name"].lower()).strip("_")
                base = f"brightdock_{idx}_{name}_{code}"
                val  = await read_vcp(bus, code)
                if val is None:
                    continue
                if feat["values"]:
                    ent   = f"input_select.{base}"
                    state = feat["values"].get(f"{val:02x}")
                elif name in ("brightness", "contrast"):
                    ent   = f"number.{base}"
                    state = val
                else:
                    ent   = f"sensor.{base}"
                    state = val
                await post_state(ent, state)
        await asyncio.sleep(POLL_INTERVAL)

async def main():
    """Main entrypoint: banner, mDNS, init, HTTP, WS, poll, teardown."""
    global _zc, _info

    # 1) debug banner
    await print_startup_info()

    # 2) advertise via mDNS
    hostname = socket.gethostname()
    ip_addr  = get_ip_address("eth0") or get_ip_address("wlan0") or "127.0.0.1"
    port     = 8000
    props    = {"version": "0.0.5", "application": SERVICE_NAME}
    info     = ServiceInfo(
        SERVICE_TYPE,
        f"{hostname}.{SERVICE_TYPE}",
        addresses=[socket.inet_aton(ip_addr)],
        port=port,
        properties=props,
        server=f"{hostname}.local."
    )
    _zc = Zeroconf()
    _zc.register_service(info)
    _LOGGER.info(f"Registered mDNS service {SERVICE_TYPE} on {ip_addr}:{port}")

    # 3) detect & HA register
    await init_monitors_and_register()

    # 4) run HTTP, WS, and poll loop in parallel
    _LOGGER.info("Launching HTTP server, WS listener, and poll loop")
    config    = uvicorn.Config(app, host="0.0.0.0", port=port, log_level="info")
    server    = uvicorn.Server(config)
    http_task = asyncio.create_task(server.serve())
    ws_task   = asyncio.create_task(ws_listener())
    poll_task = asyncio.create_task(poll_loop())

    await asyncio.wait([http_task, ws_task, poll_task], return_when=asyncio.FIRST_COMPLETED)

    # 5) cleanup mDNS
    _LOGGER.info("Unregistering mDNS service and shutting down…")
    _zc.unregister_service(info)
    _zc.close()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        _LOGGER.info("Shutting down…")
