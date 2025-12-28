"""
Minimal unit tests for normalization (kept name test_gtfs.py to match your structure).

Run:
  python -m unittest backend.test_gtfs
"""
from __future__ import annotations

import unittest

from backend.main import normalize_departureboards


class TestNormalizeDepartureboards(unittest.TestCase):
    def test_filters_only_metro_b(self) -> None:
        payload = {
            "departures": [
                {"route": {"short_name": "B"}, "trip": {"headsign": "Nemocnice Motol"}, "departure_timestamp": {"scheduled": "2030-01-01T10:00:00Z"}},
                {"route": {"short_name": "B"}, "trip": {"headsign": "Zličín"}, "departure_timestamp": {"scheduled": "2030-01-01T10:02:00Z"}},
            ]
        }
        out = normalize_departureboards(payload, metro_line="B")
        self.assertTrue(all(d["line"] == "A" for d in out))
        self.assertEqual(len(out), 1)

    def test_sorts_by_minutes(self) -> None:
        payload = {
            "departures": [
                {"route": {"short_name": "B"}, "trip": {"headsign": "X"}, "departure_timestamp": {"scheduled": "2099-01-01T10:10:00Z"}},
                {"route": {"short_name": "B"}, "trip": {"headsign": "Y"}, "departure_timestamp": {"scheduled": "2099-01-01T10:05:00Z"}},
            ]
        }
        out = normalize_departureboards(payload, metro_line="B")
        self.assertEqual(out[0]["dest"], "Y")


if __name__ == "__main__":
    unittest.main()
