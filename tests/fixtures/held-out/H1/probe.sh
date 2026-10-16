#!/bin/sh
set -u
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
MILEPOST_DATA="$work/trips.json"
export MILEPOST_DATA
python3 -m milepost log 2026-03-02 Lyon 42 >/dev/null || exit 2
python3 -m milepost log 2026-03-05 Dijon 18.5 >/dev/null || exit 2
python3 -m milepost log 2026-03-09 Annecy 63 >/dev/null || exit 2
first=$(python3 -m milepost show | head -n 1)
place=$(printf '%s\n' "$first" | awk '{print $3}')
python3 -m milepost drop 1 >/dev/null || exit 3
after=$(python3 -m milepost show)
if printf '%s\n' "$after" | grep -q "  $place  "; then
    echo "probe: show listed $first, and after drop 1 it still lists $place"
    exit 1
fi
left=$(printf '%s\n' "$after" | grep -c " km$")
if [ "$left" -ne 2 ]; then
    echo "probe: expected 2 trips after drop 1, show lists $left"
    exit 1
fi
echo "probe: drop 1 removed $place, the trip show listed first"
