# File: brightdock-core.py
# Description: Python file for BrightDock Core. 
# Author: Chuffnugget

FROM python:3.11-slim

# Install ddcutil + i2c-tools and build tools
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      ddcutil \
      i2c-tools \
      libusb-1.0-0 \
      build-essential \
      python3-dev \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -U pip \
 && pip install --no-cache-dir -r requirements.txt

COPY app ./app

# No HTTP port to expose—this script just talks to HA
ENTRYPOINT ["python3", "app/displayServer_async.py"]

chuffnugget@RAR-P1:~/servers/ddcci-server $ ^C
chuffnugget@RAR-P1:~/servers/ddcci-server $ ls
caapp  backups  compose.yaml  Dockerfile  requirements.txt
chuffnugget@RAR-P1:~/servers/ddcci-server $ cat compose.yaml
services:
  ddcci-server:
    build: .
    network_mode: host
    privileged: true
    volumes:
      - /dev:/dev
    environment:
      HA_URL: "http://192.168.0.3:8123"
      HA_TOKEN: "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiIxMzAwNjI3OTM2MDI0NTFjYTc0NTFhYTQ0NjVhOWY5OCIsImlhdCI6MTc0OTQxMjA0NywiZXhwIjoyMDY0NzcyMDQ3fQ.hC6YFxx502a9JVs-p7jKSdhaqJtjAszo5vlsuI3v524"
    ports:
      - "8000:8000"
    restart: unless-stopped

chuffnugget@RAR-P1:~/servers/ddcci-server $ ^C
chuffnugget@RAR-P1:~/servers/ddcci-server $ ▒^C
chuffnugget@RAR-P1:~/servers/ddcci-server $ ls
app  backups  compose.yaml  Dockerfile  requirements.txt
chuffnugget@RAR-P1:~/servers/ddcci-server $ cd app
chuffnugget@RAR-P1:~/servers/ddcci-server/app $ ls
displayServer_async.py
chuffnugget@RAR-P1:~/servers/ddcci-server/app $ cat displayServer_async.py
#!/usr/bin/env python3
import os
import re
import sys
import json
import glob
import asyncio
import logging
import platform
import socket
import struct
import fcntl
import subprocess

import aiohttp
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel
import uvicorn

# ── Configuration ─────────────────────────────────────────────────────────────

HA_URL = os.getenv("HA_URL")
HA_TOKEN = os.getenv("HA_TOKEN")
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "30"))

if not HA_URL or not HA_TOKEN:
    print("Error: HA_URL and HA_TOKEN environment variables are required", file=sys.stderr)
    sys.exit(1)

HEADERS = {
    "Authorization": f"Bearer {HA_TOKEN}",
    "Content-Type": "application/json",
}

_LOGGER = logging.getLogger("ddcci_async")
logging.basicConfig(level=logging.INFO, format="%(message)s")

# VCP codes we expose via HTTP
VCP_CODES = {
    "brightness":    "10",
    "contrast":      "12",
    "input_source":  "60",
}

# ── FastAPI HTTP API ──────────────────────────────────────────────────────────

app = FastAPI(title="DDC/CI Server")

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
    """Return list of monitors as [{'id':..., 'model':..., 'bus':...}]"""
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
        raise HTTPException(404, "Monitor not found")

@app.post("/monitors/{mon_id}/brightness")
async def api_set_brightness(mon_id: int, payload: BrightnessPayload):
    try:
        bus = MONITORS[mon_id]["bus"]
    except KeyError:
        raise HTTPException(404, "Monitor not found")
    await write_vcp(bus, VCP_CODES["brightness"], payload.brightness)
    return {"status": "ok", "brightness": payload.brightness}

@app.get("/monitors/{mon_id}/contrast")
async def api_get_contrast(mon_id: int):
    try:
        bus = MONITORS[mon_id]["bus"]
        val = await read_vcp(bus, VCP_CODES["contrast"])
        return {"contrast": val}
    except KeyError:
        raise HTTPException(404, "Monitor not found")

@app.post("/monitors/{mon_id}/contrast")
async def api_set_contrast(mon_id: int, payload: ContrastPayload):
    try:
        bus = MONITORS[mon_id]["bus"]
    except KeyError:
        raise HTTPException(404, "Monitor not found")
    await write_vcp(bus, VCP_CODES["contrast"], payload.contrast)
    return {"status": "ok", "contrast": payload.contrast}

@app.get("/monitors/{mon_id}/input_source")
async def api_get_input(mon_id: int):
    try:
        bus = MONITORS[mon_id]["bus"]
        val = await read_vcp(bus, VCP_CODES["input_source"])
        return {"input_source": val}
    except KeyError:
        raise HTTPException(404, "Monitor not found")

@app.post("/monitors/{mon_id}/input_source")
async def api_set_input(mon_id: int, payload: InputPayload):
    try:
        bus = MONITORS[mon_id]["bus"]
    except KeyError:
        raise HTTPException(404, "Monitor not found")
    await write_vcp(bus, VCP_CODES["input_source"], payload.input_source)
    return {"status": "ok", "input_source": payload.input_source}

# ── Startup Banner ─────────────────────────────────────────────────────────────

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
    _LOGGER.info("│ DDC/CI Server Debug Info on Startup")
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
            current["model"] = line.split("Model:",1)[1].strip()
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
    out = await run_ddc(f"ddcutil --bus {bus} getvcp {code}")
    m = re.search(r"current value\s*=\s*(\d+)", out)
    if m: return int(m.group(1))
    m = re.search(r"current value\s*=\s*0x([0-9A-Fa-f]+)", out)
    if m: return int(m.group(1), 16)
    return None

async def write_vcp(bus: str, code: str, val: int):
    await run_ddc(f"ddcutil --bus {bus} setvcp {code} {val}")
    _LOGGER.info(f"🔧 setvcp bus={bus} code={code} → {val}")

# ── Home Assistant Registration ──────────────────────────────────────────────

async def post_state(entity: str, state, attrs: dict = None):
    url = f"{HA_URL}/api/states/{entity}"
    body = {"state": str(state)}
    if attrs:
        body["attributes"] = attrs
    async with aiohttp.ClientSession() as sess:
        async with sess.post(url, headers=HEADERS, json=body) as resp:
            if resp.status not in (200,201):
                text = await resp.text()
                _LOGGER.error(f"POST {url} → {resp.status}: {text}")
            else:
                _LOGGER.info(f"Registered {entity} = {state}")

# ── Main Setup & Tasks ────────────────────────────────────────────────────────

MONITORS: dict[int, dict] = {}

async def init_monitors_and_register():
    raw = await detect_monitors()
    for idx, mon in enumerate(raw):
        bus = mon["bus"]
        model = mon.get("model", f"monitor_{idx}")
        feats = await get_capabilities(bus)
        MONITORS[idx] = {"bus": bus, "model": model, "features": feats}
        for feat in feats:
            code = feat["code"]
            name = re.sub(r"\W+", "_", feat["name"].lower()).strip("_")
            base = f"ddcci_{idx}_{name}_{code}"
            val = await read_vcp(bus, code)
            if val is None:
                _LOGGER.warning(f"Feature {code} ({feat['name']}) unreadable; skipping")
                continue

            if feat["values"]:
                options = list(feat["values"].values())
                ent = f"input_select.{base}"
                attrs = {"friendly_name": f"{model} {feat['name']}", "options": options}
                state = feat["values"].get(f"{val:02x}", options[0])
            else:
                if name in ("brightness", "contrast"):
                    ent = f"number.{base}"
                    attrs = {
                        "friendly_name": f"{model} {feat['name']}",
                        "min": 0, "max": 100, "step": 1, "unit_of_measurement": "%"
                    }
                    state = val
                else:
                    ent = f"sensor.{base}"
                    attrs = {"friendly_name": f"{model} {feat['name']}"}
                    state = val

            await post_state(ent, state, attrs)

    _LOGGER.info("Initialization & HA registration complete.")

async def ws_listener():
    url = HA_URL.replace("http", "ws") + "/api/websocket"
    _LOGGER.info(f"Connecting to HA websocket at {url}")
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

        _LOGGER.info("WebSocket authenticated. Listening for state changes…")
        async for msg in ws:
            if msg.type != aiohttp.WSMsgType.TEXT:
                continue
            j = msg.json()
            if j.get("event", {}).get("event_type") != "state_changed":
                continue
            data = j["event"]["data"]
            ent = data["entity_id"]
            new = data["new_state"]["state"]
            for idx, mon in MONITORS.items():
                bus = mon["bus"]
                for feat in mon["features"]:
                    code = feat["code"]
                    name = re.sub(r"\W+", "_", feat["name"].lower()).strip("_")
                    base = f"ddcci_{idx}_{name}_{code}"
                    if feat["values"] and ent == f"input_select.{base}":
                        rev = {v: k for k, v in feat["values"].items()}
                        he = rev.get(new)
                        if he:
                            _LOGGER.info(f"WS change: {ent} → {new} ({he})")
                            await write_vcp(bus, code, int(he, 16))
                    elif not feat["values"] and ent == f"number.{base}":
                        _LOGGER.info(f"WS change: {ent} → {new}")
                        await write_vcp(bus, code, int(new))
    await session.close()

async def poll_loop():
    while True:
        for idx, mon in MONITORS.items():
            bus = mon["bus"]
            for feat in mon["features"]:
                code = feat["code"]
                name = re.sub(r"\W+", "_", feat["name"].lower()).strip("_")
                base = f"ddcci_{idx}_{name}_{code}"
                val = await read_vcp(bus, code)
                if val is None:
                    continue
                if feat["values"]:
                    ent = f"input_select.{base}"
                    state = feat["values"].get(f"{val:02x}")
                elif name in ("brightness", "contrast"):
                    ent = f"number.{base}"
                    state = val
                else:
                    ent = f"sensor.{base}"
                    state = val
                await post_state(ent, state)
        await asyncio.sleep(POLL_INTERVAL)

async def main():
    # 1) banner
    await print_startup_info()

    # 2) detect & HA-register
    await init_monitors_and_register()

    # 3) run HTTP + WS + poll in parallel
    _LOGGER.info("Starting HTTP server on port 8000")
    config = uvicorn.Config(app, host="0.0.0.0", port=8000, log_level="info")
    server = uvicorn.Server(config)
    http_task = asyncio.create_task(server.serve())

    ws_task   = asyncio.create_task(ws_listener())
    poll_task = asyncio.create_task(poll_loop())

    await asyncio.wait(
        [http_task, ws_task, poll_task],
        return_when=asyncio.FIRST_COMPLETED
    )

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        _LOGGER.info("Shutting down…")
