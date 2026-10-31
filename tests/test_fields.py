import json

from intervals_summits import fields as F

VISITS = [{"name": "Hütte", "kind": "hut", "ele": 1263.0}, {"name": "Gscheuerkopf", "kind": "peak", "ele": 1180.4},
          {"name": "Ursulablick", "kind": "peak", "ele": None}, {"name": "Pass", "kind": "pass", "ele": 900.0}]


def test_wanted_values():
    want = F.wanted(VISITS, 1190.6, ("Summits", "SummitCount", "HighestPoint", "HutsPasses"))
    assert want == {"Summits": "Gscheuerkopf (1180 m), Ursulablick", "SummitCount": 2, "HighestPoint": 1191,
                    "HutsPasses": "Hütte (1263 m), Pass (900 m)"}
    assert F.wanted([], None, ("Summits", "SummitCount", "HighestPoint")) == {"Summits": None, "SummitCount": None, "HighestPoint": None}


def test_decide():
    mine = json.dumps("A (1 m)")
    assert F.decide("Summits", "A (1 m)", None, None) == "write"
    assert F.decide("Summits", "A (1 m)", "A (1 m)", None) == "same"
    assert F.decide("Summits", "B (2 m)", "A (1 m)", mine) == "write"          # still ours: updated
    assert F.decide("Summits", "B (2 m)", "typed by hand", mine) == "kept"
    assert F.decide("Summits", "B (2 m)", "typed by hand", mine, force=True) == "write"
    assert F.decide("Summits", None, "A (1 m)", mine) == "none"
    assert F.decide("SummitCount", 2, 2.0, None) == "same"
    assert F.decide("HighestPoint", 1191, None, None) == "write"
    assert F.decide("HighestPoint", 1191, 1188.0, json.dumps(1188), force=True) == "kept"   # a FIT value stays


def test_item_names_follow_language():
    assert F.item("Summits", "de")["name"] == "Gipfel"
    en = F.item("HighestPoint", "en")
    assert en["name"] == "Highest point" and en["content"]["code"] == "HighestPoint" and en["content"]["aggregate"] == "MAX"
    assert F.item("Summits", "en")["content"]["text_wrap"] is True


class FakeItems:
    def __init__(self, items):
        self.items, self.created, self.reordered = items, [], []

    def custom_items(self):
        return self.items

    def create_custom_item(self, item):
        self.created.append(item)
        return dict(item, id=100 + len(self.created), index=0)

    def reorder_custom_items(self, items):
        self.reordered += items


def test_ensure_creates_missing_with_next_index():
    iv = FakeItems([{"type": "ACTIVITY_FIELD", "index": 7, "content": {"code": "HighestPoint"}}])
    assert F.ensure(iv, ("Summits", "HighestPoint"), "en", False) == {"present": ["HighestPoint"], "missing": ["Summits"]}
    assert iv.created == []
    F.ensure(iv, ("Summits", "HighestPoint"), "en", True)
    assert [c["content"]["code"] for c in iv.created] == ["Summits"] and iv.reordered[0]["index"] == 8


def test_description_line():
    peaks = [{"name": "Maukspitze", "kind": "peak", "ele": 2231.0}, {"name": "Ackerlhütte", "kind": "hut", "ele": 1455.0}]
    line = F.description_line(peaks, "Great day", "en")
    assert line == "⛰️ Summits: Maukspitze (2231 m)"
    assert F.with_line("Great day", line) == "Great day\n\n⛰️ Summits: Maukspitze (2231 m)"
    assert F.with_line(None, line) == line
    assert F.our_line(F.with_line("Great day", line)) == line
    # our line replaced in place, the rest untouched; both languages are recognised
    old = "Great day\n⛰️ Gipfel: Ellmauer Halt (2344 m)\nwith friends"
    assert F.with_line(old, line) == "Great day\n⛰️ Summits: Maukspitze (2231 m)\nwith friends"
    # peakproject's lines already name the summit: nothing to add
    assert F.description_line(peaks, "⛰️ Maukspitze (2231 m)", "en") is None
    assert F.description_line([peaks[1]], "", "en") is None
    # a hand-edited line is kept, our own is updated
    assert F.decide("description", line, "⛰️ Summits: typed", json.dumps("⛰️ Summits: old")) == "kept"
    assert F.decide("description", line, "⛰️ Summits: old", json.dumps("⛰️ Summits: old")) == "write"
