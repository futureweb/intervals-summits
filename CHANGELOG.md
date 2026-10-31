# Changelog

## 0.1.0 – 2026-11-01

First release.

- **Finds summits, huts and passes** on every Intervals activity with a GPS track (any source).
  Uses OpenStreetMap: peaks within 100 m with the track at most 80 m below the top; huts and
  passes within 60 m. Calibrated against peakproject (38 of 40 summits).
- **Writes activity fields**, created on first use:
  - `Summits` (text) and `SummitCount` (summed per day: summits per week, month or year in fitness charts);
  - `HighestPoint` only where empty (Intervals fills it from FIT files itself);
  - `HutsPasses` optional.
- **Optional description line** `⛰️ Summits: …` (`SUMMITS_DESCRIPTION=true`): Intervals' search looks at
  names and descriptions, not at custom fields. Skipped where the description names the summits already.
- **Your edits stay:** only values the tool wrote itself are ever updated; `--force` overrides.
- **Summit log page:** timeline with hover, pin and link to the activity; top 10/20/50/100 by visits or
  height; per year; searchable log. English and German, light and dark, one self-contained file
  (`page`), or served (`ui`, `run --ui`).
- **Commands:** `sync`, `backfill`, `recompute`, `run`, `ui`, `page`, `status [--check]`, `fields`.
- **Fair use:** Intervals paced with 429 handling (the key is shared with the bridge); OpenStreetMap
  cached in 0.2° cells for 180 days, regions fetched at once.
- **Runs** with pip (Python 3.12+), Docker (amd64/arm64) and as a Home Assistant app with the summit
  log in the sidebar. It reads the settings of garmin-intervals-bridge when there are any.
