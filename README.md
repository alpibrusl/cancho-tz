# cancho-tz

IANA time zones for [cancho](https://github.com/alpibrusl/cancho): what is the offset from UTC in this zone at this instant, and **what instant is this wall-clock time in this zone**, which is not a function, because a clock time can happen twice (clocks go back) or never (they jump forward). No capability, no foreign code.

**Status: alpha.** `src/tz.cho` (the pure core), `src/tz_io.cho` (reading the system zoneinfo), 43 unit tests, and a conformance run of **537,088 instants over all 345 distinct zones in tzdata 2026e with zero disagreements** against CPython's `zoneinfo`.

```cancho
let (zone, code) = tz_io.read_system_zone(heap, fs, "Europe/Madrid");   // fs: Fs("/usr/share/zoneinfo"), nothing else
borrow zone as &z in {
    let i = tz.info_at(z, 1784116800);       // utoff 7200, isdst 1, abbreviation "CEST"
    let t = tz.to_local(z, 1784116800);      // wall clock, in seconds

    let r = tz.local_to_utc(z, 1774751400);  // 2026-03-29 02:30 Madrid
    // r.kind == tz.k_gap(): that time never happened. r.first reads it with the offset before the jump,
    // r.second with the offset after (Python's fold=0 and fold=1).

    let a = tz.local_to_utc(z, 1792895400);  // 2026-10-25 02:30 Madrid
    // a.kind == tz.k_ambiguous(): it happened twice. a.first is the earlier instant, a.second the later.
}
```

## What it does

* **`load`** reads a version 2+ TZif file (RFC 8536) from bytes. The zone keeps the bytes and the offsets of its tables; nothing is decoded until asked.
* **`info_at(z, t)`**: offset, daylight flag and abbreviation at instant `t` (seconds). Binary search over the file's explicit transitions; **after the last one the POSIX rule string at the end of the file answers** (`CET-1CEST,M3.5.0,M10.5.0/3`), which is what a date in 2040 uses.
* **`local_to_utc(z, local)`** answers `k_unique`, `k_ambiguous` or `k_gap` with the two readings; **`minutes_*`** for callers that count minutes (floor division, exact below zero).
* **`tz_io`** reads a zone by name. Names are untrusted: `[A-Za-z0-9_+-/.]`, 1 to 64 bytes, no empty or `.`-leading segment, so `..` cannot occur. `read_system_zone` takes a capability narrowed to `/usr/share/zoneinfo`.
* Pure functions on the calendar (`days_from_civil`, `civil_of_days`, `year_of_days`, `nth_weekday`, ...) are exported and exact for any year, negative ones included.

## What it does not do

* **Only the `Mm.w.d[/time]` form of a rule** (every rule in tzdata 2026e; checked over all 599 files). A file with a Julian-day rule is refused (`r_bad_rule`), never guessed at.
* **Version 1 files** (32-bit times, no rule) are refused. Leap-second records are skipped, not applied (POSIX time has none).
* **Two changes of offset less than a day apart** are not told apart by `local_to_utc` (it looks a day either side). None exists in tzdata 2026e; the conformance run checks every zone.
* **Before the first transition** the answer is the zone's first local time type (RFC 8536), normally its local mean time.
* No zone **names** to aliases or links, no "which zone is this city in", no formatting or parsing of dates, no `Etc/` or POSIX-string-only zones given as a string: you pass a zone file's bytes.
* The data is whatever the system has. tzdata changes (several times a year); the caller owns keeping it current. Nothing here embeds a database.

## Test

```sh
CANCHO=/path/to/cancho scripts/test.sh            # 43 unit tests, real zone files embedded as hex
CANCHO=/path/to/cancho scripts/conformance.sh     # all zones vs CPython zoneinfo (python3 is the oracle only)
```

The unit expectations were computed independently of this package: instants and offsets by Python's `zoneinfo` reading the same files, calendar facts by Python's `datetime`. The conformance vectors (`scripts/gen_vectors.py`) cover every explicit transition from 1800 on (the instant and one second either side), every daylight change the rule makes from 2024 to 2099 (found by scanning and bisecting `zoneinfo`), 40 random instants per zone, and wall-clock times through every gap and fold window.

Both suites were checked by deliberately breaking `tz.cho` (about 60 breakages) and requiring a test or the conformance run to fail. Every survivor was either a missing test (which was then added) or an equivalent change; the equivalent ones are `year_of_local` (matters only for a rule change within hours of New Year, which no zone has), `ambiguous_sort` (an offset only ever decreases at a fold, so the order is already right) and `dst_name_needed` (the next parse step refuses the same input). The conformance run shares tzdata's own mistakes by construction, and agreement with another implementation is strong evidence, not proof.

Licence: EUPL-1.2.
