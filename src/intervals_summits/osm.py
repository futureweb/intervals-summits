"""Named peaks, passes and huts from OpenStreetMap (Overpass), cached in 0.2° cells.

Only cells are ever sent to Overpass, never a track. Missing or stale cells are grouped into
connected areas, one query per area (at most MAX_SPAN cells a side). Fair use: one query at a time,
a pause between them, patience on 429/5xx.
"""
from __future__ import annotations

import logging
import re
import time
from datetime import datetime, timedelta, timezone
from typing import Callable
from urllib.parse import quote

import requests

from . import __version__
from .store import Store

log = logging.getLogger(__name__)
CELL = 0.2
EDGE = 0.004            # a track point this close (°) to a cell border also needs the neighbouring cell
MAX_SPAN = 6            # cells per side and query
TTL_DAYS = 180
QUERY = """[out:json][timeout:300];
(
  node["natural"~"^(peak|volcano|saddle)$"]["name"]({b});
  node["mountain_pass"="yes"]["name"]({b});
  node["tourism"~"^(alpine_hut|wilderness_hut)$"]["name"]({b});
  way["tourism"~"^(alpine_hut|wilderness_hut)$"]["name"]({b});
);
out center tags;"""
# a collection: every named summit inside an area (by name, or r<relation id>), coordinates included
COLLECTION_QUERY = """[out:json][timeout:300];
{area}->.a;
node["natural"~"^(peak|volcano)$"]["name"](area.a);
out;"""


def area_filter(area: str) -> str:
    if re.fullmatch(r"r\d+", area):
        return f"area(id:{3600000000 + int(area[1:])})"
    return 'area["name"="' + area.replace("\\", "\\\\").replace('"', '\\"') + '"]'


def collection_members(elements: list[dict], min_ele: int = 0) -> list[dict]:
    out = {}
    for el in elements:
        tags = el.get("tags") or {}
        height = ele(tags.get("ele"))
        if el.get("type") != "node" or not tags.get("name") or el.get("lat") is None:
            continue
        if min_ele and (height is None or height < min_ele):
            continue
        out[el["id"]] = {"osm": f"node/{el['id']}", "name": tags["name"], "ele": height, "lat": el["lat"], "lon": el["lon"]}
    return list(out.values())

Cell = tuple[int, int]


def cell_of(lat: float, lon: float) -> Cell:
    return int(lat // CELL), int(lon // CELL)


def cells_for(lat: list[float], lng: list[float]) -> set[Cell]:
    out: set[Cell] = set()
    for la, lo in zip(lat, lng):
        i, j = cell_of(la, lo)
        out.add((i, j))
        fi, fj = la / CELL - i, lo / CELL - j          # position inside the cell, 0..1
        di = -1 if fi * CELL < EDGE else 1 if (1 - fi) * CELL < EDGE else 0
        dj = -1 if fj * CELL < EDGE else 1 if (1 - fj) * CELL < EDGE else 0
        if di:
            out.add((i + di, j))
        if dj:
            out.add((i, j + dj))
        if di and dj:
            out.add((i + di, j + dj))
    return out


def areas(cells: set[Cell]) -> list[set[Cell]]:
    """Connected groups of cells, each cut into blocks of at most MAX_SPAN × MAX_SPAN cells."""
    left, groups = set(cells), []
    while left:
        stack, comp = [left.pop()], set()
        while stack:
            c = stack.pop()
            comp.add(c)
            for n in ((c[0] + 1, c[1]), (c[0] - 1, c[1]), (c[0], c[1] + 1), (c[0], c[1] - 1)):
                if n in left:
                    left.remove(n)
                    stack.append(n)
        blocks: dict[Cell, set[Cell]] = {}
        i0, j0 = min(c[0] for c in comp), min(c[1] for c in comp)
        for c in comp:
            blocks.setdefault(((c[0] - i0) // MAX_SPAN, (c[1] - j0) // MAX_SPAN), set()).add(c)
        groups.extend(blocks.values())
    return sorted(groups, key=lambda g: min(g))


def bbox(group: set[Cell]) -> tuple[float, float, float, float]:
    """south, west, north, east of the rectangle around the cells."""
    return (min(c[0] for c in group) * CELL, min(c[1] for c in group) * CELL,
            (max(c[0] for c in group) + 1) * CELL, (max(c[1] for c in group) + 1) * CELL)


def ele(text: str | None) -> float | None:
    found = re.match(r"\s*(-?\d+(?:[.,]\d+)?)", text or "")
    return float(found.group(1).replace(",", ".")) if found else None


def wiki(tags: dict) -> str | None:
    """OpenStreetMap's link to an article: "de:Maukspitze", else the Wikidata item "wikidata:Q123"."""
    if tags.get("wikipedia") and ":" in tags["wikipedia"]:
        return tags["wikipedia"]
    return f"wikidata:{tags['wikidata']}" if tags.get("wikidata") else None


def wiki_url(value: str | None) -> str | None:
    if not value or ":" not in value:
        return None
    lang, title = value.split(":", 1)
    if lang == "wikidata":
        return "https://www.wikidata.org/wiki/" + quote(title.strip())
    if not lang.isalpha() or len(lang) > 12:
        return None
    return f"https://{lang}.wikipedia.org/wiki/" + quote(title.strip().replace(" ", "_"))


def parse(elements: list[dict]) -> list[dict]:
    out = {}
    for el in elements:
        tags = el.get("tags") or {}
        lat = el.get("lat", (el.get("center") or {}).get("lat"))
        lon = el.get("lon", (el.get("center") or {}).get("lon"))
        if lat is None or lon is None or not tags.get("name"):
            continue
        if tags.get("natural") in ("peak", "volcano"):
            kind = "peak"
        elif tags.get("natural") == "saddle" or tags.get("mountain_pass") == "yes":
            kind = "pass"
        elif tags.get("tourism") in ("alpine_hut", "wilderness_hut"):
            kind = "hut"
        else:
            continue
        ci, cj = cell_of(lat, lon)
        osm = f"{el['type']}/{el['id']}"
        out[osm] = {"osm": osm, "name": tags["name"], "kind": kind, "ele": ele(tags.get("ele")), "lat": lat, "lon": lon,
                    "ci": ci, "cj": cj, "names": {k[5:]: v for k, v in tags.items() if k.startswith("name:") and len(k) <= 8},
                    "wiki": wiki(tags)}
    return list(out.values())


class OSM:
    def __init__(self, store: Store, url: str, *, session: requests.Session | None = None,
                 sleep: Callable[[float], None] = time.sleep, ttl_days: int = TTL_DAYS, pause: float = 5.0):
        self.store, self.url, self.sleep, self.pause = store, url, sleep, pause
        self.ttl = timedelta(days=ttl_days)
        self.session = session or requests.Session()
        self.session.headers["User-Agent"] = f"intervals-summits/{__version__} (+https://github.com/futureweb/intervals-summits)"
        self.queries = 0

    def stale(self, cells: set[Cell]) -> set[Cell]:
        limit = datetime.now(timezone.utc) - self.ttl
        out = set()
        for c in cells:
            fetched = self.store.cell_fetched(c)
            if not fetched or datetime.fromisoformat(fetched) < limit:
                out.add(c)
        return out

    def ensure(self, cells: set[Cell]) -> int:
        """Fetch what is missing or stale; returns the number of Overpass queries."""
        todo = self.stale(cells)
        groups = areas(todo)
        for n, group in enumerate(groups):
            s, w, no, e = bbox(group)
            elements = self._query(f"{s:.4f},{w:.4f},{no:.4f},{e:.4f}")
            covered = {(i, j) for i in range(round(s / CELL), round(no / CELL)) for j in range(round(w / CELL), round(e / CELL))}
            self.store.save_pois(covered, parse(elements))
            log.info("OpenStreetMap: area %d/%d (%d cells), %d points", n + 1, len(groups), len(covered), len(elements))
            if n + 1 < len(groups):
                self.sleep(self.pause)
        return len(groups)

    def collection(self, c) -> list[dict]:
        """The summits of one collection (one query; the caller keeps them for half a year)."""
        return collection_members(self._post(COLLECTION_QUERY.format(area=area_filter(c.area))), c.min_ele)

    def _query(self, box: str) -> list[dict]:
        return self._post(QUERY.format(b=box))

    def _post(self, query: str) -> list[dict]:
        response = None
        for wait in (0, 30, 90, 180, 300, 600):
            self.sleep(wait)
            self.queries += 1
            try:
                response = self.session.post(self.url, data={"data": query}, timeout=360)
            except requests.RequestException as exc:
                log.info("OpenStreetMap: %s, trying again", exc.__class__.__name__)
                continue
            if response.status_code not in (429, 502, 503, 504):
                break
            log.info("OpenStreetMap: HTTP %s, trying again", response.status_code)
        if response is None:
            raise RuntimeError("OpenStreetMap (Overpass) not reachable")
        response.raise_for_status()
        return response.json().get("elements", [])
