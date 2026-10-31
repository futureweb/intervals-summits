"""The Intervals activity fields: their definitions, the values for an activity, and when to write.

Codes are the same for everyone (charts and scripts keep working); names follow SUMMITS_LANGUAGE
and may be renamed in Intervals at will – the tool goes by the code.

A value is written when the field is empty, or when it still holds what this tool wrote last time.
A value someone typed or another tool wrote is kept (unless --force). HighestPoint is only ever
filled when empty: Intervals fills it from a FIT file itself (session enhanced_max_altitude).

Optional (SUMMITS_DESCRIPTION=true): one line "⛰️ Summits: …" in the activity description, because
Intervals' search looks at names and descriptions, not at custom fields. Only that line is ever
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
    parts = [f"{v['name']} ({round(v['ele'])} m)" if v.get("ele") is not None else v["name"]
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
    if "HutsPasses" in codes:
        out["HutsPasses"] = text(visits, ("hut", "pass"))
    return out


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


DESCRIPTION_LABELS = {"en": "Summits", "de": "Gipfel"}
MOUNTAIN = "\u26f0\ufe0f"


def is_our_line(line: str) -> bool:
    s = line.strip().lstrip("\u26f0\ufe0f").strip()
    return line.strip().startswith("\u26f0") and any(s.startswith(f"{label}:") for label in DESCRIPTION_LABELS.values())


def description_line(visits: list[dict], description: str | None, language: str) -> str | None:
    """None when there are no summits, or when the description names them all already (peakproject's lines)."""
    peaks = [v for v in visits if v["kind"] == "peak"]
    if not peaks:
        return None
    rest = "\n".join(line for line in (description or "").split("\n") if not is_our_line(line))
    if all(v["name"] in rest for v in peaks):
        return None
    return f"{MOUNTAIN} {DESCRIPTION_LABELS.get(language, 'Summits')}: {text(peaks, ('peak',))}"


def our_line(description: str | None) -> str | None:
    return next((line.strip() for line in (description or "").split("\n") if is_our_line(line)), None)


def with_line(description: str | None, line: str) -> str:
    """The description with our line replaced, or appended after a blank line."""
    lines = (description or "").split("\n")
    at = [i for i, x in enumerate(lines) if is_our_line(x)]
    if not at:
        base = (description or "").rstrip()
        return f"{base}\n\n{line}" if base else line
    lines[at[0]] = line
    return "\n".join(x for i, x in enumerate(lines) if i not in at[1:])
