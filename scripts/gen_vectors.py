#!/usr/bin/env python3
"""Generate conformance vectors for cancho-tz from CPython's zoneinfo, an implementation independent of this one.

    python3 -I scripts/gen_vectors.py [--zoneinfo /usr/share/zoneinfo] [--out vectors.txt] [--seed N]

The oracle is Python's own zoneinfo reading the SAME files cancho-tz reads. Only the explicit transition instants are taken
from the file directly (a few lines of struct parsing, below), to know where to sample; every expected answer comes from
`zoneinfo`. Two kinds of line, space separated, ordered by zone:

    O <zone> <utc_seconds> <utoff_seconds> <isdst 0|1> <abbreviation>
    L <zone> <local_seconds> <kind 0 unique|1 ambiguous|2 gap> <first_utc> <second_utc>

`L` follows Python's `fold`: `first` is the instant for fold=0 and `second` for fold=1; for an ambiguous time `first` is the
earlier one; for a gap `first` reads the time with the offset before the jump and `second` with the offset after.

Zones whose files are byte-identical are written once (aliases and links read the same bytes). Instants are sampled:
every explicit transition from 1800 on (the instant, one second before, one second after); every daylight-time change the
rule produces from 2024 to 2099, found by scanning and bisecting zoneinfo itself; a fixed number of random instants; and
for each transition the wall-clock times through the window where a gap or fold can be.
"""
import argparse
import hashlib
import os
import random
import struct
import sys
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)
NAIVE_EPOCH = datetime(1970, 1, 1)
LOW = int((datetime(1800, 1, 1, tzinfo=timezone.utc) - EPOCH).total_seconds())
HIGH = int((datetime(2100, 1, 1, tzinfo=timezone.utc) - EPOCH).total_seconds())


def file_transitions(data):
    """Explicit transition instants of a TZif v2+ file (independent of the cancho parser)."""
    assert data[:4] == b"TZif"
    v1 = struct.unpack(">6l", data[20:44])
    isutcnt, isstdcnt, leapcnt, timecnt, typecnt, charcnt = v1
    size1 = timecnt * 4 + timecnt + typecnt * 6 + charcnt + leapcnt * 8 + isstdcnt + isutcnt
    h2 = 44 + size1
    assert data[h2 : h2 + 4] == b"TZif"
    isutcnt, isstdcnt, leapcnt, timecnt, typecnt, charcnt = struct.unpack(">6l", data[h2 + 20 : h2 + 44])
    body = h2 + 44
    return list(struct.unpack(">%dq" % timecnt, data[body : body + 8 * timecnt]))


def utc_to_dt(zone, t):
    return (EPOCH + timedelta(seconds=t)).astimezone(zone)


def offset_row(name, zone, t):
    dt = utc_to_dt(zone, t)
    off = int(dt.utcoffset().total_seconds())
    dst = 1 if dt.dst() else 0
    return "O %s %d %d %d %s" % (name, t, off, dst, dt.tzname())


def local_row(name, zone, local):
    naive = NAIVE_EPOCH + timedelta(seconds=local)
    d0 = naive.replace(tzinfo=zone, fold=0)
    d1 = naive.replace(tzinfo=zone, fold=1)
    off0 = int(d0.utcoffset().total_seconds())
    off1 = int(d1.utcoffset().total_seconds())
    u0 = local - off0
    u1 = local - off1
    if off0 == off1:
        return "L %s %d 0 %d %d" % (name, local, u0, u0)
    back0 = int((utc_to_dt(zone, u0).replace(tzinfo=None) - NAIVE_EPOCH).total_seconds())
    back1 = int((utc_to_dt(zone, u1).replace(tzinfo=None) - NAIVE_EPOCH).total_seconds())
    if back0 == local and back1 == local:
        return "L %s %d 1 %d %d" % (name, local, min(u0, u1), max(u0, u1))
    if back0 != local and back1 != local:
        return "L %s %d 2 %d %d" % (name, local, u0, u1)
    return "L %s %d 3 %d %d" % (name, local, u0, u1)  # inconsistent: the harness reports it


def rule_transitions(zone, first_year=2024, last_year=2099):
    """Instants at which zoneinfo's offset changes, 2024 to 2099, found by scanning and bisecting."""
    out = []
    step = 15 * 86400
    t = int((datetime(first_year, 1, 1, tzinfo=timezone.utc) - EPOCH).total_seconds())
    end = int((datetime(last_year + 1, 1, 1, tzinfo=timezone.utc) - EPOCH).total_seconds())
    prev = utc_to_dt(zone, t).utcoffset()
    while t < end:
        nxt = t + step
        cur = utc_to_dt(zone, nxt).utcoffset()
        if cur != prev:
            lo, hi = t, nxt
            while hi - lo > 1:
                mid = (lo + hi) // 2
                if utc_to_dt(zone, mid).utcoffset() == prev:
                    lo = mid
                else:
                    hi = mid
            out.append(hi)
        prev = cur
        t = nxt
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--zoneinfo", default="/usr/share/zoneinfo")
    ap.add_argument("--out", default="vectors.txt")
    ap.add_argument("--seed", type=int, default=2026)
    ap.add_argument("--random", type=int, default=40)
    args = ap.parse_args()
    rng = random.Random(args.seed)
    seen = {}
    names = []
    for dirpath, dirnames, filenames in os.walk(args.zoneinfo):
        dirnames.sort()
        for fn in sorted(filenames):
            path = os.path.join(dirpath, fn)
            try:
                data = open(path, "rb").read()
            except OSError:
                continue
            if data[:4] != b"TZif":
                continue
            digest = hashlib.sha256(data).hexdigest()
            name = os.path.relpath(path, args.zoneinfo)
            if digest in seen:
                continue
            seen[digest] = name
            names.append((name, data))
    lines = []
    for name, data in names:
        zone = ZoneInfo(name)
        trans = [t for t in file_transitions(data) if LOW <= t < HIGH]
        instants = set()
        for t in trans:
            instants.update((t - 1, t, t + 1))
        rule = rule_transitions(zone)
        for t in rule:
            instants.update((t - 1, t, t + 1))
        for _ in range(args.random):
            instants.add(rng.randrange(LOW, HIGH))
        for t in sorted(instants):
            lines.append(offset_row(name, zone, t))
        locals_ = set()
        for t in sorted(set(trans) | set(rule)):
            before = int(utc_to_dt(zone, t - 1).utcoffset().total_seconds())
            for d in (-7200, -3600, -1800, -900, -1, 0, 1, 900, 1800, 3600, 7200):
                locals_.add(t + before + d)
        for _ in range(args.random):
            locals_.add(rng.randrange(LOW, HIGH))
        for local in sorted(locals_):
            lines.append(local_row(name, zone, local))
    with open(args.out, "w") as f:
        f.write("\n".join(lines) + "\n")
    kinds = {}
    for line in lines:
        if line[0] == "L":
            k = line.split()[3]
            kinds[k] = kinds.get(k, 0) + 1
    sys.stderr.write("zones %d (of %d files), vectors %d, local kinds %s\n" % (len(names), len(seen) and sum(1 for _ in seen), len(lines), kinds))


if __name__ == "__main__":
    main()
