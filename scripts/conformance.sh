#!/bin/sh
# Check cancho-tz against CPython's zoneinfo on every distinct zone in a zoneinfo directory.
#   CANCHO=/path/to/cancho scripts/conformance.sh [zoneinfo-dir]
# Needs python3 (3.9+, with zoneinfo) only as the ORACLE: it generates the vectors; the check itself is a cancho program.
set -e
cd "$(dirname "$0")/.."
dir="${1:-/usr/share/zoneinfo}"
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
python3 -I scripts/gen_vectors.py --zoneinfo "$dir" --out "$work/vectors.txt"
"${CANCHO:-cancho}" build src/tz.cho src/tz_io.cho tests/conformance/zones_all.cho --std -o "$work/zones_all" 2>&1 | grep -v "^ld: warning" || true
"$work/zones_all" "$dir" "$work/vectors.txt"
