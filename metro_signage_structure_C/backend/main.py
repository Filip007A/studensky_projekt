import asyncio
import datetime
import json
import os
import pathlib
import random
import logging

import httpx
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from google.transit import gtfs_realtime_pb2

ROOT = pathlib.Path(__file__).resolve().parents[1]

app = FastAPI()
logging.basicConfig(level=logging.DEBUG, format="%(asctime)s %(levelname)s %(message)s")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

frontend_path = ROOT / "studentsk-signage-frontend" / "src"
if frontend_path.exists():
    app.mount("/static", StaticFiles(directory=str(frontend_path)), name="frontend")

# Shared state filled by background poller
LATEST_DEPARTURES = []
POLL_TASK = None

GTFS_URL = os.getenv("GTFS_RT_URL")  # e.g. "https://.../gtfs-rt.pb"
POLL_INTERVAL = int(os.getenv("GTFS_POLL_INTERVAL", "5"))  # seconds (use larger in prod)
# Optional headers as JSON string, e.g. export GTFS_RT_HEADERS='{"x-api-key":"XXX"}'
GTFS_HEADERS = None
if os.getenv("GTFS_RT_HEADERS"):
    try:
        GTFS_HEADERS = json.loads(os.getenv("GTFS_RT_HEADERS"))
    except Exception:
        logging.warning("Invalid GTFS_RT_HEADERS JSON, ignoring")


@app.get("/api/status")
async def status():
    return {"ok": True, "time": datetime.datetime.utcnow().isoformat()}


@app.get("/api/fallback")
async def fallback():
    data_file = ROOT / "data" / "stations.json"
    if data_file.exists():
        return json.loads(data_file.read_text(encoding="utf-8"))
    return {"departures": []}


@app.get("/api/latest")
async def api_latest():
    """Return the last polled GTFS departures (or empty list)."""
    return {"count": len(LATEST_DEPARTURES), "departures": LATEST_DEPARTURES}


async def fetch_gtfs_rt(url: str):
    """Download and parse GTFS-RT feed -> list[dict] or None on error.
    Supports http(s) URLs or local file paths / file:// URIs.
    """
    import os
    logging.debug("Fetching GTFS-RT from %s", url)
    if not url:
        logging.debug("No GTFS URL provided")
        return None

    try:
        content = None

        if url.startswith("file://"):
            path = url[7:]
            path = os.path.expanduser(path)
            if not os.path.exists(path):
                logging.error("Local GTFS file not found: %s", path)
                return None
            logging.debug("Reading GTFS-RT local file (file://): %s", path)
            with open(path, "rb") as fh:
                content = fh.read()
        elif url.lower().startswith("http://") or url.lower().startswith("https://"):
            async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
                r = await client.get(url, headers=GTFS_HEADERS)
                r.raise_for_status()
                content = r.content
        else:
            path = os.path.expanduser(url)
            if os.path.exists(path):
                logging.debug("Reading GTFS-RT local file: %s", path)
                with open(path, "rb") as fh:
                    content = fh.read()
            else:
                logging.error("GTFS_RT_URL does not look like HTTP(s) and file does not exist: %s", url)
                logging.debug("Not attempting HTTP fetch for non-HTTP value")
                return None

        feed = gtfs_realtime_pb2.FeedMessage()
        feed.ParseFromString(content)
        departures = []
        now_ts = int(datetime.datetime.utcnow().timestamp())
        for entity in feed.entity:
            if entity.HasField("trip_update"):
                tu = entity.trip_update
                # safe access to trip fields (some bindings raise on missing attributes)
                route_id = getattr(tu.trip, "route_id", "") or ""
                route_id = route_id[:10]
                trip_headsign = getattr(tu.trip, "trip_headsign", None)
                for stu in tu.stop_time_update:
                    if stu.HasField("arrival") and getattr(stu.arrival, "time", None):
                        arrival_ts = stu.arrival.time
                        in_min = max(0, int((arrival_ts - now_ts) / 60))
                        dest = trip_headsign or route_id or "?"
                        departures.append({"line": route_id or "?", "dest": dest, "in_min": in_min})
                        break
        departures = sorted(departures, key=lambda x: x["in_min"])[:50]
        logging.debug("Parsed %d departures", len(departures))
        return departures
    except Exception:
        logging.exception("GTFS fetch/parse failed")
        return None


async def gtfs_poller_loop():
    global LATEST_DEPARTURES
    if not GTFS_URL:
        logging.info("GTFS_RT_URL not set — poller disabled")
        return
    logging.info("Starting GTFS poller for %s (interval %ss)", GTFS_URL, POLL_INTERVAL)
    try:
        while True:
            deps = await fetch_gtfs_rt(GTFS_URL)
            if deps is not None:
                LATEST_DEPARTURES = deps
                logging.debug("Updated LATEST_DEPARTURES (%d items)", len(deps))
            await asyncio.sleep(POLL_INTERVAL)
    except asyncio.CancelledError:
        logging.info("GTFS poller cancelled")
        raise


@app.on_event("startup")
async def startup_event():
    global POLL_TASK
    if GTFS_URL:
        POLL_TASK = asyncio.create_task(gtfs_poller_loop())


@app.on_event("shutdown")
async def shutdown_event():
    global POLL_TASK
    if POLL_TASK:
        POLL_TASK.cancel()
        try:
            await POLL_TASK
        except asyncio.CancelledError:
            logging.debug("POLL_TASK cancelled during shutdown")
        except Exception:
            logging.exception("Error waiting for POLL_TASK")


@app.websocket("/ws/updates")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    try:
        base_lines = [
            {"line": "A", "dest": "Muzeum"},
            {"line": "B", "dest": "Florenc"},
            {"line": "C", "dest": "Hradčanská"},
            {"line": "D", "dest": "Hloubětín"},
        ]
        while True:
            now = datetime.datetime.utcnow().isoformat()
            departures = []
            # Prefer background-polled GTFS data
            if LATEST_DEPARTURES:
                departures = LATEST_DEPARTURES[:20]
            else:
                # fallback to simulated feed
                for entry in base_lines:
                    in_min = random.randint(1, 12)
                    departures.append({"line": entry["line"], "dest": entry["dest"], "in_min": in_min})
            payload = {"t": now, "departures": departures}
            await websocket.send_json(payload)
            await asyncio.sleep(5)
    except WebSocketDisconnect:
        return
    except Exception:
        try:
            await websocket.close()
        except Exception:
            pass