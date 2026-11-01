"""A summit log with made-up activities on well-known summits, for screenshots and to try the page.

    python examples/demo.py demo.html [en|de]

Nothing is read from or written to Intervals; the activity links lead nowhere.
"""
from __future__ import annotations

import random
import sys
import tempfile
import zlib
from datetime import date, timedelta
from pathlib import Path

from intervals_summits import page
from intervals_summits.config import OPENTOPOMAP, Collection
from intervals_summits.store import Store

# where they are (rounded), for the map
WHERE = {"Patscherkofel": (47.2087, 11.4611), "Nockspitze": (47.1990, 11.3160), "Serles": (47.1222, 11.3825),
         "Glungezer": (47.2047, 11.5258), "Salzburger Hochthron": (47.7310, 12.9940), "Zeppezauerhaus": (47.7240, 13.0150),
         "Schafberg": (47.7765, 13.4344), "Hoher Göll": (47.5947, 13.0647), "Purtschellerhaus": (47.6000, 13.0570),
         "Rosskogel": (47.2244, 11.1828), "Pirchkogel": (47.2235, 11.0460), "Lampsenspitze": (47.1720, 11.1090),
         "Zischgeles": (47.1480, 11.0650), "Kitzsteinhorn": (47.1880, 12.6870), "Großglockner": (47.0742, 12.6947),
         "Erzherzog-Johann-Hütte": (47.0687, 12.6928), "Stüdlhütte": (47.0587, 12.6730), "Wildspitze": (46.8853, 10.8672),
         "Breslauer Hütte": (46.8783, 10.8900), "Großvenediger": (47.1092, 12.3461), "Kürsingerhütte": (47.1336, 12.3528),
         "Olperer": (47.0558, 11.6603), "Olpererhütte": (47.0450, 11.6800), "Habicht": (47.0430, 11.2880),
         "Innsbrucker Hütte": (47.0961, 11.3456), "Zuckerhütl": (46.9658, 11.1531), "Dresdner Hütte": (47.0050, 11.1470),
         "Weißkugel": (46.7972, 10.7272), "Weißkugelhütte": (46.8156, 10.7414), "Großes Wiesbachhorn": (47.1567, 12.7558),
         "Heinrich-Schwaiger-Haus": (47.1600, 12.7400), "Hochfeiler": (46.9725, 11.7275), "Hochfeilerhütte": (46.9800, 11.7240),
         "Hochkönig": (47.4200, 13.0650), "Matrashaus": (47.4202, 13.0662), "Timmelsjoch": (46.9064, 11.0956),
         "Hochtor": (47.0820, 12.8430), "Kühtaisattel": (47.2140, 11.0270), "Brennerpass": (47.0030, 11.5070),
         "Arlbergpass": (47.1286, 10.2110), "Fernpass": (47.3620, 10.8350)}
# a collection: the 3000ers of the Hohe Tauern (a few of them)
TAUERN = Collection("Hohe Tauern 3000ers", "Hohe Tauern", 3000)
TAUERN_PEAKS = [("Großglockner", 3798, 47.0742, 12.6947), ("Kleinglockner", 3770, 47.0725, 12.6950),
                ("Glocknerwand", 3721, 47.0756, 12.6867), ("Großvenediger", 3657, 47.1092, 12.3461),
                ("Großes Wiesbachhorn", 3564, 47.1567, 12.7558), ("Rainerhorn", 3560, 47.1000, 12.3478),
                ("Dreiherrnspitze", 3499, 47.0717, 12.2414), ("Hochalmspitze", 3360, 47.0189, 13.3197),
                ("Ankogel", 3252, 47.0497, 13.2464), ("Hoher Sonnblick", 3106, 47.0542, 12.9578),
                ("Johannisberg", 3453, 47.1167, 12.6667), ("Hohe Riffl", 3338, 47.1450, 12.6930)]


def node(name: str) -> str:
    return f"node/{zlib.crc32(name.encode())}"

# (name, kind, height m) – heights rounded, as OpenStreetMap has them; well-known Tyrolean and Salzburg goals
HOME = [("Patscherkofel", "peak", 2246), ("Nockspitze", "peak", 2404), ("Serles", "peak", 2717),
        ("Glungezer", "peak", 2677), ("Salzburger Hochthron", "peak", 1853), ("Zeppezauerhaus", "hut", 1664),
        ("Schafberg", "peak", 1783), ("Hoher Göll", "peak", 2522), ("Purtschellerhaus", "hut", 1692)]
SKI = [("Rosskogel", "peak", 2646), ("Pirchkogel", "peak", 2828), ("Lampsenspitze", "peak", 2875),
       ("Zischgeles", "peak", 3004), ("Kitzsteinhorn", "peak", 3203)]
BIG = [[("Großglockner", "peak", 3798), ("Erzherzog-Johann-Hütte", "hut", 3454), ("Stüdlhütte", "hut", 2801)],
       [("Wildspitze", "peak", 3768), ("Breslauer Hütte", "hut", 2844)],
       [("Großvenediger", "peak", 3657), ("Kürsingerhütte", "hut", 2547)],
       [("Olperer", "peak", 3476), ("Olpererhütte", "hut", 2389)],
       [("Habicht", "peak", 3277), ("Innsbrucker Hütte", "hut", 2369)],
       [("Zuckerhütl", "peak", 3507), ("Dresdner Hütte", "hut", 2308)],
       [("Weißkugel", "peak", 3739), ("Weißkugelhütte", "hut", 2542)],
       [("Großes Wiesbachhorn", "peak", 3564), ("Heinrich-Schwaiger-Haus", "hut", 2802)],
       [("Hochfeiler", "peak", 3510), ("Hochfeilerhütte", "hut", 2710)],
       [("Hochkönig", "peak", 2941), ("Matrashaus", "hut", 2941)]]
RIDES = [("Timmelsjoch", "pass", 2474), ("Hochtor", "pass", 2504), ("Kühtaisattel", "pass", 2017),
         ("Brennerpass", "pass", 1370), ("Arlbergpass", "pass", 1793), ("Fernpass", "pass", 1216)]


def tours(rng: random.Random, start: date, days: int):
    """Activities named after their summits, as many people name theirs."""
    for n in range(days):
        day = start + timedelta(days=n)
        winter = day.month in (12, 1, 2, 3, 4)
        r = rng.random()
        if day in (date(2026, 7, 18), date(2026, 8, 9)):      # this year's new ones
            kind, places = "Hike", BIG[-2] if day.month == 7 else BIG[-1]
        elif r < 0.07:
            kind, places = "Hike", rng.sample(HOME[:4], rng.randint(1, 2))
        elif r < 0.12:
            kind, places = "Hike", rng.sample(HOME[4:], rng.randint(1, 3))
        elif r < 0.16 and winter:
            kind, places = "BackcountrySki", rng.sample(SKI, rng.randint(1, 2))
        elif r < 0.17 and not winter:
            kind, places = "Hike", rng.choice(BIG[:-2])
        elif r < 0.185 and not winter:
            kind, places = "Ride", rng.sample(RIDES, rng.randint(1, 2))
        else:
            continue
        name = ", ".join(p[0] for p in places if p[1] == "peak") or ", ".join(p[0] for p in places)
        yield day, kind, name, places


def build(out: Path, language: str = "en") -> int:
    rng = random.Random(7)
    with tempfile.TemporaryDirectory() as tmp:
        store = Store(Path(tmp) / "demo.sqlite", Path(tmp) / "tracks")
        for n, (day, kind, name, places) in enumerate(tours(rng, date(2019, 5, 1), 7 * 365 + 150)):
            visits = [{"osm": node(p[0]), "name": p[0], "kind": p[1], "ele": float(p[2]), "dist": 20} for p in places]
            store.save_activity({"id": f"i{100000 + n}", "start_date_local": f"{day}T08:00:00", "type": kind, "name": name},
                                "done", 1000, max(p[2] for p in places) + 5, 1, visits)
        with store.db:                                   # the places: where, and a Wikipedia link for the summits
            for name, (lat, lon) in WHERE.items():
                kind = next(p[1] for group in (HOME, SKI, RIDES, *BIG) for p in group if p[0] == name)
                store.db.execute("INSERT OR REPLACE INTO pois (osm, name, names, kind, ele, lat, lon, ci, cj, wiki) "
                                 "VALUES (?,?,?,?,?,?,?,?,?,?)", (node(name), name, "{}", kind, None, lat, lon, 0, 0,
                                                                  f"de:{name}" if kind == "peak" else None))
        store.save_collection(TAUERN.key, TAUERN.label, [{"osm": node(n), "name": n, "ele": e, "lat": la, "lon": lo}
                                                         for n, e, la, lo in TAUERN_PEAKS])
        size = page.write(store, out, language, "Summit log (demo)" if language == "en" else "Gipfelbuch (Demo)",
                          tiles=OPENTOPOMAP, wanted=(TAUERN,))
        store.close()
    return size


if __name__ == "__main__":
    target = Path(sys.argv[1] if len(sys.argv) > 1 else "demo.html")
    print(f"{target}: {build(target, sys.argv[2] if len(sys.argv) > 2 else 'en') // 1024} KB")
