"""Which peaks, passes and huts a track reached.

A point counts as visited when the track's closest approach is within the radius of its kind; a
peak only when the track also got up to it (track altitude there at least the peak's height minus
`peak_below`), so a path traversing the slope below a summit does not count. Calibrated against
peakproject's peak lines on 25 activities: 38 of 40 peaks found with 100 m / 80 m.
"""
from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass

GRID = 0.01
ALGO = 1                # bump when the result for the same track and points can change


@dataclass(frozen=True)
class Rules:
    peak_radius: float = 100.0
    peak_below: float = 80.0
    hut_radius: float = 60.0
    pass_radius: float = 60.0

    def radius(self, kind: str) -> float:
        return {"peak": self.peak_radius, "hut": self.hut_radius, "pass": self.pass_radius}[kind]


def display_name(poi: dict, language: str) -> str:
    return (poi.get("names") or {}).get(language) or poi["name"] if language else poi["name"]


def visits(track: dict, pois: list[dict], rules: Rules = Rules(), language: str = "") -> list[dict]:
    """[{osm, name, kind, ele, dist, idx}] in the order the track reached them; one per name and kind."""
    grid: dict[tuple[int, int], list[dict]] = defaultdict(list)
    for p in pois:
        grid[(int(p["lat"] // GRID), int(p["lon"] // GRID))].append(p)
    best: dict[str, tuple[float, int, float | None, dict]] = {}
    alt = track.get("alt") or []
    for i, (la, lo) in enumerate(zip(track["lat"], track["lng"])):
        ci, cj = int(la // GRID), int(lo // GRID)
        k = math.cos(math.radians(la)) * 111320
        for di in (-1, 0, 1):
            for dj in (-1, 0, 1):
                for p in grid.get((ci + di, cj + dj), ()):
                    d = math.hypot((p["lat"] - la) * 110540, (p["lon"] - lo) * k)
                    if d < 300 and (p["osm"] not in best or d < best[p["osm"]][0]):
                        best[p["osm"]] = (d, i, alt[i] if i < len(alt) else None, p)
    out = []
    for d, i, a, p in best.values():
        if d > rules.radius(p["kind"]):
            continue
        if p["kind"] == "peak" and p.get("ele") is not None and a is not None and a < p["ele"] - rules.peak_below:
            continue
        out.append({"osm": p["osm"], "name": display_name(p, language), "kind": p["kind"], "ele": p.get("ele"),
                    "dist": round(d), "idx": i})
    out.sort(key=lambda v: v["idx"])
    seen, unique = set(), []
    for v in out:
        if (v["kind"], v["name"]) not in seen:
            seen.add((v["kind"], v["name"]))
            unique.append(v)
    return unique
