# Privacy

intervals-summits runs on your own computer, NAS or Home Assistant. There is no server of ours in
between, and nothing is sent to us.

| Who | What they get | Why |
|---|---|---|
| **Intervals.icu** (your account) | requests with your API key: activity lists, GPS tracks of new activities, and the field values it writes | the tool's job |
| **Overpass API** (OpenStreetMap; overpass-api.de unless you choose another server with `SUMMITS_OVERPASS_URL`) | the corners of rectangles made of 0.2° cells (about 22 × 15 km) where your activities are, never a track, a time or an activity | named peaks, huts and passes in that area |

Stored on your disk, in `SUMMITS_DATA_DIR`:
- the database: activities, summits found, values written, OpenStreetMap points;
- the GPS tracks (`tracks/`; `SUMMITS_KEEP_TRACKS=false` deletes each one once it is matched);
- the summit log page `summits.html`.

The page served with `ui` / `run --ui` listens on 127.0.0.1 unless you say otherwise. It shows your
activities' names and dates, so give it to your network only on purpose.
