import http.client
import json
import logging
import threading
from datetime import date, datetime, timedelta

import pytest

from intervals_summits import cli
from intervals_summits.config import load
from intervals_summits.sync import sync
from test_sync_page import STREAMS, hike, make


def test_rules_can_be_set_within_limits():
    s = load({"INTERVALS_API_KEY": "x", "SUMMITS_PEAK_RADIUS": "50", "SUMMITS_PEAK_BELOW": "30", "SUMMITS_PASS_RADIUS": "80"})
    assert (s.peak_radius, s.peak_below, s.hut_radius, s.pass_radius) == (50, 30, 60, 80)
    with pytest.raises(SystemExit, match="10 to 200"):
        load({"INTERVALS_API_KEY": "x", "SUMMITS_PEAK_RADIUS": "500"})
    with pytest.raises(SystemExit, match="number of metres"):
        load({"INTERVALS_API_KEY": "x", "SUMMITS_HUT_RADIUS": "far"})


def test_changed_rules_are_pointed_out(tmp_path, caplog):
    ctx, _ = make(tmp_path, [], {})
    sync(ctx, apply=True, today=date(2026, 10, 31))
    ctx.settings.peak_radius = 50
    with caplog.at_level(logging.WARNING):
        sync(ctx, apply=True, today=date(2026, 10, 31))
    assert "recompute" in caplog.text and "50/80/60/60" in caplog.text


def post(port, path, body=b"{}"):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    conn.request("POST", path, body, {"Content-Type": "application/json"})
    status = conn.getresponse().status
    conn.close()
    return status


def test_post_sync_wakes_the_run_loop(tmp_path):
    ctx, _ = make(tmp_path, [], {})
    wake = threading.Event()
    server = cli.serve(ctx.settings, "127.0.0.1", 0, wake)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    port = server.server_address[1]
    try:
        assert post(port, "/nothing") == 404 and not wake.is_set()
        assert post(port, "/sync", b"not json") == 202 and wake.is_set()
        wake.clear()
        assert post(port, "/sync", json.dumps({"source": "garmin-intervals-bridge", "new": 1}).encode()) == 202
        assert wake.is_set()
    finally:
        server.shutdown()
    plain = cli.serve(ctx.settings, "127.0.0.1", 0)            # `ui` alone has no loop to wake
    threading.Thread(target=plain.serve_forever, daemon=True).start()
    try:
        assert post(plain.server_address[1], "/sync") == 404
    finally:
        plain.shutdown()


def test_bridge_notes_slow_down_own_polling(tmp_path):
    acts = [hike("i1", "2026-10-30")]
    ctx, _ = make(tmp_path, acts, {"i1": STREAMS}, interval_minutes=15)
    assert cli.poll_minutes(ctx) == 15
    wake, slept = threading.Event(), []
    wake.set()                                                   # the bridge reported while the first sync ran
    cli.run_loop(ctx, apply=True, wake=wake, iterations=2, sleep=slept.append)
    assert slept and not wake.is_set()
    assert ctx.store.get("notified_at") and cli.poll_minutes(ctx) == cli.QUIET_MINUTES
    later = datetime.now() + timedelta(days=cli.NOTIFIED_DAYS + 1)
    assert cli.poll_minutes(ctx, later) == 15                    # the bridge went quiet: look every 15 minutes again
    ctx.store.put("last_sync_at", (datetime.now() - timedelta(hours=4)).isoformat(timespec="seconds"))
    assert cli.healthy(ctx)[0]                                   # 4 hours is fine while the bridge reports
    assert not cli.healthy(ctx, later)[0]
