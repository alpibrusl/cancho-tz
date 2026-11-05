#!/bin/sh
# Run the cancho-tz unit tests. CANCHO overrides the compiler path (default: `cancho` on PATH).
cd "$(dirname "$0")/.."
exec "${CANCHO:-cancho}" test tests/tz_test.cho src/tz.cho src/tz_io.cho tests/fixtures/zone_data.cho --std
