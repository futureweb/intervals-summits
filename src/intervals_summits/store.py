"""Local state in one SQLite file: processed activities, their visits, what was written to
Intervals, and the cached OpenStreetMap points with the cells they were fetched for. Tracks
(optional) as tracks/<id>.json.gz."""
from __future__ import annotations

import gzip
import json
import os
import sqlite3
import tempfile
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS activities(id TEXT PRIMARY KEY, start TEXT, type TEXT, name TEXT, status TEXT,
  points INTEGER, max_alt REAL, algo INTEGER, processed_at TEXT);
CREATE TABLE IF NOT EXISTS visits(activity_id TEXT, seq INTEGER, osm TEXT, name TEXT, kind TEXT, ele REAL, dist INTEGER,
  PRIMARY KEY(activity_id, seq));
CREATE TABLE IF NOT EXISTS written(activity_id TEXT, code TEXT, value TEXT, at TEXT, PRIMARY KEY(activity_id, code));
CREATE TABLE IF NOT EXISTS pois(osm TEXT PRIMARY KEY, name TEXT, names TEXT, kind TEXT, ele REAL, lat REAL, lon REAL,
  ci INTEGER, cj INTEGER, wiki TEXT);
CREATE INDEX IF NOT EXISTS pois_cell ON pois(ci, cj);
CREATE TABLE IF NOT EXISTS cells(ci INTEGER, cj INTEGER, fetched_at TEXT, PRIMARY KEY(ci, cj));
CREATE TABLE IF NOT EXISTS collections(key TEXT PRIMARY KEY, label TEXT, fetched_at TEXT, members TEXT);
"""


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def atomic_write(path: Path, data: bytes, *, readable: bool = False) -> None:
    """Write via a temporary file and rename. `readable`: as a file created normally would be (the
    umask decides), not 0600 – for a page a web server serves."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        if readable:                                   # after closing: os.fchmod is not there on Windows
            mask = os.umask(0)
            os.umask(mask)
            os.chmod(tmp, 0o666 & ~mask)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


class Store:
    def __init__(self, db_file: Path, tracks_dir: Path):
        db_file.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(db_file)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)
        if "wiki" not in {r[1] for r in self.db.execute("PRAGMA table_info(pois)")}:
            # 0.1 kept no Wikipedia links: add the column and read the cells again when next needed
            with self.db:
                self.db.execute("ALTER TABLE pois ADD COLUMN wiki TEXT")
                self.db.execute("UPDATE cells SET fetched_at='1970-01-01T00:00:00+00:00'")
        self.tracks_dir = tracks_dir

    def close(self) -> None:
        self.db.close()

    # ---- meta ----
    def get(self, key: str) -> str | None:
        row = self.db.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return row[0] if row else None

    def put(self, key: str, value: str) -> None:
        with self.db:
            self.db.execute("INSERT OR REPLACE INTO meta VALUES (?, ?)", (key, value))

    # ---- activities and visits ----
    def activity(self, aid: str) -> sqlite3.Row | None:
        return self.db.execute("SELECT * FROM activities WHERE id=?", (aid,)).fetchone()

    def save_activity(self, a: dict, status: str, points: int, max_alt: float | None, algo: int,
                      visits: list[dict] | None = None) -> None:
        with self.db:
            self.db.execute("INSERT OR REPLACE INTO activities VALUES (?,?,?,?,?,?,?,?,?)",
                            (a["id"], a.get("start_date_local"), a.get("type"), a.get("name"), status, points,
                             max_alt, algo, now()))
            self.db.execute("DELETE FROM visits WHERE activity_id=?", (a["id"],))
            self.db.executemany("INSERT INTO visits VALUES (?,?,?,?,?,?,?)",
                                [(a["id"], n, v["osm"], v["name"], v["kind"], v.get("ele"), v.get("dist"))
                                 for n, v in enumerate(visits or [])])

    def refresh_activity(self, a: dict) -> None:
        """Name, type or date changed in Intervals: the page shows the new ones."""
        with self.db:
            self.db.execute("UPDATE activities SET start=?, type=?, name=? WHERE id=?",
                            (a.get("start_date_local"), a.get("type"), a.get("name"), a["id"]))

    def visits(self, aid: str) -> list[dict]:
        return [dict(r) for r in self.db.execute("SELECT * FROM visits WHERE activity_id=? ORDER BY seq", (aid,))]

    def all_visits(self) -> list[dict]:
        return [dict(r) for r in self.db.execute(
            "SELECT v.*, a.start, a.type, a.name AS aname FROM visits v JOIN activities a ON a.id = v.activity_id "
            "ORDER BY a.start, v.seq")]

    def forget_missing(self, oldest: str, newest: str, present: set[str]) -> int:
        """Activities deleted in Intervals (within a window that was listed in full)."""
        gone = [r[0] for r in self.db.execute("SELECT id FROM activities WHERE substr(start,1,10) BETWEEN ? AND ?",
                                              (oldest, newest)) if r[0] not in present]
        with self.db:
            for aid in gone:
                for table, col in (("activities", "id"), ("visits", "activity_id"), ("written", "activity_id")):
                    self.db.execute(f"DELETE FROM {table} WHERE {col}=?", (aid,))
        return len(gone)

    def counts(self) -> dict:
        q = self.db.execute
        return {"activities": dict(q("SELECT status, COUNT(*) FROM activities GROUP BY status").fetchall()),
                "visits": q("SELECT COUNT(*) FROM visits").fetchone()[0],
                "places": q("SELECT COUNT(DISTINCT osm) FROM visits").fetchone()[0],
                "with_visits": q("SELECT COUNT(DISTINCT activity_id) FROM visits").fetchone()[0],
                "written": dict(q("SELECT code, COUNT(*) FROM written GROUP BY code").fetchall()),
                "osm_points": q("SELECT COUNT(*) FROM pois").fetchone()[0],
                "osm_cells": q("SELECT COUNT(*) FROM cells").fetchone()[0]}

    # ---- what the tool wrote ----
    def written(self, aid: str) -> dict[str, str]:
        return {r[0]: r[1] for r in self.db.execute("SELECT code, value FROM written WHERE activity_id=?", (aid,))}

    def record_written(self, aid: str, values: dict) -> None:
        with self.db:
            self.db.executemany("INSERT OR REPLACE INTO written VALUES (?,?,?,?)",
                                [(aid, code, json.dumps(value), now()) for code, value in values.items()])

    # ---- OpenStreetMap cache ----
    def cell_fetched(self, cell: tuple[int, int]) -> str | None:
        row = self.db.execute("SELECT fetched_at FROM cells WHERE ci=? AND cj=?", cell).fetchone()
        return row[0] if row else None

    def save_pois(self, cells: set[tuple[int, int]], pois: list[dict]) -> None:
        """Replace everything known in these cells (renamed or deleted points included)."""
        with self.db:
            for cell in cells:
                self.db.execute("DELETE FROM pois WHERE ci=? AND cj=?", cell)
            self.db.executemany("INSERT OR REPLACE INTO pois (osm, name, names, kind, ele, lat, lon, ci, cj, wiki) "
                                "VALUES (?,?,?,?,?,?,?,?,?,?)",
                                [(p["osm"], p["name"], json.dumps(p.get("names") or {}, ensure_ascii=False), p["kind"],
                                  p.get("ele"), p["lat"], p["lon"], p["ci"], p["cj"], p.get("wiki"))
                                 for p in pois if (p["ci"], p["cj"]) in cells])
            stamp = now()
            self.db.executemany("INSERT OR REPLACE INTO cells VALUES (?,?,?)", [(i, j, stamp) for i, j in cells])

    def places(self) -> dict[str, dict]:
        """Where the visited places are, and their Wikipedia link (for the map and the log)."""
        return {r["osm"]: dict(r) for r in self.db.execute(
            "SELECT osm, lat, lon, wiki FROM pois WHERE osm IN (SELECT DISTINCT osm FROM visits)")}

    # ---- collections (all summits of an area above a height) ----
    def collection(self, key: str) -> dict | None:
        row = self.db.execute("SELECT * FROM collections WHERE key=?", (key,)).fetchone()
        return dict(row, members=json.loads(row["members"])) if row else None

    def save_collection(self, key: str, label: str, members: list[dict]) -> None:
        with self.db:
            self.db.execute("INSERT OR REPLACE INTO collections VALUES (?,?,?,?)",
                            (key, label, now(), json.dumps(members, ensure_ascii=False)))

    def pois_in(self, cells: set[tuple[int, int]]) -> list[dict]:
        out = []
        for cell in cells:
            for r in self.db.execute("SELECT * FROM pois WHERE ci=? AND cj=?", cell):
                p = dict(r)
                p["names"] = json.loads(p["names"] or "{}")
                out.append(p)
        return out

    # ---- tracks ----
    def track_path(self, aid: str) -> Path:
        return self.tracks_dir / f"{aid}.json.gz"

    def load_track(self, aid: str) -> dict | None:
        path = self.track_path(aid)
        if not path.is_file():
            return None
        with gzip.open(path, "rt", encoding="utf-8") as f:
            return json.load(f)

    def save_track(self, track: dict) -> None:
        atomic_write(self.track_path(track["id"]), gzip.compress(json.dumps(track).encode("utf-8")))

    def drop_track(self, aid: str) -> None:
        self.track_path(aid).unlink(missing_ok=True)
