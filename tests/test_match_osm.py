from intervals_summits.match import Rules, visits
from intervals_summits.osm import CELL, areas, bbox, cells_for, parse

PEAK = {"osm": "node/1", "name": "Gscheuerkopf", "kind": "peak", "ele": 1180.0, "lat": 47.5, "lon": 12.4, "names": {"en": "Gscheuer Head"}}
HUT = {"osm": "node/2", "name": "Gaudeamushütte", "kind": "hut", "ele": 1263.0, "lat": 47.51, "lon": 12.41, "names": {}}


def track(points, alt):
    return {"lat": [p[0] for p in points], "lng": [p[1] for p in points], "alt": alt}


def test_peak_reached_within_radius_and_height():
    t = track([(47.499, 12.4), (47.4996, 12.4)], [1100, 1150])           # ~44 m away, 30 m below
    assert [v["name"] for v in visits(t, [PEAK])] == ["Gscheuerkopf"]


def test_peak_slope_below_does_not_count():
    t = track([(47.4996, 12.4)], [1050])                                # 130 m below the summit
    assert visits(t, [PEAK]) == []


def test_peak_too_far_and_hut_radius():
    t = track([(47.4985, 12.4), (47.5095, 12.41)], [1180, 1263])        # peak ~166 m, hut ~55 m
    assert [(v["name"], v["kind"]) for v in visits(t, [PEAK, HUT])] == [("Gaudeamushütte", "hut")]
    assert visits(t, [HUT], Rules(hut_radius=40)) == []


def test_order_dedup_and_language():
    twin = dict(PEAK, osm="node/3", lat=47.5001)                        # cross and summit, same name
    t = track([(47.5095, 12.41), (47.5, 12.4)], [1263, 1180])
    found = visits(t, [PEAK, twin, HUT])
    assert [v["name"] for v in found] == ["Gaudeamushütte", "Gscheuerkopf"]
    assert visits(t, [PEAK], language="en")[0]["name"] == "Gscheuer Head"


def test_on_a_summit_its_neighbour_does_not_count():
    halt = dict(PEAK, osm="node/4", name="Ellmauer Halt", ele=2342.0)
    tower = dict(PEAK, osm="node/5", name="Kapuzenturm", ele=2280.0, lon=12.4 + 94 / 75207)   # 94 m east
    t = track([(47.499, 12.4), (47.5, 12.4)], [2200, 2335])
    assert [v["name"] for v in visits(t, [halt, tower])] == ["Ellmauer Halt"]
    t = track([(47.5, 12.4 + 94 / 75207), (47.5, 12.4)], [2280, 2335])                     # on both
    assert [v["name"] for v in visits(t, [halt, tower])] == ["Kapuzenturm", "Ellmauer Halt"]
    twin = dict(tower, lon=12.4 + 20 / 75207)                                                # 20 m apart: both
    t = track([(47.499, 12.4), (47.5, 12.4)], [2200, 2335])
    assert {v["name"] for v in visits(t, [halt, twin])} == {"Ellmauer Halt", "Kapuzenturm"}


def test_peak_without_height_or_altitude_counts_by_distance():
    t = track([(47.4996, 12.4)], [None])
    found = visits(t, [dict(PEAK, ele=None)])
    assert len(found) == 1 and found[0]["ele"] is None and not found[0]["est"]


def test_a_place_without_height_takes_the_track_s_altitude_marked_as_estimate():
    from intervals_summits.fields import text
    t = track([(47.499, 12.4), (47.4999, 12.4)], [1100, 1176.4])
    found = visits(t, [dict(PEAK, ele=None)])
    assert found[0]["ele"] == 1176 and found[0]["est"] is True
    assert text(found, ("peak",)) == "Gscheuerkopf (≈1176 m)"
    assert visits(t, [PEAK])[0]["est"] is False and text(visits(t, [PEAK]), ("peak",)) == "Gscheuerkopf (1180 m)"


def test_cells_near_border_take_the_neighbour():
    inner = cells_for([47.5], [12.5])
    assert inner == {(int(47.5 // CELL), int(12.5 // CELL))}
    edge = cells_for([47.401], [12.5])                                  # 0.001° above a cell border
    assert len(edge) == 2


def test_areas_group_and_cut():
    cells = {(0, j) for j in range(10)} | {(5, 5)}
    groups = areas(cells)
    assert sorted(len(g) for g in groups) == [1, 4, 6]
    assert bbox({(1, 2), (2, 3)}) == (1 * CELL, 2 * CELL, 3 * CELL, 4 * CELL)


def test_parse_kinds():
    els = [{"type": "node", "id": 1, "lat": 47.5, "lon": 12.4, "tags": {"natural": "peak", "name": "A", "ele": "1180,5", "name:en": "A en"}},
           {"type": "node", "id": 2, "lat": 47.5, "lon": 12.4, "tags": {"natural": "saddle", "name": "B"}},
           {"type": "way", "id": 3, "center": {"lat": 47.5, "lon": 12.4}, "tags": {"tourism": "alpine_hut", "name": "C"}},
           {"type": "node", "id": 4, "lat": 47.5, "lon": 12.4, "tags": {"natural": "peak"}}]
    got = {p["name"]: p for p in parse(els)}
    assert got["A"]["kind"] == "peak" and got["A"]["ele"] == 1180.5 and got["A"]["names"] == {"en": "A en"}
    assert got["B"]["kind"] == "pass" and got["C"]["kind"] == "hut" and len(got) == 3
