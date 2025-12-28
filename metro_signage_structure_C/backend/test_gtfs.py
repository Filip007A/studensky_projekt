# Jak aktivovat virtuální prostředí (.venv) na macOS (zsh / bash):
# 1) otevři terminál ve složce backend:
#    cd /Users/adamvitek/Documents/GitHub/Studentsk-projekt/backend
# 2) aktivuj venv:
#    source .venv/bin/activate
# 3) po práci deaktivuj:
#    deactivate
import os
import asyncio
import datetime
import logging
from google.transit import gtfs_realtime_pb2
from main import fetch_gtfs_rt

logging.basicConfig(level=logging.DEBUG, format="%(asctime)s %(levelname)s %(message)s")

def parse_feed_bytes(content):
    feed = gtfs_realtime_pb2.FeedMessage()
    feed.ParseFromString(content)
    now_ts = int(datetime.datetime.utcnow().timestamp())
    departures = []

    def safe_attr(obj, name, default=None):
        try:
            return getattr(obj, name, default)
        except Exception:
            return default

    for entity in feed.entity:
        try:
            if not entity.HasField("trip_update"):
                continue
            tu = entity.trip_update
            route_id = (safe_attr(tu.trip, "route_id", "") or "")[:10]
            trip_headsign = safe_attr(tu.trip, "trip_headsign", None)
            for stu in tu.stop_time_update:
                try:
                    if not stu.HasField("arrival"):
                        continue
                    arrival_ts = safe_attr(stu.arrival, "time", None)
                    if not arrival_ts:
                        continue
                    in_min = max(0, int((arrival_ts - now_ts) / 60))
                    dest = trip_headsign or route_id or "?"
                    departures.append({"line": route_id or "?", "dest": dest, "in_min": in_min})
                    break
                except Exception:
                    logging.debug("Skipping stop_time_update due to parse error", exc_info=True)
                    continue
        except Exception:
            logging.debug("Skipping entity due to parse error", exc_info=True)
            continue

    return sorted(departures, key=lambda x: x["in_min"])

async def run():
    url = os.getenv("GTFS_RT_URL")
    if not url:
        print("GTFS_RT_URL not set. Export real HTTP URL or path to local .pb file.")
        return

    # local file path or file:// URI
    if url.startswith("file://") or os.path.exists(url):
        path = url[7:] if url.startswith("file://") else url
        logging.debug("Reading local GTFS-RT file: %s", path)
        try:
            with open(path, "rb") as fh:
                content = fh.read()
            deps = parse_feed_bytes(content)
            print("OK (local)", len(deps), deps[:10])
        except Exception:
            logging.exception("Failed to read/parse local file")
            print("FAILED None")
        return

    # otherwise try HTTP fetch via fetch_gtfs_rt from main.py
    logging.debug("Using fetch_gtfs_rt for URL: %s", url)
    deps = await fetch_gtfs_rt(url)
    if deps:
        print("OK (http)", len(deps), deps[:10])
    else:
        print("FAILED None")

if __name__ == "__main__":
    asyncio.run(run())