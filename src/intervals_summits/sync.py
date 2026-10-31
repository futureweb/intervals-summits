"""One pass over a date window: new outdoor activities get their track read and matched, then every
activity in the window gets its field values compared with Intervals and written where needed.

Three steps so a backfill stays light: tracks first (cached on disk), then OpenStreetMap for all
the cells they need at once (few, large queries), then matching and writing one activity at a time.
"""
from __future__ import annotations

import logging
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from . import fields as F
from .config import INDOOR, Settings
from .intervals import IntervalsClient
from .match import ALGO, Rules, visits as match_visits
from .osm import OSM, cells_for
from .store import Store

log = logging.getLogger(__name__)


@dataclass
class Context:
    settings: Settings
    iv: IntervalsClient
    store: Store
    osm: OSM
    counts: Counter = field(default_factory=Counter)

    @property
    def rules(self) -> Rules:
        s = self.settings
        return Rules(s.peak_radius, s.peak_below, s.hut_radius, s.pass_radius)


def list_fields(settings: Settings) -> list[str]:
    extra = ["description"] if settings.description else []
    return ["id", "type", "name", "start_date_local", "distance", "elapsed_time", "trainer", "max_altitude", *settings.fields, *extra]


def outdoor(a: dict, settings: Settings) -> bool:
    if a.get("trainer") or not a.get("type"):
        return False
    if settings.types:
        if a["type"] not in settings.types:
            return False
    elif a["type"] in INDOOR:
        return False
    # some uploads (a Samsung watch's TCX) have a track but a distance of 0
    return (a.get("distance") or 0) > 500 or (a.get("elapsed_time") or 0) > 1200


def read_track(ctx: Context, a: dict) -> dict:
    cached = ctx.store.load_track(a["id"])
    if cached is not None:
        return cached
    streams = {s.get("type"): s for s in ctx.iv.streams(a["id"], ["latlng", "altitude", "fixed_altitude"]) if isinstance(s, dict)}
    ll = streams.get("latlng") or {}
    alt = (streams.get("fixed_altitude") or streams.get("altitude") or {}).get("data") or []
    lat, lng = ll.get("data") or [], ll.get("data2") or []
    keep = [i for i in range(min(len(lat), len(lng)))
            if isinstance(lat[i], (int, float)) and isinstance(lng[i], (int, float)) and (lat[i], lng[i]) != (0, 0)]
    track = {"id": a["id"], "date": a.get("start_date_local"), "type": a.get("type"), "name": a.get("name"),
             "lat": [round(lat[i], 5) for i in keep], "lng": [round(lng[i], 5) for i in keep],
             "alt": [round(alt[i]) if i < len(alt) and isinstance(alt[i], (int, float)) else None for i in keep]}
    ctx.store.save_track(track)
    ctx.counts["tracks_read"] += 1
    return track


def needs_matching(ctx: Context, a: dict, recompute: bool) -> bool:
    row = ctx.store.activity(a["id"])
    return recompute or row is None or row["algo"] != ALGO


def process_window(ctx: Context, oldest: date, newest: date, *, apply: bool, force: bool = False,
                   recompute: bool = False) -> None:
    s = ctx.settings
    acts = ctx.iv.activities(oldest, newest, list_fields(s))
    ctx.counts["listed"] += len(acts)
    ctx.counts["forgotten"] += ctx.store.forget_missing(oldest.isoformat(), newest.isoformat(), {a["id"] for a in acts})
    outdoor_acts = [a for a in acts if outdoor(a, s)]
    todo = [a for a in outdoor_acts if needs_matching(ctx, a, recompute)]
    if todo:
        log.info("%s – %s: %d outdoor activities, %d to match", oldest, newest, len(outdoor_acts), len(todo))
    # 1. tracks (and the cells they need)
    cells: set = set()
    tracks_ok = []
    for n, a in enumerate(todo, 1):
        try:
            track = read_track(ctx, a)
        except Exception as exc:  # noqa: BLE001 – one bad activity must not stop the others
            log.warning("Activity %s: track not readable (%s)", a["id"], exc)
            ctx.counts["failed"] += 1
            continue
        if track["lat"]:
            cells |= cells_for(track["lat"], track["lng"])
        tracks_ok.append(a)
        if n % 100 == 0:
            log.info("  tracks %d/%d", n, len(todo))
    # 2. OpenStreetMap for all of them
    if cells:
        ctx.counts["osm_queries"] += ctx.osm.ensure(cells)
    # 3. match
    for a in tracks_ok:
        track = ctx.store.load_track(a["id"]) or {"lat": [], "lng": [], "alt": []}
        if not track["lat"]:
            ctx.store.save_activity(a, "no_gps", 0, a.get("max_altitude"), ALGO)
            ctx.counts["no_gps"] += 1
        else:
            found = match_visits(track, ctx.store.pois_in(cells_for(track["lat"], track["lng"])), ctx.rules, s.name_language)
            alts = [x for x in track["alt"] if x is not None]
            max_alt = a.get("max_altitude") or (max(alts) if alts else None)
            ctx.store.save_activity(a, "done", len(track["lat"]), max_alt, ALGO, found)
            ctx.counts["matched"] += 1
            ctx.counts["with_summits"] += any(v["kind"] == "peak" for v in found)
        if not s.keep_tracks:
            ctx.store.drop_track(a["id"])
    # 4. fields
    for a in outdoor_acts:
        row = ctx.store.activity(a["id"])
        if row is None or row["status"] != "done":
            continue
        ctx.store.refresh_activity(a)
        want = F.wanted(ctx.store.visits(a["id"]), row["max_alt"], s.fields)
        last = ctx.store.written(a["id"])
        writes, adopted, adopted_line = {}, {}, None
        for code, value in want.items():
            verdict = F.decide(code, value, a.get(code), last.get(code), force)
            ctx.counts[f"{code}_{verdict}"] += 1
            if verdict == "write":
                writes[code] = value
            elif verdict == "same" and code not in last and code != "HighestPoint":
                adopted[code] = value
        if s.description:
            line = F.description_line(ctx.store.visits(a["id"]), a.get("description"), s.language)
            verdict = F.decide("description", line, F.our_line(a.get("description")), last.get("description"), force)
            ctx.counts[f"description_{verdict}"] += 1
            if verdict == "write":
                writes["description"] = F.with_line(a.get("description"), line)
                adopted_line = line
            elif verdict == "same" and "description" not in last:
                adopted["description"] = line
        if adopted:
            ctx.store.record_written(a["id"], adopted)
        if writes:
            ctx.counts["activities_to_write"] += 1
            if apply:
                ctx.iv.update_activity(a["id"], writes)
                # for the description only our line counts as written, not the whole text
                ctx.store.record_written(a["id"], {k: (adopted_line if k == "description" else v) for k, v in writes.items()})
                ctx.counts["activities_written"] += 1


def windows(oldest: date, newest: date, days: int = 366):
    start = oldest
    while start <= newest:
        end = min(newest, start + timedelta(days=days - 1))
        yield start, end
        start = end + timedelta(days=1)


def sync(ctx: Context, *, apply: bool, force: bool = False, today: date | None = None) -> None:
    """The recent days; after a pause back to the last run (at most catchup_days)."""
    today = today or date.today()
    s = ctx.settings
    oldest = today - timedelta(days=s.lookback_days)
    last = ctx.store.get("last_sync")
    if last:
        oldest = min(oldest, max(date.fromisoformat(last) - timedelta(days=1), today - timedelta(days=s.catchup_days)))
    process_window(ctx, oldest, today + timedelta(days=1), apply=apply, force=force)
    if apply:
        ctx.store.put("last_sync", today.isoformat())
        ctx.store.put("last_sync_at", datetime.now().isoformat(timespec="seconds"))


def backfill(ctx: Context, oldest: date, newest: date, *, apply: bool, force: bool = False, recompute: bool = False) -> None:
    for start, end in windows(oldest, newest):
        process_window(ctx, start, end, apply=apply, force=force, recompute=recompute)
        log.info("%s – %s done: %s", start, end, dict(ctx.counts))
