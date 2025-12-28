"""
Mock feed generator for offline mode.

Writes data/stations.json with random Metro A departures.

Run:
  python backend/mock_feed.py --out data/stations.json
"""
from __future__ import annotations

import argparse
import json
import random
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="data/stations.json")
    parser.add_argument("--count", type=int, default=6)
    args = parser.parse_args()

    destinations = [
        "Nemocnice Motol",
        "Depo Hostivař",
        "Skalka",
        "Dejvická",
    ]

    deps = []
    mins = sorted(random.sample(range(1, 20), k=min(args.count, 10)))
    for i, m in enumerate(mins):
        deps.append({"line": "A", "dest": random.choice(destinations), "in_min": m})

    payload = {"departures": deps}
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {out} ({len(deps)} departures)")


if __name__ == "__main__":
    main()
