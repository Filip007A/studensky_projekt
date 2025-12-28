"""
Backend for Metro A signage (FastAPI)

Endpoints:
- WebSocket: /ws/updates  -> pushes {"t": "...", "departures": [...], "online": bool}
- REST:
  - GET /api/status
  - GET /api/latest
  - GET /api/fallback

Data source:
- Golemio PID departureboards (filters to Metro line A only)

Env vars:
- GOLEMIO_API_KEY (required for live data)
- GOLEMIO_STOP_NAMES="Muzeum" or "Můstek,Muzeum"
- REFRESH_SECONDS=10
- WS_PUSH_SECONDS=5
- OFFLINE_AFTER_SECONDS=60
- GOLEMIO_LIMIT=12
- GOLEMIO_MINUTES_AFTER=99
- GOLEMIO_TZ="Europe/Prague"

Run:
  pip install -r backend/requirements.txt
  export GOLEMIO_API_KEY="..."
  export GOLEMIO_STOP_NAMES="Muzeum"
  uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
"""
from __future__ import annotations

import asyncio
import datetime as dt
import json
import logging
import os
import pathlib
from typing import Any, Dict, List, Optional

import httpx
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

LOG = logging.getLogger("signage")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

ROOT = pathlib.Path(__file__).resolve().parents[1]
STATIC_DIR = ROOT / "frontend"

GOLEMIO_URL = "https://api.golemio.cz/v2/pid/departureboards/"
METRO_LINE = "A"

REFRESH_SECONDS = int(os.getenv("REFRESH_SECONDS", "10"))
WS_PUSH_SECONDS = int(os.getenv("WS_PUSH_SECONDS", "5"))
OFFLINE_AFTER_SECONDS = int(os.getenv("OFFLINE_AFTER_SECONDS", "60"))

GOLEMIO_LIMIT = int(os.getenv("GOLEMIO_LIMIT", "12"))
GOLEMIO_MINUTES_AFTER = int(os.getenv("GOLEMIO_MINUTES_AFTER", "99"))
GOLEMIO_TZ = os.getenv("GOLEMIO_TZ", "Europe/Prague")

STOP_NAMES = [s.strip() for s in os.getenv("GOLEMIO_STOP_NAMES", "Muzeum").split(",") if s.strip()]
API_KEY = os.getenv("GOLEMIO_API_KEY", "").strip()

app = FastAPI(title="Metro A Signage Backend")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

if STATIC_DIR.exists():
    app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="frontend")

LATEST_DEPARTURES: List[Dict[str, Any]] = []
LAST_OK_UTC: Optional[dt.datetime] = None
POLL_TASK: Optional[asyncio.Task] = None


def _utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _parse_iso(s: Optional[str]) -> Optional[dt.datetime]:
    if not s:
        return None
    s = s.replace("Z", "+00:00")
    try:
        d = dt.datetime.fromisoformat(s)
    except ValueError:
        return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=dt.timezone.utc)
    return d.astimezone(dt.timezone.utc)


def _minutes_until(ts_utc: Optional[dt.datetime], now_utc: dt.datetime) -> Optional[int]:
    if not ts_utc:
        return None
    return max(0, int((ts_utc - now_utc).total_seconds() // 60))


def normalize_departureboards(payload: Dict[str, Any], *, metro_line: str = METRO_LINE) -> List[Dict[str, Any]]:
    """Convert Golemio payload to small JSON used by frontend; filters to a single metro line."""
    metro_line = metro_line.strip().upper()
    now = _utc_now()
    out: List[Dict[str, Any]] = []

    for dep in payload.get("departures", []) or []:
        route = dep.get("route") or {}
        trip = dep.get("trip") or {}
        last_stop = dep.get("last_stop") or {}
        ts = dep.get("departure_timestamp") or {}

        line = str(route.get("short_name") or "").strip().upper()
        if line != metro_line:
            continue

        dest = str(trip.get("headsign") or last_stop.get("name") or "—").strip() or "—"
        predicted = _parse_iso(ts.get("predicted"))
        scheduled = _parse_iso(ts.get("scheduled"))
        used = predicted or scheduled
        in_min = _minutes_until(used, now)
        if in_min is None:
            continue

        out.append(
            {
                "line": metro_line,
                "dest": dest,
                "in_min": in_min,
                "t_utc": used.isoformat(),
            }
        )

    out.sort(key=lambda x: (x["in_min"], x["dest"]))
    return out


async def fetch_golemio_departures(client: httpx.AsyncClient) -> Optional[List[Dict[str, Any]]]:
    if not API_KEY:
        LOG.warning("Missing GOLEMIO_API_KEY -> live data disabled (fallback only).")
        return None

    params: List[tuple[str, str]] = []
    for name in STOP_NAMES:
        params.append(("names", name))

    params.extend(
        [
            ("preferredTimezone", GOLEMIO_TZ),
            ("includeMetroTrains", "true"),
            ("limit", str(GOLEMIO_LIMIT)),
            ("minutesAfter", str(GOLEMIO_MINUTES_AFTER)),
        ]
    )

    headers = {
        "Content-Type": "application/json; charset=utf-8",
        "x-access-token": API_KEY,
    }

    try:
        r = await client.get(GOLEMIO_URL, params=params, headers=headers, timeout=8.0)
        r.raise_for_status()
        payload = r.json()
        return normalize_departureboards(payload, metro_line=METRO_LINE)
    except Exception:
        LOG.exception("Golemio fetch failed")
        return None


def _is_online() -> bool:
    if LAST_OK_UTC is None:
        return False
    return (_utc_now() - LAST_OK_UTC).total_seconds() <= OFFLINE_AFTER_SECONDS


async def poller_loop() -> None:
    global LATEST_DEPARTURES, LAST_OK_UTC
    async with httpx.AsyncClient() as client:
        while True:
            deps = await fetch_golemio_departures(client)
            if deps is not None:
                LATEST_DEPARTURES = deps
                LAST_OK_UTC = _utc_now()
            await asyncio.sleep(REFRESH_SECONDS)


@app.on_event("startup")
async def _startup() -> None:
    global POLL_TASK
    POLL_TASK = asyncio.create_task(poller_loop())
    LOG.info("Poller started (line=%s stops=%s)", METRO_LINE, STOP_NAMES)


@app.on_event("shutdown")
async def _shutdown() -> None:
    global POLL_TASK
    if POLL_TASK:
        POLL_TASK.cancel()
        try:
            await POLL_TASK
        except asyncio.CancelledError:
            pass


@app.get("/api/status")
async def api_status() -> Dict[str, Any]:
    return {
        "ok": True,
        "online": _is_online(),
        "line": METRO_LINE,
        "stops": STOP_NAMES,
        "last_ok_utc": LAST_OK_UTC.isoformat() if LAST_OK_UTC else None,
        "time_utc": _utc_now().isoformat(),
    }


@app.get("/api/latest")
async def api_latest() -> Dict[str, Any]:
    return {"count": len(LATEST_DEPARTURES), "departures": LATEST_DEPARTURES}


@app.get("/api/fallback")
async def api_fallback() -> Dict[str, Any]:
    data_file = ROOT / "data" / "stations.json"
    if not data_file.exists():
        return {"departures": []}

    try:
        data = json.loads(data_file.read_text(encoding="utf-8"))
        deps = data.get("departures") or []
        out: List[Dict[str, Any]] = []
        for d in deps:
            if str(d.get("line", "")).strip().upper() != METRO_LINE:
                continue
            out.append(
                {
                    "line": METRO_LINE,
                    "dest": str(d.get("dest", "—")).strip() or "—",
                    "in_min": int(d.get("in_min", 0)),
                }
            )
        out.sort(key=lambda x: x["in_min"])
        return {"departures": out}
    except Exception:
        LOG.exception("Fallback read failed")
        return {"departures": []}


@app.websocket("/ws/updates")
async def ws_updates(ws: WebSocket) -> None:
    await ws.accept()
    try:
        while True:
            now = _utc_now().isoformat()
            departures = (LATEST_DEPARTURES[:20] if LATEST_DEPARTURES else [])
            if not departures:
                departures = [{"line": METRO_LINE, "dest": "—", "in_min": 0, "t_utc": now}]
            await ws.send_json({"t": now, "departures": departures, "online": _is_online()})
            await asyncio.sleep(WS_PUSH_SECONDS)
    except WebSocketDisconnect:
        return
    except Exception:
        LOG.exception("WS error")
        try:
            await ws.close()
        except Exception:
            pass
