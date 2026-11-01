# Changelog

## 0.2.0 – 2026-11-01

- **Huts and passes in fields of their own:** `Huts` and `Passes` (`SUMMITS_FIELDS=…,Huts,Passes`; in
  Home Assistant *Huts and passes*). With them on, the description line names them too, and only when
  there were some: `⛰️ Summits: … · Huts: … · Passes: …`. `HutsPasses` from 0.1 still works.
- **A map in the summit log:** every summit, hut and pass you reached, sized by visits, with your tours
  there and the Wikipedia link; OpenTopoMap tiles (`SUMMITS_MAP_TILES`). Loaded once it is in view; the
  rest of the page still works offline.
- **Wikipedia links** in the log and on the map, where OpenStreetMap has the article. The cached
  OpenStreetMap cells are read once more for them.
- **First visits:** starred in the log, "new in <year>" among the figures, the new places per year
  under the year chart.
- **Collections** (`SUMMITS_COLLECTIONS`): all summits of an area above a height, e.g. the 3000ers of
  Tirol; how many you have been on, the list, and the missing ones on the map.
- **Intervals charts:** *Intervals Summits: per week* and *per month* (summits, highest point of each
  day), made with the fields and kept up to date (`SUMMITS_CHARTS`, `charts --apply`).
- **The page on a web server:** `SUMMITS_PAGE_FILE` writes it there, readable by the server;
  `SUMMITS_PAGE_LANGUAGE` gives it a language of its own.

## 0.1.1 – 2026-11-01

- **Only activity notes start a sync.** garmin-intervals-bridge 0.12.10 also reports new wellness data
  to `BRIDGE_NOTIFY_URL` (`"event": "wellness"`); summits takes those and leaves them alone. Notes
  without an event (bridge 0.12.9) still count as new activities.

## 0.1.0 – 2026-11-01

First release.

- **Finds summits, huts and passes** on every Intervals activity with a GPS track (any source).
  Uses OpenStreetMap: peaks within 100 m with the track at most 80 m below the top; huts and
  passes within 60 m. Calibrated against an independent summit log (38 of 40 summits).
- **Writes activity fields**, created on first use:
  - `Summits` (text) and `SummitCount` (summed per day: summits per week, month or year in fitness charts);
  - `HighestPoint` only where empty (Intervals fills it from FIT files itself);
  - `HutsPasses` optional.
- **Optional description line** `⛰️ Summits: …` (`SUMMITS_DESCRIPTION=true`): Intervals' search looks at
  names and descriptions, not at custom fields. Skipped where the description names the summits already.
  The description is read again right before writing; the tool adds or updates its own line only, the
  rest stays character for character.
- **Your edits stay:** only values the tool wrote itself are ever updated; `--force` overrides.
- **The rules can be set:** `SUMMITS_PEAK_RADIUS`, `SUMMITS_PEAK_BELOW`, `SUMMITS_HUT_RADIUS`,
  `SUMMITS_PASS_RADIUS` (also in Home Assistant); `recompute` applies new ones to the past.
- **Next to garmin-intervals-bridge 0.12.9+:** the bridge says when there are new activities
  (`BRIDGE_NOTIFY_URL` → `POST /sync`); summits syncs at once and looks on its own only every 3 hours.
- **Summit log page:** timeline with hover, pin and link to the activity; top 10/20/50/100 by visits or
  height; per year; searchable log. English and German, light and dark, one self-contained file
  (`page`), or served (`ui`, `run --ui`).
- **Commands:** `sync`, `backfill`, `recompute`, `run`, `ui`, `page`, `status [--check]`, `fields`.
- **Fair use:** Intervals paced with 429 handling (the key is shared with the bridge); OpenStreetMap
  cached in 0.2° cells for 180 days, regions fetched at once.
- **Runs** with pip (Python 3.12+), Docker (amd64/arm64) and as a Home Assistant app with the summit
  log in the sidebar. It reads the settings of garmin-intervals-bridge when there are any.
