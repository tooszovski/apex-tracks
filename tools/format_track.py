#!/usr/bin/env python3
"""Rewrites track files in the canonical layout: fixed key order, 2-space indent, one outline point per line,
coordinates with 6–7 decimals. Keeps reviews' diffs small and passes the precision check.

    python3 tools/format_track.py tracks/ru/igora-drive.json [...]
    python3 tools/format_track.py --check            # every file; fail if any is not canonical
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from trackfile import ROOT, canonical, load_raw, track_files


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("files", nargs="*", type=Path)
    parser.add_argument("--check", action="store_true", help="only report files that are not canonical")
    args = parser.parse_args()
    files = [p.resolve() for p in args.files] or track_files()
    stale = []
    for path in files:
        text = canonical(load_raw(path))
        if path.read_text(encoding="utf-8") != text:
            stale.append(path)
            if not args.check:
                path.write_text(text, encoding="utf-8")
    for path in stale:
        print(("not canonical: " if args.check else "formatted: ") + path.relative_to(ROOT).as_posix())
    return 1 if args.check and stale else 0


if __name__ == "__main__":
    sys.exit(main())
