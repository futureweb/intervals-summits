"""Command line: sync, backfill, recompute, run, ui, page, status, fields."""
from __future__ import annotations

import argparse
import http.server
import json
import logging
import sys
import threading
import time
from collections import Counter
from datetime import date, datetime, timedelta
from pathlib import Path

from . import __version__, page
from . import fields as F
from .config import Settings, load
from .intervals import IntervalsClient
from .osm import OSM
from .store import Store
from .sync import Context, backfill, sync

log = logging.getLogger("intervals_summits")

# garmin-intervals-bridge (BRIDGE_NOTIFY_URL) can tell `run --ui` about new activities with a POST /sync
QUIET_MINUTES = 180         # while it does, look on our own only this often (in case the bridge stops)
NOTIFIED_DAYS = 14          # ... as long as its last note is this recent
RECHECK_MINUTES = 10        # a reported activity without a track yet: ask once more this soon
NOTE_DELAY = 5              # seconds: notes in quick succession make one sync
MIN_GAP_SECONDS = 60        # and at most one sync a minute


def context(settings: Settings) -> Context:
    store = Store(settings.db_file, settings.tracks_dir)
    iv = IntervalsClient(settings.api_key, settings.athlete_id, pause=settings.pause)
    return Context(settings, iv, store, OSM(store, settings.overpass_url))


def write_page(ctx: Context) -> None:
    size = page.write(ctx.store, ctx.settings.page_file, ctx.settings.language, ctx.settings.page_title)
    ctx.counts["page_kb"] = size // 1024


def ensure_fields(ctx: Context) -> None:
    """Create missing fields – checked once a day (the list of custom items is not small)."""
    key = ",".join(ctx.settings.fields)
    if ctx.store.get("fields_checked") == f"{date.today()} {key}":
        return
    for code in F.ensure(ctx.iv, ctx.settings.fields, ctx.settings.language, True)["missing"]:
        ctx.counts[f"field_created_{code}"] += 1
    ctx.store.put("fields_checked", f"{date.today()} {key}")


def report(ctx: Context, apply: bool, **extra) -> None:
    out = {"apply": apply, **extra, **{k: v for k, v in sorted(ctx.counts.items())},
           "intervals_requests": ctx.iv.requests, "page": str(ctx.settings.page_file)}
    print(json.dumps(out, ensure_ascii=False, indent=2))


def cmd_sync(ctx: Context, args) -> int:
    if args.apply:
        ensure_fields(ctx)
    sync(ctx, apply=args.apply, force=args.force)
    write_page(ctx)
    report(ctx, args.apply)
    return 0


def cmd_backfill(ctx: Context, args, recompute: bool = False) -> int:
    if args.apply:
        ensure_fields(ctx)
    oldest = date.fromisoformat(args.from_)
    newest = date.fromisoformat(args.to) if args.to else date.today() + timedelta(days=1)
    backfill(ctx, oldest, newest, apply=args.apply, force=args.force, recompute=recompute)
    write_page(ctx)
    report(ctx, args.apply, window=f"{oldest} – {newest}")
    return 0


def cmd_page(ctx: Context, args) -> int:
    path = Path(args.out) if args.out else ctx.settings.page_file
    size = page.write(ctx.store, path, args.language or ctx.settings.language, ctx.settings.page_title)
    print(f"{path}: {size // 1024} KB")
    return 0


def poll_minutes(ctx: Context, now: datetime | None = None) -> int:
    """How often to look on our own: SUMMITS_INTERVAL_MINUTES, or every 3 hours while the bridge reports."""
    told = ctx.store.get("notified_at")
    if told and (now or datetime.now()) - datetime.fromisoformat(told) <= timedelta(days=NOTIFIED_DAYS):
        return max(ctx.settings.interval_minutes, QUIET_MINUTES)
    return ctx.settings.interval_minutes


def healthy(ctx: Context, now: datetime | None = None) -> tuple[bool, str]:
    """No request to anyone: is the last successful sync recent enough?"""
    last = ctx.store.get("last_sync_at")
    if not last:
        return True, "no sync yet"
    age = ((now or datetime.now()) - datetime.fromisoformat(last)).total_seconds() / 60
    limit = max(60, 3 * poll_minutes(ctx, now))
    return age <= limit, f"last sync {age:.0f} minutes ago"


def cmd_status(ctx: Context, args) -> int:
    if args.check:
        ok, text = healthy(ctx)
        print(("healthy: " if ok else "unhealthy: ") + text)
        return 0 if ok else 1
    out = {"version": __version__, "data_dir": str(ctx.settings.data_dir), "fields": list(ctx.settings.fields),
           "language": ctx.settings.language, "last_sync": ctx.store.get("last_sync_at"),
           "last_bridge_note": ctx.store.get("notified_at"), **ctx.store.counts()}
    if args.fields:
        out["intervals_fields"] = F.ensure(ctx.iv, ctx.settings.fields, ctx.settings.language, False)
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


def cmd_fields(ctx: Context, args) -> int:
    print(json.dumps(F.ensure(ctx.iv, ctx.settings.fields, ctx.settings.language, args.apply), indent=2))
    return 0


def serve(settings: Settings, host: str, port: int, wake: threading.Event | None = None) -> http.server.ThreadingHTTPServer:
    """The summit log, rendered fresh from the database for every request (read only). With `wake`
    (from `run`) also POST /sync: new activities in Intervals, sync now. It takes no data, only the
    note; the run loop keeps it to one sync a minute."""

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            if self.path.split("?")[0].rstrip("/") not in ("", "/index.html"):
                self.send_error(404)
                return
            store = Store(settings.db_file, settings.tracks_dir)
            try:
                body = page.render(store, settings.language, settings.page_title).encode("utf-8")
            finally:
                store.close()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self):  # noqa: N802
            if wake is None or self.path.split("?")[0].rstrip("/") != "/sync":
                self.send_error(404)
                return
            try:
                length = min(max(int(self.headers.get("Content-Length") or 0), 0), 65536)
                who = str(json.loads(self.rfile.read(length) or b"{}").get("source") or "")
            except (ValueError, AttributeError):
                who = ""
            log.info("%s reports new activities: a sync follows", "".join(c for c in who[:60] if c.isprintable()) or "Someone")
            wake.set()
            body = b'{"ok": true}'
            self.send_response(202)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass

    return http.server.ThreadingHTTPServer((host, port), Handler)


def cmd_ui(ctx: Context, args) -> int:
    server = serve(ctx.settings, args.host, args.port)
    print(f"Summit log on http://{args.host}:{args.port}/ (Ctrl+C stops it)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


def cmd_run(ctx: Context, args) -> int:
    """Keep running: a sync every SUMMITS_INTERVAL_MINUTES, the page after each (and with --ui on the web)."""
    wake = threading.Event()
    if args.ui:
        server = serve(ctx.settings, args.host, args.port, wake)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        log.info("Summit log on http://%s:%d/ (POST /sync there: new activities, sync now)", args.host, args.port)
    log.info("intervals-summits %s: a sync every %d minutes%s", __version__, poll_minutes(ctx),
             "" if args.apply else " – a dry run: nothing is written to Intervals until --apply")
    run_loop(ctx, apply=args.apply, wake=wake)
    return 0


def run_loop(ctx: Context, *, apply: bool, wake: threading.Event, iterations: int | None = None,
             sleep=time.sleep) -> None:
    told, count = False, 0
    while iterations is None or count < iterations:
        count += 1
        started = time.monotonic()
        ctx.counts = Counter()
        try:
            if told:
                ctx.store.put("notified_at", datetime.now().isoformat(timespec="seconds"))
            if apply:
                ensure_fields(ctx)
            sync(ctx, apply=apply)
            write_page(ctx)
            done = {k: v for k, v in ctx.counts.items() if k in ("matched", "with_summits", "activities_to_write",
                                                                  "activities_written", "failed") and v}
            if done:
                log.info("Sync: %s", done)
        except Exception as exc:  # noqa: BLE001 – keep running; the next pass tries again
            log.warning("Sync failed: %s", exc)
        if iterations is not None and count >= iterations:
            return
        wait = poll_minutes(ctx) * 60
        if told and ctx.counts["no_gps"]:
            wait = min(wait, RECHECK_MINUTES * 60)       # Intervals may not have read its track yet
        told = wake.wait(wait)
        if told:
            sleep(max(NOTE_DELAY, started + MIN_GAP_SECONDS - time.monotonic()))
            wake.clear()                                 # notes until now: this one sync covers them


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="intervals-summits", description="Summits on your Intervals.icu activities")
    ap.add_argument("--version", action="version", version=__version__)
    ap.add_argument("-v", "--verbose", action="store_true")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("sync", help="the recent days (after a pause back to the last run)")
    p.add_argument("--apply", action="store_true", help="write to Intervals (else: a dry run)")
    p.add_argument("--force", action="store_true", help="also overwrite values someone else wrote")
    for name, text in (("backfill", "the past: match activities not matched yet"), ("recompute", "match again (new OSM data or rules)")):
        p = sub.add_parser(name, help=text)
        p.add_argument("--from", dest="from_", required=True, metavar="DATE")
        p.add_argument("--to", metavar="DATE")
        p.add_argument("--apply", action="store_true")
        p.add_argument("--force", action="store_true")
    p = sub.add_parser("run", help="keep running: a sync every few minutes")
    p.add_argument("--apply", action="store_true")
    p.add_argument("--ui", action="store_true", help="also serve the summit log page")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8766)
    p = sub.add_parser("ui", help="serve the summit log page")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8766)
    p = sub.add_parser("page", help="write the summit log page")
    p.add_argument("--out")
    p.add_argument("--language", choices=["en", "de"])
    p = sub.add_parser("status")
    p.add_argument("--check", action="store_true", help="health only, no request: exit 1 when no sync came for long")
    p.add_argument("--fields", action="store_true", help="also ask Intervals which fields exist")
    p = sub.add_parser("fields", help="create the activity fields that are missing")
    p.add_argument("--apply", action="store_true")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                        datefmt="%Y-%m-%d %H:%M:%S", stream=sys.stderr)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    ctx = context(load())
    try:
        if args.cmd == "sync":
            return cmd_sync(ctx, args)
        if args.cmd in ("backfill", "recompute"):
            return cmd_backfill(ctx, args, recompute=args.cmd == "recompute")
        return {"page": cmd_page, "status": cmd_status, "fields": cmd_fields, "run": cmd_run, "ui": cmd_ui}[args.cmd](ctx, args)
    finally:
        ctx.store.close()
