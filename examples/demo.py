"""A summit log with made-up activities on well-known summits, for screenshots and to try the page.

    python examples/demo.py demo.html [en|de]

Nothing is read from or written to Intervals; the activity links lead nowhere.
"""
from __future__ import annotations

import random
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path

from intervals_summits import page
from intervals_summits.store import Store

# (name, kind, height m) – heights rounded, as OpenStreetMap has them
HOME = [("Kitzbüheler Horn", "peak", 1996), ("Alpenhaus", "hut", 1670), ("Hohe Salve", "peak", 1829),
        ("Wendelstein", "peak", 1838), ("Brecherspitz", "peak", 1683), ("Gruttenhütte", "hut", 1620),
        ("Ellmauer Tor", "pass", 1995), ("Herzogstand", "peak", 1731), ("Heimgarten", "peak", 1791)]
SKI = [("Schwarzkogel", "peak", 2030), ("Gamshag", "peak", 2178), ("Pengelstein", "peak", 1938),
       ("Wildseeloder", "peak", 2118), ("Wildseeloderhaus", "hut", 1854)]
BIG = [[("Großglockner", "peak", 3798), ("Erzherzog-Johann-Hütte", "hut", 3454), ("Stüdlhütte", "hut", 2801)],
       [("Wildspitze", "peak", 3768), ("Breslauer Hütte", "hut", 2844)],
       [("Großvenediger", "peak", 3657), ("Kürsingerhütte", "hut", 2547)],
       [("Zugspitze", "peak", 2962), ("Münchner Haus", "hut", 2959), ("Reintalangerhütte", "hut", 1369)],
       [("Similaun", "peak", 3599), ("Similaunhütte", "hut", 3019), ("Niederjoch", "pass", 3017)],
       [("Hoher Dachstein", "peak", 2995), ("Seethalerhütte", "hut", 2740)],
       [("Triglav", "peak", 2864), ("Kredarica", "hut", 2515)],
       [("Ellmauer Halt", "peak", 2344), ("Gruttenhütte", "hut", 1620)]]
RIDES = [("Timmelsjoch", "pass", 2474), ("Stilfser Joch", "pass", 2757), ("Hochtor", "pass", 2504),
         ("Gerlospass", "pass", 1531), ("Pass Thurn", "pass", 1274), ("Kühtaisattel", "pass", 2017)]


def tours(rng: random.Random, start: date, days: int):
    for n in range(days):
        day = start + timedelta(days=n)
        winter = day.month in (12, 1, 2, 3, 4)
        r = rng.random()
        if r < 0.10:
            yield day, "Hike", "Hausrunde", rng.sample(HOME[:3], rng.randint(1, 2))
        elif r < 0.15:
            yield day, "Hike", "Feierabendrunde", rng.sample(HOME[3:], rng.randint(1, 3))
        elif r < 0.19 and winter:
            yield day, "BackcountrySki", "Skitour", rng.sample(SKI, rng.randint(1, 2))
        elif r < 0.195 and not winter:
            yield day, "Hike", "Hochtour", rng.choice(BIG)
        elif r < 0.21 and not winter:
            yield day, "Ride", "Passfahrt", rng.sample(RIDES, rng.randint(1, 2))


def build(out: Path, language: str = "en") -> int:
    rng = random.Random(7)
    with tempfile.TemporaryDirectory() as tmp:
        store = Store(Path(tmp) / "demo.sqlite", Path(tmp) / "tracks")
        for n, (day, kind, name, places) in enumerate(tours(rng, date(2019, 5, 1), 7 * 365 + 150)):
            visits = [{"osm": f"node/{abs(hash(p[0])) % 10**9}", "name": p[0], "kind": p[1], "ele": float(p[2]), "dist": 20}
                      for p in places]
            store.save_activity({"id": f"i{100000 + n}", "start_date_local": f"{day}T08:00:00", "type": kind, "name": name},
                                "done", 1000, max(p[2] for p in places) + 5, 1, visits)
        size = page.write(store, out, language, "Summit log (demo)" if language == "en" else "Gipfelbuch (Demo)")
        store.close()
    return size


if __name__ == "__main__":
    target = Path(sys.argv[1] if len(sys.argv) > 1 else "demo.html")
    print(f"{target}: {build(target, sys.argv[2] if len(sys.argv) > 2 else 'en') // 1024} KB")
