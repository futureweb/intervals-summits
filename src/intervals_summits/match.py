"""Which peaks, passes and huts a track reached.

A point counts as visited when the track's closest approach is within the radius of its kind; a
peak only when the track also got up to it (track altitude there at least the peak's height minus
`peak_below`), so a path traversing the slope below a summit does not count. Of two summits close
together, standing on one does not count the other: when the track, at its closest to a summit, was
more than NEIGHBOUR metres nearer to another summit it reached, only that one counts (the Kapuzenturm,
94 m from the Ellmauer Halt). Calibrated against an independent summit log of 25 activities: 38 of
40 peaks found with 100 m / 80 m.
"""
from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass

GRID = 0.01
ALGO = 2                # bump when the result for the same track and points can change
NEIGHBOUR = 25.0        # metres; twin summits nearer together than this both count


@dataclass(frozen=True)
class Rules:
    peak_radius: float = 100.0
    peak_below: float = 80.0
    hut_radius: float = 60.0
    pass_radius: float = 60.0

    def radius(self, kind: str) -> float:
        return {"peak": self.peak_radius, "hut": self.hut_radius, "pass": self.pass_radius}[kind]


def metres(p: dict, la: float, lo: float) -> float:
    return math.hypot((p["lat"] - la) * 110540, (p["lon"] - lo) * math.cos(math.radians(la)) * 111320)


def display_name(poi: dict, language: str) -> str:
    return (poi.get("names") or {}).get(language) or poi["name"] if language else poi["name"]


def visits(track: dict, pois: list[dict], rules: Rules = Rules(), language: str = "") -> list[dict]:
    """[{osm, name, kind, ele, est, dist, idx}] in the order the track reached them; one per name and kind.
    Without a height in OpenStreetMap, `ele` is the track's altitude at its closest point and `est` True."""
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
    reached = []
    for d, i, a, p in best.values():
        if d > rules.radius(p["kind"]):
            continue
        if p["kind"] == "peak" and p.get("ele") is not None and a is not None and a < p["ele"] - rules.peak_below:
            continue
        reached.append((d, i, a, p))
    peaks = [p for _, _, _, p in reached if p["kind"] == "peak"]
    out = []
    for d, i, a, p in reached:
        la, lo = track["lat"][i], track["lng"][i]
        if p["kind"] == "peak" and any(q is not p and metres(q, la, lo) + NEIGHBOUR < d for q in peaks):
            continue                                   # the track was on the neighbour summit
        ele, est = p.get("ele"), False
        if ele is None and a is not None:
            ele, est = float(round(a)), True
        out.append({"osm": p["osm"], "name": display_name(p, language), "kind": p["kind"], "ele": ele, "est": est,
                    "dist": round(d), "idx": i})
    out.sort(key=lambda v: v["idx"])
    seen, unique = set(), []
    for v in out:
        if (v["kind"], v["name"]) not in seen:
            seen.add((v["kind"], v["name"]))
            unique.append(v)
    return unique
