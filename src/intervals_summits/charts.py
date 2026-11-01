"""Ready-made Intervals fitness charts for the summit fields: private items in your account.

A plot of an activity field is "af_<code>" with the field's own item embedded (filter customInput),
as Intervals' chart editor stores it. A chart is made once one of its fields exists; a chart this
tool made earlier (its description says so) is brought up to date; a chart of yours is never touched.
"""
from __future__ import annotations

import secrets
from typing import Any

MARK = "Created by intervals-summits for its fields: https://forum.intervals.icu/t/133380"
# (code, legend, type, aggregation, fill, stroke, scale): one y axis per scale
CHARTS: list[dict[str, Any]] = [
    {
        "name": "Intervals Summits: per month",
        "title": "Summits per month, the highest point of each day",
        "y": "Summits", "y2": "m", "height": 180,
        "plots": [("SummitCount", "Summits", "bars", "month_tot", "#0B8FB399", "#0B8FB3FF", "count"),
                  ("HighestPoint", "Highest", "dot", "none", "#7C3AED55", "#7C3AEDFF", "m")],
    },
    {
        "name": "Intervals Summits: per week",
        "title": "Summits per week, the highest point of each day",
        "y": "Summits", "y2": "m", "height": 180,
        "plots": [("SummitCount", "Summits", "bars", "week_tot", "#0B8FB399", "#0B8FB3FF", "count"),
                  ("HighestPoint", "Highest", "dot", "none", "#7C3AED55", "#7C3AEDFF", "m")],
    },
]
_KEYS = ("field", "text", "type", "agg", "fill", "stroke", "scale")


def _plot(index: int, spec: tuple, field_item: dict) -> dict:
    code, text, ptype, agg, fill, stroke, scale = spec
    return {"id": index, "field": f"af_{code}", "filter": "customInput", "tickFormat": "customInput",
            "customInput": field_item, "text": text, "title": field_item.get("name") or code, "type": ptype, "agg": agg,
            "fill": fill, "stroke": stroke, "strokeWidth": 1, "radius": 3, "gauge": True, "scale": scale, "stack": "",
            "band": 0, "min": 0, "extras": [], "filters": [], "markerValue": "right-inline", "invertSubWellness": False}


def ours(item: dict) -> bool:
    return str(item.get("description") or "").startswith("Created by intervals-summits")


def plan(custom_items: list[dict]) -> dict:
    fields = {(it.get("content") or {}).get("code"): it for it in custom_items if it.get("type") == "ACTIVITY_FIELD"}
    existing = {it.get("name"): it for it in custom_items if it.get("type") == "FITNESS_CHART"}
    create, update, skipped = [], [], {}
    for chart in CHARTS:
        plots = [_plot(i, spec, fields[spec[0]]) for i, spec in enumerate(chart["plots"], 1) if spec[0] in fields]
        if not plots:
            skipped[chart["name"]] = "none of its fields exist yet"
            continue
        present = existing.get(chart["name"])
        if present is not None:
            if not ours(present):
                skipped[chart["name"]] = "exists and was not made by intervals-summits"
                continue
            now = [tuple(str(p.get(k)) for k in _KEYS) for p in (present.get("content") or {}).get("plots", [])]
            if now == [tuple(str(p.get(k)) for k in _KEYS) for p in plots]:
                skipped[chart["name"]] = "up to date"
                continue
            content = dict(present.get("content") or {}, plots=plots, title=chart["title"],
                           yAxisLabel=chart["y"], y2AxisLabel=chart.get("y2"))
            update.append({"id": present["id"], "name": chart["name"], "type": "FITNESS_CHART",
                           "visibility": present.get("visibility", "PRIVATE"), "description": MARK, "content": content})
            continue
        content = {"id": secrets.token_hex(4), "name": chart["name"], "title": chart["title"], "plots": plots,
                   "height": chart["height"], "yAxisLabel": chart["y"], "y2AxisLabel": chart.get("y2"),
                   "yAxisMin": None, "yAxisMax": None, "y2AxisMin": None, "y2AxisMax": None, "y3AxisMin": None,
                   "y3AxisMax": None, "stackTo100Percent": None}
        create.append({"name": chart["name"], "type": "FITNESS_CHART", "visibility": "PRIVATE",
                       "description": MARK, "content": content})
    return {"create": create, "update": update, "skipped": skipped}


def setup(iv, *, apply: bool) -> dict:
    """Create or update the charts (a dry run without apply)."""
    items = iv.custom_items()
    p = plan(items)
    out = {"apply": apply, "create": [c["name"] for c in p["create"]], "update": [c["name"] for c in p["update"]],
           "skipped": p["skipped"], "created": [], "updated": []}
    if not apply:
        return out
    top = max((it.get("index") or 0 for it in items if it.get("type") == "FITNESS_CHART"), default=0)
    for chart in p["create"]:
        created = iv.create_custom_item(chart) or {}
        if created.get("id"):
            top += 1                                   # a new item lands at index 0, where the picker hides it
            iv.reorder_custom_items([dict(created, index=top)])
        out["created"].append({"name": chart["name"], "id": created.get("id")})
    for chart in p["update"]:
        iv.update_custom_item(chart["id"], chart)
        out["updated"].append({"name": chart["name"], "id": chart["id"]})
    return out
