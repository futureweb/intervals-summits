# Intervals Summits

Finds the summits, huts and passes on your Intervals.icu activities, from your GPS tracks and
OpenStreetMap. It writes them into activity fields (`Summits`, `SummitCount`, `HighestPoint`) and
shows your **summit log** in the sidebar.

1. Enter your **Intervals API key**: Intervals.icu → Settings → Developer Settings. The same key
   as the Garmin bridge's works.
2. Optionally set **Backfill from**, e.g. `2015-01-01`: your past activities are matched once.
3. Start the app. It begins as a **dry run**: the summit log in the sidebar fills, and the log shows
   what it would write. Nothing is written to Intervals yet.
4. When it looks right, switch on **Write to Intervals** and restart.

It looks for new activities every 15 minutes. Values you edit by hand in Intervals stay as you left them.

**Next to the Garmin bridge app** (0.12.9 or newer): enter `http://<hostname>:8766/sync` as the
bridge's *Notify URL*, with the hostname from this app's *Info* tab. The bridge then says when there is
something new, and this app looks on its own only every 3 hours.

**Stricter or more generous:** the optional radius settings (summit, below the summit, hut, pass) change
how close the track must come. Best set them before the first backfill: they apply to every activity
matched after the change.

Everything else: https://github.com/futureweb/intervals-summits
