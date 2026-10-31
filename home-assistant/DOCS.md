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

Everything else: https://github.com/futureweb/intervals-summits
