#!/bin/sh
# Home Assistant app: intervals-summits with the settings of the app's form. Writes to Intervals
# only once "Write to Intervals" is switched on; until then a dry run (the summit log still fills).
set -e
DATA=${HA_DATA:-/data}
opt() {
    python3 -c 'import json, sys
v = json.load(open(sys.argv[1])).get(sys.argv[2])
print("" if v is None else str(v).lower() if isinstance(v, bool) else v)' "$DATA/options.json" "$1"
}
export SUMMITS_DATA_DIR="$DATA" INTERVALS_API_KEY="$(opt intervals_api_key)" SUMMITS_LANGUAGE="$(opt language)"
export SUMMITS_DESCRIPTION="$(opt description_line)"
FIELDS=Summits,SummitCount,HighestPoint
if [ "$(opt huts_passes)" = true ]; then FIELDS="$FIELDS,Huts,Passes"; fi
export SUMMITS_FIELDS="$FIELDS"
TYPES="$(opt types)"
if [ -n "$TYPES" ]; then export SUMMITS_TYPES="$TYPES"; fi
for RULE in peak_radius peak_below hut_radius pass_radius; do
    VALUE="$(opt $RULE)"
    if [ -n "$VALUE" ]; then export "SUMMITS_$(echo $RULE | tr a-z A-Z)=$VALUE"; fi
done
APPLY=""
if [ "$(opt write_to_intervals)" = true ]; then APPLY="--apply"; fi
# The past, once per date (and once more when writing gets switched on)
FROM="$(opt backfill_from)"
DONE="$DATA/.backfill-$FROM${APPLY:+-applied}"
if [ -n "$FROM" ] && [ ! -e "$DONE" ]; then
    echo "Backfill from $FROM ${APPLY:-(dry run)}"
    intervals-summits backfill --from "$FROM" $APPLY && touch "$DONE"
fi
exec intervals-summits run $APPLY --ui --host 0.0.0.0 --port 8766
