#!/usr/bin/env python3
"""Builds index.json from tracks/: what the app downloads first to know which track files exist.

    python3 tools/build_index.py          # rewrite index.json
    python3 tools/build_index.py --check  # fail if index.json is not up to date
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys

from trackfile import EXAMPLE_DIR, INDEX, ROOT, TRACKS, load_raw, to_plain, track_files

INDEX_FIELDS = ["id", "slug", "name", "localName", "country", "city", "center", "surface", "lengthM", "variantOf", "license"]


def build() -> str:
    entries = []
    for path in track_files():
        if path.relative_to(TRACKS).parts[0] == EXAMPLE_DIR:
            continue
        track = to_plain(load_raw(path))
        if track.get("example"):
            continue
        entry = {k: track[k] for k in INDEX_FIELDS if k in track}
        entry["center"] = {k: round(v, 6) for k, v in entry["center"].items()}
        entry["path"] = path.relative_to(ROOT).as_posix()
        entry["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
        entry["updated"] = track["updated"]
        entries.append(entry)
    entries.sort(key=lambda e: (e["country"], e["slug"]))
    index = {
        "formatVersion": 1,
        "updated": max((e["updated"] for e in entries), default=None),
        "count": len(entries),
        "tracks": entries,
    }
    return json.dumps(index, ensure_ascii=False, indent=2) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--check", action="store_true", help="only check that index.json is up to date")
    args = parser.parse_args()
    fresh = build()
    if args.check:
        current = INDEX.read_text(encoding="utf-8") if INDEX.exists() else ""
        if current != fresh:
            print("index.json is out of date: run python3 tools/build_index.py and commit the result", file=sys.stderr)
            return 1
        print("index.json is up to date")
        return 0
    INDEX.write_text(fresh, encoding="utf-8")
    print(f"index.json: {json.loads(fresh)['count']} track(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
