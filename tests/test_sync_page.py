import re
import shutil
import subprocess
from datetime import date
from pathlib import Path

import pytest

from intervals_summits import page
from intervals_summits.config import Settings
from intervals_summits.osm import OSM
from intervals_summits.store import Store
from intervals_summits.sync import Context, sync

PEAK_EL = {"type": "node", "id": 1, "lat": 47.5, "lon": 12.4, "tags": {"natural": "peak", "name": "Gscheuerkopf", "ele": "1180"}}


class FakeIntervals:
    def __init__(self, acts, streams):
        self.acts, self.streams_by_id, self.puts, self.requests = acts, streams, [], 0

    def activities(self, oldest, newest, fields=None):
        return [a for a in self.acts if oldest.isoformat() <= a["start_date_local"][:10] <= newest.isoformat()]

    def streams(self, aid, types):
        return self.streams_by_id[aid]

    def update_activity(self, aid, values):
        self.puts.append((aid, values))
        for a in self.acts:
            if a["id"] == aid:
                a.update(values)


class FakeResponse:
    status_code = 200

    def raise_for_status(self):
        pass

    def json(self):
        return {"elements": [PEAK_EL]}


class FakeSession:
    def __init__(self):
        self.headers, self.posts = {}, 0

    def post(self, url, data, timeout):
        self.posts += 1
        return FakeResponse()


def make(tmp_path, acts, streams, **settings):
    s = Settings(api_key="x", data_dir=tmp_path, **settings)
    store = Store(s.db_file, s.tracks_dir)
    session = FakeSession()
    return Context(s, FakeIntervals(acts, streams), store, OSM(store, "http://osm", session=session, sleep=lambda _: None)), session


def hike(aid, day, **kw):
    return {"id": aid, "type": "Hike", "name": "Tour", "start_date_local": f"{day}T09:00:00", "distance": 8000,
            "elapsed_time": 9000, "max_altitude": 1190.0, **kw}


STREAMS = [{"type": "latlng", "data": [47.499, 47.4996], "data2": [12.4, 12.4]}, {"type": "altitude", "data": [1100, 1150]}]


def test_sync_writes_then_leaves_alone(tmp_path):
    acts = [hike("i1", "2026-10-30"), hike("i2", "2026-10-30", Summits="typed by hand"),
            {"id": "i3", "type": "VirtualRide", "start_date_local": "2026-10-30T18:00:00", "distance": 30000}]
    ctx, session = make(tmp_path, acts, {"i1": STREAMS, "i2": STREAMS})
    sync(ctx, apply=False, today=date(2026, 10, 31))
    assert ctx.iv.puts == [] and ctx.counts["matched"] == 2 and session.posts == 1
    sync(ctx, apply=True, today=date(2026, 10, 31))
    assert ctx.iv.puts == [("i1", {"Summits": "Gscheuerkopf (1180 m)", "SummitCount": 1, "HighestPoint": 1190}),
                           ("i2", {"SummitCount": 1, "HighestPoint": 1190})]           # the typed value stays
    assert session.posts == 1                                                           # cells cached
    ctx.iv.puts.clear()
    sync(ctx, apply=True, today=date(2026, 10, 31))
    assert ctx.iv.puts == []


def test_a_failed_write_does_not_stop_the_others(tmp_path):
    import requests
    acts = [hike("i1", "2026-10-30"), hike("i2", "2026-10-30")]
    ctx, _ = make(tmp_path, acts, {"i1": STREAMS, "i2": STREAMS})
    real = ctx.iv.update_activity

    def flaky(aid, values):
        if aid == "i1":
            raise requests.HTTPError("502 Server Error")
        return real(aid, values)
    ctx.iv.update_activity = flaky
    sync(ctx, apply=True, today=date(2026, 10, 31))
    assert ctx.counts["write_failed"] == 1 and [p[0] for p in ctx.iv.puts] == ["i2"]
    ctx.iv.update_activity = real                                   # next run: i1 gets its values
    sync(ctx, apply=True, today=date(2026, 10, 31))
    assert [p[0] for p in ctx.iv.puts] == ["i2", "i1"]


def test_track_not_there_yet_is_asked_again(tmp_path):
    acts = [hike("i1", "2026-10-31")]
    ctx, _ = make(tmp_path, acts, {"i1": []})                      # just uploaded: no streams yet
    sync(ctx, apply=True, today=date(2026, 10, 31))
    assert ctx.counts["no_gps"] == 1 and ctx.iv.puts == []
    ctx.iv.streams_by_id["i1"] = STREAMS
    sync(ctx, apply=True, today=date(2026, 10, 31))
    assert ctx.iv.puts and ctx.iv.puts[0][1]["Summits"] == "Gscheuerkopf (1180 m)"
    ctx.counts.clear()
    sync(ctx, apply=True, today=date(2026, 11, 10))                 # an old one without GPS stays as it is
    assert ctx.counts["matched"] == 0


def test_description_line_is_opt_in_and_written_once(tmp_path):
    acts = [hike("i1", "2026-10-30", description="Nice day")]
    ctx, _ = make(tmp_path, acts, {"i1": STREAMS}, description=True, fields=("Summits",))
    sync(ctx, apply=True, today=date(2026, 10, 31))
    assert ctx.iv.puts == [("i1", {"Summits": "Gscheuerkopf (1180 m)", "description": "Nice day\n\n⛰️ Summits: Gscheuerkopf (1180 m)"})]
    ctx.iv.puts.clear()
    sync(ctx, apply=True, today=date(2026, 10, 31))
    assert ctx.iv.puts == []


def test_page_renders_and_names_are_safe(tmp_path):
    ctx, _ = make(tmp_path, [hike("i1", "2026-10-30", name="</script><b>x")], {"i1": STREAMS})
    sync(ctx, apply=False, today=date(2026, 10, 31))
    html = page.render(ctx.store, "de")
    assert html.count("</script>") == 1 and "Gscheuerkopf" in html and "Gipfelbuch" in html
    script = html.split("<script>")[1]
    # a top-level declaration named like a window property breaks the whole page (function top() did)
    declared = set(re.findall(r"(?:^|[;\n])\s*(?:const|let|var|function)\s+([A-Za-z_$][\w$]*)", script))
    declared |= set(re.findall(r",\s*([A-Za-z_$][\w$]*)\s*=", script.split("\n", 1)[0]))
    assert not declared & {"top", "name", "status", "parent", "self", "length", "window", "document", "location",
                           "open", "close", "stop", "print", "event", "origin", "history", "frames", "opener"}


def _browser() -> bool:
    if not shutil.which("node"):
        return False
    probe = "for (const m of [process.env.PLAYWRIGHT_CORE, 'playwright', 'playwright-core'].filter(Boolean)) " \
            "{ try { require.resolve(m); process.exit(0) } catch (e) {} } process.exit(1)"
    return subprocess.run(["node", "-e", probe], capture_output=True).returncode == 0


@pytest.mark.skipif(not _browser(), reason="no playwright here (npm install playwright)")
def test_page_runs_in_a_browser(tmp_path):
    ctx, _ = make(tmp_path, [hike("i1", "2026-10-30")], {"i1": STREAMS})
    sync(ctx, apply=False, today=date(2026, 10, 31))
    html_file = tmp_path / "p.html"
    page.write(ctx.store, html_file, "en")
    out = subprocess.run(["node", str(Path(__file__).with_name("browser_check.js")), str(html_file)],
                         capture_output=True, text=True, timeout=120)
    assert out.returncode == 0, out.stdout + out.stderr
    assert "kpis=1 entries" in out.stdout
