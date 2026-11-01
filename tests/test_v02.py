"""0.2: huts and passes fields, Wikipedia links, the map, first visits, collections, the Intervals charts."""
import re
import sqlite3
from datetime import date

import pytest

from intervals_summits import charts, page
from intervals_summits.config import Collection, collections, load
from intervals_summits.osm import area_filter, collection_members, parse, wiki_url
from intervals_summits.store import Store
from intervals_summits.sync import sync
from test_sync_page import PEAK_EL, STREAMS, hike, make


def field(code, i):
    return {"id": i, "type": "ACTIVITY_FIELD", "name": code, "content": {"code": code, "name": code}}


class Charts:
    def __init__(self, items):
        self.items, self.created, self.updated, self.reordered = items, [], [], []

    def custom_items(self):
        return self.items

    def create_custom_item(self, item):
        self.created.append(item)
        return {"id": 900 + len(self.created), **item}

    def update_custom_item(self, item_id, item):
        self.updated.append((item_id, item))

    def reorder_custom_items(self, items):
        self.reordered.extend(items)


def test_charts_made_with_the_fields_kept_up_to_date_and_foreign_ones_untouched():
    iv = Charts([field("SummitCount", 1), field("HighestPoint", 2), {"type": "FITNESS_CHART", "name": "Mine", "index": 7}])
    out = charts.setup(iv, apply=True)
    assert out["created"] and [c["name"] for c in iv.created] == ["Intervals Summits: per month", "Intervals Summits: per week"]
    plots = iv.created[0]["content"]["plots"]
    assert [p["field"] for p in plots] == ["af_SummitCount", "af_HighestPoint"] and plots[0]["agg"] == "month_tot"
    assert plots[0]["filter"] == "customInput" and plots[0]["customInput"]["content"]["code"] == "SummitCount"
    assert [r["index"] for r in iv.reordered] == [8, 9]                  # after the charts already there
    # made earlier with SummitCount only: HighestPoint joins; a chart of the same name not made by us stays
    old = dict(iv.created[0], id=901, content=dict(iv.created[0]["content"], plots=plots[:1]))
    foreign = {"type": "FITNESS_CHART", "name": "Intervals Summits: per week", "id": 5, "description": "mine"}
    p = charts.plan([field("SummitCount", 1), field("HighestPoint", 2), old, foreign])
    assert [c["id"] for c in p["update"]] == [901] and p["create"] == []
    assert "not made by intervals-summits" in p["skipped"]["Intervals Summits: per week"]
    assert charts.plan([])["skipped"]["Intervals Summits: per month"] == "none of its fields exist yet"


def test_wikipedia_links_and_collection_members():
    pois = parse([{**PEAK_EL, "tags": {**PEAK_EL["tags"], "wikipedia": "de:Gscheuerkopf"}},
                  {"type": "node", "id": 2, "lat": 47.6, "lon": 12.5, "tags": {"natural": "peak", "name": "Q", "wikidata": "Q42"}}])
    assert [p["wiki"] for p in pois] == ["de:Gscheuerkopf", "wikidata:Q42"]
    assert wiki_url("de:Ellmauer Halt") == "https://de.wikipedia.org/wiki/Ellmauer_Halt"
    assert wiki_url("wikidata:Q42") == "https://www.wikidata.org/wiki/Q42" and wiki_url("x") is None
    els = [{"type": "node", "id": 1, "lat": 47.0, "lon": 11.0, "tags": {"name": "A", "ele": "3012"}},
           {"type": "node", "id": 2, "lat": 47.1, "lon": 11.1, "tags": {"name": "B", "ele": "2900"}},
           {"type": "node", "id": 3, "lat": 47.2, "lon": 11.2, "tags": {"name": "C"}}]
    assert [m["name"] for m in collection_members(els, 3000)] == ["A"] and len(collection_members(els)) == 3
    assert area_filter("r52343") == "area(id:3600052343)" and area_filter('Ti"rol') == 'area["name"="Ti\\"rol"]'


def test_settings_for_collections_map_and_charts():
    assert collections("Tirol 3000ers=Tirol>=3000; Kaisergebirge") == (Collection("Tirol 3000ers", "Tirol", 3000),
                                                                       Collection("Kaisergebirge", "Kaisergebirge", 0))
    with pytest.raises(SystemExit):
        collections("=>=3000")
    base = {"INTERVALS_API_KEY": "x"}
    assert load(base).map_tiles["url"].startswith("https://{s}.tile.opentopomap.org")
    assert load({**base, "SUMMITS_MAP_TILES": "off"}).map_tiles is None
    with pytest.raises(SystemExit):
        load({**base, "SUMMITS_MAP_TILES": "http://insecure/{z}/{x}/{y}.png"})
    assert load({**base, "SUMMITS_CHARTS": "false"}).charts is False
    assert load({**base, "SUMMITS_FIELDS": "Summits,Huts,Passes"}).fields == ("Summits", "Huts", "Passes")


def test_an_old_database_gets_the_wiki_column_and_reads_its_cells_again(tmp_path):
    db = tmp_path / "summits.sqlite"
    con = sqlite3.connect(db)
    con.executescript("CREATE TABLE pois(osm TEXT PRIMARY KEY, name TEXT, names TEXT, kind TEXT, ele REAL, lat REAL, "
                      "lon REAL, ci INTEGER, cj INTEGER); CREATE TABLE cells(ci INTEGER, cj INTEGER, fetched_at TEXT, "
                      "PRIMARY KEY(ci, cj)); INSERT INTO cells VALUES (1, 2, '2026-11-01T00:00:00+00:00');")
    con.commit()
    con.close()
    store = Store(db, tmp_path / "tracks")
    assert "wiki" in {r[1] for r in store.db.execute("PRAGMA table_info(pois)")}
    assert store.cell_fetched((1, 2)).startswith("1970")


def test_collections_are_read_once_and_shown_with_first_visits_map_and_links(tmp_path):
    ctx, session = make(tmp_path, [hike("i1", "2026-10-30", name="__DATA__ </script>")], {"i1": STREAMS},
                        collections=(Collection("Hausberge", "Kitzbühel"),))
    sync(ctx, apply=False, today=date(2026, 10, 31))
    assert ctx.store.collection("Kitzbühel>=0")["members"][0]["name"] == "Gscheuerkopf" and session.posts == 2
    sync(ctx, apply=False, today=date(2026, 10, 31))
    assert session.posts == 2                                             # kept: no second query
    html = page.render(ctx.store, "en", tiles={"url": "https://t/{z}/{x}/{y}.png", "attribution": "a"},
                       wanted=ctx.settings.collections)
    data = re.search(r"const V=(.*?),P=(.*?),C=(.*?),T=", html).groups()
    assert '"osm": "node/1"' in data[0] and '"node/1": [47.5, 12.4' in data[1] and '"Hausberge"' in data[2]
    assert html.count("</script>") == 1 and "cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4" in html


def test_the_page_can_go_to_a_web_folder_in_its_own_language_and_be_read_there(tmp_path):
    import os
    s = load({"INTERVALS_API_KEY": "x", "SUMMITS_LANGUAGE": "en", "SUMMITS_PAGE_LANGUAGE": "de",
              "SUMMITS_PAGE_FILE": str(tmp_path / "web" / "index.html"), "SUMMITS_DATA_DIR": str(tmp_path / "data")})
    assert s.page_file == tmp_path / "web" / "index.html" and s.page_lang == "de" and s.language == "en"
    store = Store(s.db_file, s.tracks_dir)
    old = os.umask(0o027)
    try:
        page.write(store, s.page_file, s.page_lang)
    finally:
        os.umask(old)
    assert oct(s.page_file.stat().st_mode & 0o777) == "0o640" and "Gipfelbuch" in s.page_file.read_text()
