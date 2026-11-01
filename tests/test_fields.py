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
    # the text stays exactly as it is: line ends, trailing newlines, Windows line breaks
    assert F.with_line("Great day\n", line) == "Great day\n\n" + line
    assert F.with_line("Great day\n\n", line) == "Great day\n\n" + line
    assert F.with_line("Great day  \r\nok", line) == "Great day  \r\nok\n\n" + line
    assert F.with_line("a\r\n⛰️ Summits: old\r\nb", line) == f"a\r\n{line}\r\nb"
    for text in (None, "", "Great day", "Great day\n", "a\r\nb ", old, "a\n⛰️ Summits: x\nb\n⛰️ Summits: y"):
        assert F.keeps_text(text, F.with_line(text, line))
    assert not F.keeps_text("Great day", "Great dax\n\n" + line)
    assert not F.keeps_text("Great day", "Great day\n\n" + line + "\nmore")
    assert not F.keeps_text("Great day", "Great day\n\nsomething else")
    assert not F.keeps_text(old, "Great day\n" + line)
    # another tool's lines already name the summit: nothing to add
    assert F.description_line(peaks, "⛰️ Maukspitze (2231 m)", "en") is None
    assert F.description_line([peaks[1]], "", "en") is None
    # a hand-edited line is kept, our own is updated
    assert F.decide("description", line, "⛰️ Summits: typed", json.dumps("⛰️ Summits: old")) == "kept"
    assert F.decide("description", line, "⛰️ Summits: old", json.dumps("⛰️ Summits: old")) == "write"


def test_description_line_with_huts_and_passes_only_when_there_were_some():
    visits = [{"name": "Maukspitze", "kind": "peak", "ele": 2231.0}, {"name": "Ackerlhütte", "kind": "hut", "ele": 1455.0},
              {"name": "Stripsenjoch", "kind": "pass", "ele": 1577.0}]
    kinds = F.line_kinds(("Summits", "Huts", "Passes"))
    assert kinds == ("peak", "hut", "pass") and F.line_kinds(("Summits", "HutsPasses")) == kinds
    assert F.line_kinds(("Summits",)) == ("peak",)
    line = F.description_line(visits, "", "en", kinds)
    assert line == "⛰️ Summits: Maukspitze (2231 m) · Huts: Ackerlhütte (1455 m) · Passes: Stripsenjoch (1577 m)"
    assert F.description_line(visits[1:2], "", "de", kinds) == "⛰️ Hütten: Ackerlhütte (1455 m)"   # a hut alone
    assert F.description_line(visits, "", "en") == "⛰️ Summits: Maukspitze (2231 m)"           # fields off: summits only
    assert F.description_line(visits[1:], "", "en") is None                                    # no summit, fields off
    # a line of either shape is ours: updated in place, never a second one
    old = "Great day\n⛰️ Summits: Maukspitze (2231 m)"
    assert F.with_line(old, line) == "Great day\n" + line and F.is_our_line("⛰️ Hütten: X") and F.is_our_line(line)
    assert F.keeps_text(old, F.with_line(old, line))
    assert F.wanted(visits, 2300, ("Huts", "Passes")) == {"Huts": "Ackerlhütte (1455 m)", "Passes": "Stripsenjoch (1577 m)"}
