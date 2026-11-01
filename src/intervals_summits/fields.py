"""The Intervals activity fields: their definitions, the values for an activity, and when to write.

Codes are the same for everyone (charts and scripts keep working); names follow SUMMITS_LANGUAGE
and may be renamed in Intervals at will – the tool goes by the code.

A value is written when the field is empty, or when it still holds what this tool wrote last time.
A value someone typed or another tool wrote is kept (unless --force). HighestPoint is only ever
filled when empty: Intervals fills it from a FIT file itself (session enhanced_max_altitude).

Optional (SUMMITS_DESCRIPTION=true): one line "⛰️ Summits: … · Huts: … · Passes: …" in the activity
description, because Intervals' search looks at names and descriptions, not at custom fields. Huts and
passes come into it when their fields are on, and only when there were some. Only that line is ever
touched; the rest of the description stays as it is.
"""
from __future__ import annotations

import json
import logging

log = logging.getLogger(__name__)
ATTRIBUTION = "© OpenStreetMap contributors"

DEFS = {
    "Summits": {"names": {"en": "Summits", "de": "Gipfel"}, "type": "text", "icon": "mdi-flag-triangle",
                "description": f"Summits reached on the activity, in order (OpenStreetMap peaks within 100 m of the track; {ATTRIBUTION})"},
    "SummitCount": {"names": {"en": "Summit count", "de": "Gipfelanzahl"}, "type": "numeric", "icon": "mdi-flag-triangle",
                    "aggregate": "SUM", "number_format": ".0f",
                    "description": "Number of summits reached on the activity (intervals-summits)"},
    "HighestPoint": {"names": {"en": "Highest point", "de": "Höchster Punkt"}, "type": "numeric",
                     "icon": "mdi-image-filter-hdr", "aggregate": "MAX", "units": "m", "suffix": "m", "number_format": ".0f",
                     "fit_session_field": "enhanced_max_altitude",
                     "description": "Highest point of the activity (m): from the FIT file (session enhanced_max_altitude); "
                                    "otherwise from the altitude stream (intervals-summits)"},
    "Huts": {"names": {"en": "Huts", "de": "Hütten"}, "type": "text", "icon": "mdi-home-variant",
             "description": f"Huts on the activity, in order (OpenStreetMap alpine and wilderness huts within 60 m; {ATTRIBUTION})"},
    "Passes": {"names": {"en": "Passes", "de": "Pässe"}, "type": "text", "icon": "mdi-swap-horizontal",
               "description": f"Passes and saddles on the activity, in order (OpenStreetMap, within 60 m; {ATTRIBUTION})"},
    # the field of 0.1: huts and passes in one, kept for whoever has it
    "HutsPasses": {"names": {"en": "Huts & passes", "de": "Hütten & Pässe"}, "type": "text", "icon": "mdi-home-variant",
                   "description": f"Huts and passes on the activity, in order (OpenStreetMap; {ATTRIBUTION})"},
}


def item(code: str, language: str) -> dict:
    d = DEFS[code]
    name = d["names"].get(language, d["names"]["en"])
    content = {"code": code, "name": name, "type": d["type"], "icon": d["icon"], "inline": True,
               "fit_session_field": d.get("fit_session_field"), "script": None, "processes_fit_messages": False}
    for key in ("aggregate", "number_format", "units", "suffix"):
        if key in d:
            content[key] = d[key]
    if d["type"] == "text":
        content["text_wrap"] = True
    return {"type": "ACTIVITY_FIELD", "visibility": "PRIVATE", "name": name, "description": d["description"], "content": content}


def ensure(iv, codes: tuple[str, ...], language: str, apply: bool) -> dict:
    """Create the fields that are missing (with the next free index, else Intervals' pickers hide them)."""
    items = [i for i in iv.custom_items() if i.get("type") == "ACTIVITY_FIELD"]
    present = {(i.get("content") or {}).get("code") for i in items}
    missing = [c for c in codes if c not in present]
    if apply and missing:
        top = max((i.get("index") or 0 for i in items), default=0)
        for code in missing:
            created = iv.create_custom_item(item(code, language)) or {}
            if created.get("id"):
                top += 1
                iv.reorder_custom_items([dict(created, index=top)])
            log.info("Created the activity field %s", code)
    return {"present": sorted(c for c in codes if c in present), "missing": missing}


def text(visits: list[dict], kinds: tuple[str, ...]) -> str | None:
    """"Name (2231 m)"; "≈" marks a height from the track where OpenStreetMap has none."""
    parts = [f"{v['name']} ({'≈' if v.get('est') else ''}{round(v['ele'])} m)" if v.get("ele") is not None else v["name"]
             for v in visits if v["kind"] in kinds]
    return ", ".join(parts) or None


def wanted(visits: list[dict], max_alt: float | None, codes: tuple[str, ...]) -> dict:
    out = {}
    if "Summits" in codes:
        out["Summits"] = text(visits, ("peak",))
    if "SummitCount" in codes:
        out["SummitCount"] = sum(1 for v in visits if v["kind"] == "peak") or None
    if "HighestPoint" in codes:
        out["HighestPoint"] = round(max_alt) if max_alt is not None else None
    if "Huts" in codes:
        out["Huts"] = text(visits, ("hut",))
    if "Passes" in codes:
        out["Passes"] = text(visits, ("pass",))
    if "HutsPasses" in codes:
        out["HutsPasses"] = text(visits, ("hut", "pass"))
    return out


def line_kinds(codes: tuple[str, ...]) -> tuple[str, ...]:
    """What the description line names: summits, and huts and passes when their fields are on."""
    huts = "Huts" in codes or "HutsPasses" in codes
    passes = "Passes" in codes or "HutsPasses" in codes
    return ("peak",) + (("hut",) if huts else ()) + (("pass",) if passes else ())


def same(a, b) -> bool:
    if a in (None, "") or b in (None, ""):
        return a in (None, "") and b in (None, "")
    if isinstance(a, (int, float)) or isinstance(b, (int, float)):
        try:
            return abs(float(a) - float(b)) < 0.5
        except (TypeError, ValueError):
            return False
    return str(a).strip() == str(b).strip()


def decide(code: str, want, current, last: str | None, force: bool = False) -> str:
    """write | same | kept (someone else's value) | none (nothing to write)."""
    if want is None:
        return "none"
    if same(current, want):
        return "same"
    if current in (None, ""):
        return "write"
    if code == "HighestPoint":
        return "kept"
    if force or (last is not None and same(current, json.loads(last))):
        return "write"
    return "kept"


DESCRIPTION_LABELS = {"en": {"peak": "Summits", "hut": "Huts", "pass": "Passes"},
                      "de": {"peak": "Gipfel", "hut": "Hütten", "pass": "Pässe"}}
MOUNTAIN = "\u26f0\ufe0f"
_LABELS = {label for labels in DESCRIPTION_LABELS.values() for label in labels.values()}


def is_our_line(line: str) -> bool:
    s = line.strip().lstrip("\u26f0\ufe0f").strip()
    return line.strip().startswith("\u26f0") and any(s.startswith(f"{label}:") for label in _LABELS)


def description_line(visits: list[dict], description: str | None, language: str,
                     kinds: tuple[str, ...] = ("peak",)) -> str | None:
    """None when there is nothing of these kinds, or when the description names it all already
    (another tool's lines). Summits, huts, passes – each part only when there were some."""
    named = [v for v in visits if v["kind"] in kinds]
    if not named:
        return None
    rest = "\n".join(line for line in (description or "").split("\n") if not is_our_line(line))
    if all(v["name"] in rest for v in named):
        return None
    labels = DESCRIPTION_LABELS.get(language, DESCRIPTION_LABELS["en"])
    parts = [f"{labels[k]}: {text(named, (k,))}" for k in ("peak", "hut", "pass") if k in kinds and text(named, (k,))]
    return f"{MOUNTAIN} " + " · ".join(parts)


def our_line(description: str | None) -> str | None:
    return next((line.strip() for line in (description or "").split("\n") if is_our_line(line)), None)


def with_line(description: str | None, line: str) -> str:
    """The description with our line replaced, or appended after a blank line: the rest stays exactly as it is."""
    text = description or ""
    lines = text.split("\n")
    at = [i for i, x in enumerate(lines) if is_our_line(x)]
    if not at:
        if not text.strip():
            return line
        return text + ("" if text.endswith("\n\n") else "\n" if text.endswith("\n") else "\n\n") + line
    lines[at[0]] = line + ("\r" if lines[at[0]].endswith("\r") else "")
    return "\n".join(x for i, x in enumerate(lines) if i not in at[1:])


def keeps_text(old: str | None, new: str) -> bool:
    """The last check before a description is written: all of the user's text is still there, unchanged."""
    old = old or ""
    if our_line(old) is None:
        start = old if old.strip() else ""
        added = new[len(start):].strip()
        return new.startswith(start) and "\n" not in added and is_our_line(added)
    return [x for x in old.split("\n") if not is_our_line(x)] == [x for x in new.split("\n") if not is_our_line(x)]
