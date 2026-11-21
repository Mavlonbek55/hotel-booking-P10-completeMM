"""Measure 1,000 identical availability requests against the running API.

Run the app in one terminal, then: python tools/measure.py
Set MEASURE_MODE=cache or no-cache to label the run in the output.
"""
from __future__ import annotations

import json
import os
import statistics
import time
import urllib.request

BASE = os.getenv("HOTEL_API_URL", "http://localhost:5080")
URL = BASE + "/rooms/availability?checkIn=2026-11-12&checkOut=2026-11-14"
COUNT = 1000


def get_json(url):
    with urllib.request.urlopen(url, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


before = get_json(BASE + "/stats")
durations = []
for _ in range(COUNT):
    start = time.perf_counter()
    with urllib.request.urlopen(URL, timeout=10) as response:
        if response.status != 200:
            raise RuntimeError(f"Unexpected HTTP status: {response.status}")
        response.read()
    durations.append((time.perf_counter() - start) * 1000)
after = get_json(BASE + "/stats")

durations.sort()
p95 = durations[int(0.95 * len(durations)) - 1]
print(f"Mode: {os.getenv('MEASURE_MODE', 'unspecified')}")
print(f"Searches: {COUNT}")
print(f"Average: {statistics.mean(durations):.3f} ms")
print(f"p95: {p95:.3f} ms")
for key, label in (("databaseQueries", "Database queries"),
                   ("cacheHits", "Cache hits"), ("cacheMisses", "Cache misses")):
    print(f"{label}: {after[key] - before[key]}")
