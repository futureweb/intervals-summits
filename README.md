# intervals-summits

**Summits, huts and passes on your [Intervals.icu](https://intervals.icu) activities**, found in your
own GPS tracks with OpenStreetMap, plus your personal **summit log**.

![The summit log page (demo data)](docs/images/summit-log.png)

- **In Intervals:** every activity gets its summits in a field, e.g. `Maukspitze (2231 m), Ackerlspitze (2329 m)`.
  Two more fields: the number of summits, which you can chart per week, month or year, and the
  highest point of the activity.
- **The summit log page:**
  - your summits, huts and passes over time;
  - your top 10/20/50/100 (most visited or highest);
  - a count per year;
  - a searchable log, every entry linked to its activity in Intervals.
- **It works with every activity that has a GPS track**, whatever it came from: Garmin, Wahoo, Coros,
  Suunto, Polar, a Strava import or an upload. Old ones too: one backfill matches your whole history.
- It needs nothing but your Intervals API key. It runs **next to
  [garmin-intervals-bridge](https://github.com/futureweb/garmin-intervals-bridge)** with the same
  settings, but does not need it.

## How a summit is found

- **Peaks** (`natural=peak`/`volcano`): the track comes within **100 m**, *and* the track's altitude
  there is at most **80 m below** the summit. A path along the slope below a summit does not count;
  a gondola ride to the top does.
- **Huts** (`tourism=alpine_hut`/`wilderness_hut`) and **passes** (`mountain_pass=yes`,
  `natural=saddle`): within **60 m**.
- One entry per name and activity, in the order of the track.

These rules were calibrated against peakproject's summit lines on 25 activities: 38 of 40 summits
were found. A summit that OpenStreetMap does not have, or has under another name, cannot be found.
Improve the map, and `recompute` picks it up.

## What lands in Intervals

| Field (code) | Type | Content |
|---|---|---|
| `Summits` | text | `Maukspitze (2231 m), Ackerlspitze (2329 m)`: the summits in the order you reached them |
| `SummitCount` | number, summed per day | how many summits; chart them per week, month or year |
| `HighestPoint` | number, max per day | **only where empty.** Intervals fills it from a FIT file itself; for GPX/TCX and old activities the tool takes the highest point of the track |
| `HutsPasses` | text | huts and passes. Off by default: `SUMMITS_FIELDS=…,HutsPasses` |
| description | one line | optional, `SUMMITS_DESCRIPTION=true`: `⛰️ Summits: Maukspitze (2231 m), …`, **so Intervals' search finds them** (see below) |

The tool creates missing fields itself.
- **Codes are the same for everyone**, so charts and scripts can be shared.
- **Names** are English, or German with `SUMMITS_LANGUAGE=de`. You may rename them in Intervals freely:
  the tool goes by the code.

**Your edits stay.** A value you typed, or another tool wrote, is never overwritten (unless
`--force`). The tool only updates what it wrote itself. In the description it only ever touches its
own line. If the description already names all the summits (peakproject's lines, for example), it
adds nothing.

### Seeing them in Intervals

- **On the activity:** the fields show above the charts. Which fields show is chosen per sport, and
  they can go into the summary layout.
- **List and totals:** custom fields work as columns and in filters.
- **Fitness charts:** `SummitCount` (summed per day) and `HighestPoint` (maximum per day) can be
  plotted; on a weekly or monthly scale you get summits per week or month.
- **Search:** Intervals' search looks at names and descriptions, not at custom fields. Turn on
  `SUMMITS_DESCRIPTION=true`, and searching "Maukspitze" finds every activity that reached it.

## Installing and running

### Docker (NAS, server, next to the bridge)

```bash
curl -O https://raw.githubusercontent.com/futureweb/intervals-summits/main/compose.yaml
curl -o .env https://raw.githubusercontent.com/futureweb/intervals-summits/main/.env.example   # put your key in
docker compose up -d                  # a dry run: the summit log fills, nothing is written
docker compose logs -f                # what it would write
docker compose run --rm summits backfill --from 2015-01-01 --apply      # your past
# then command: ["run", "--apply", "--ui", "--host", "0.0.0.0"] in compose.yaml and up -d again
```

The summit log is at **http://localhost:8766/**. Next to the bridge, add the service to the bridge's
`compose.yaml` and use its `.env`: the same key works.

### Home Assistant

Add `https://github.com/futureweb/intervals-summits` as an app repository (Settings → Apps → App store
→ ⋮ → Repositories). Then install **Intervals Summits**, enter your Intervals API key, optionally
"Backfill from", and start it. The summit log appears in the sidebar. Switch on *Write to Intervals*
once the dry run looks right.

### On your computer (Windows, Mac, Linux), Python 3.12+

```bash
pip install intervals-summits              # Windows: py -m pip install intervals-summits
intervals-summits backfill --from 2015-01-01          # dry run over your past
intervals-summits backfill --from 2015-01-01 --apply  # … and write
intervals-summits run --apply --ui         # keep running; the summit log on http://127.0.0.1:8766/
```

Settings come from the environment, else from `./.env`, `~/IntervalsSummits/.env` or the bridge's
`~/GarminBridge/.env`. A bridge set up on the same computer is enough: nothing to configure twice.
Instead of keeping it running, `intervals-summits sync --apply` once a day (Task Scheduler, cron)
works as well. It catches up on the days since its last run.

### Commands

| Command | |
|---|---|
| `sync [--apply] [--force]` | The recent days; after a pause it reads back to the last run (at most 14 days) |
| `backfill --from DATE [--to DATE] [--apply]` | The past: tracks first, then OpenStreetMap for all of them at once, then matching and writing. Resumable. |
| `recompute --from DATE [--apply]` | Match again, e.g. after OpenStreetMap got better. Writes only differences. |
| `run [--apply] [--ui] [--host H] [--port 8766]` | Keeps running: a sync every 15 minutes, optionally with the summit log page |
| `ui [--host H] [--port 8766]` | Only the summit log page |
| `page [--out FILE] [--language de]` | The summit log as one self-contained HTML file, to keep or share |
| `status [--check] [--fields]` | Counts and the last sync; `--check` for health checks (exit 1 when no sync came for long) |
| `fields [--apply]` | Create the activity fields now |

Without `--apply`, nothing is written to Intervals. The summit log page still fills.

`python examples/demo.py demo.html` builds a summit log with made-up data (the screenshot above).

## Settings

| Variable | Default | |
|---|---|---|
| `INTERVALS_API_KEY` | – | Intervals → Settings → Developer Settings |
| `INTERVALS_ATHLETE_ID` | `0` | `0` = the key's owner |
| `SUMMITS_DATA_DIR` | `~/GarminBridge/summits` next to a bridge, else `~/IntervalsSummits` | database, tracks, `summits.html` |
| `SUMMITS_LANGUAGE` | `en` | `en` or `de`: names of new fields, the page, the description line |
| `SUMMITS_NAME_LANGUAGE` | – | e.g. `en`: OpenStreetMap's `name:en` where there is one, else the local name |
| `SUMMITS_FIELDS` | `Summits,SummitCount,HighestPoint` | add `HutsPasses` for huts and passes |
| `SUMMITS_DESCRIPTION` | `false` | `true`: the `⛰️ Summits:` line in the description (searchable) |
| `SUMMITS_TYPES` | every outdoor type | only these activity types, e.g. `Hike,BackcountrySki` |
| `SUMMITS_LOOKBACK_DAYS` | `3` | how far `sync` looks back |
| `SUMMITS_INTERVAL_MINUTES` | `15` | `run`: minutes between syncs |
| `SUMMITS_KEEP_TRACKS` | `true` | keep the tracks: `recompute` without downloading them again (~20 KB per activity) |
| `SUMMITS_OVERPASS_URL` | overpass-api.de | another Overpass server |
| `SUMMITS_PAGE_TITLE` | Summit log / Gipfelbuch | |

## Fair to Intervals and OpenStreetMap

- **Intervals:** the API key is usually shared with the bridge. The tool paces itself (at most
  about 1.5 requests a second) and waits whenever Intervals answers 429. A sync with nothing new is
  one small request.
- **OpenStreetMap:** points come from the Overpass API and are cached in 0.2° cells for 180 days,
  so your usual tours cost no query after the first time. A backfill asks for whole regions at
  once (16 years and 1,800 tours, in the Alps and on a few trips abroad: 18 queries). One query at a time, with a pause between
  queries, and patience on 429/5xx.

## Privacy

Your data stays on your computer and in your Intervals account. Overpass learns which 0.2° cells
(about 22 × 15 km) you need, never a track or an activity. Details: [PRIVACY.md](PRIVACY.md).

## Licence

MIT. Map data © [OpenStreetMap](https://www.openstreetmap.org/copyright) contributors, ODbL.
