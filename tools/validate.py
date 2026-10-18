#!/usr/bin/env python3
"""Checks track files: the schema, where the file lives, coordinate precision, geometry sanity, licence of the
sources, unique slugs and ids, and that index.json is up to date.

    python3 tools/validate.py                      # every file under tracks/
    python3 tools/validate.py tracks/ru/foo.json   # these files (cross-file checks still see all of them)

Errors fail the run; warnings are for the moderator to look at. Needs `pip install jsonschema`.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
from pathlib import Path

from trackfile import (EXAMPLE_DIR, ROOT, SCHEMA, TRACKS, Frame, Path2, angle_diff, decimals, load_raw, to_plain,
                       track_files)

try:
    import jsonschema
except ImportError:  # pragma: no cover
    sys.exit("jsonschema is missing: pip install jsonschema")

# Limits. CONTRIBUTING.md explains each one; keep them in step.
MIN_DECIMALS = 6
CLOSE_GAP_M = 60            # a circuit's outline ends this close to where it starts
MAX_POINT_GAP_M = 30        # error: a hole in the outline
WARN_POINT_GAP_M = 15
GATE_OFFSET_M = 20          # a line's middle off the driven line
GATE_HEADING_DEG = 30       # a line's heading against the outline's direction there
WIDTH_WARN = (15, 50)
GATE_SPACING_M = 100        # error below, warning below the next one
GATE_SPACING_WARN_M = 150
CORNER_OFFSET_M = 30
CENTER_MAX_M = 3000
LENGTH_ERROR = 0.05
LENGTH_WARN = 0.02


class Report:
    def __init__(self):
        self.errors = 0
        self.warnings = 0
        self.annotate = os.environ.get("GITHUB_ACTIONS") == "true"

    def _emit(self, level: str, path: Path, message: str):
        rel = path.relative_to(ROOT).as_posix() if path.is_absolute() else str(path)
        if self.annotate:
            print(f"::{level} file={rel}::{message}")
        else:
            print(f"{level.upper():7} {rel}: {message}")

    def error(self, path, message):
        self.errors += 1
        self._emit("error", path, message)

    def warn(self, path, message):
        self.warnings += 1
        self._emit("warning", path, message)


def geo_points(raw: dict):
    """(where, point) for every coordinate in the file."""
    if isinstance(raw.get("center"), dict):
        yield "center", raw["center"]
    for key in ("startFinish", "finish"):
        if isinstance(raw.get(key), dict) and isinstance(raw[key].get("point"), dict):
            yield key, raw[key]["point"]
    for i, gate in enumerate(raw.get("sectors") or []):
        if isinstance(gate, dict) and isinstance(gate.get("point"), dict):
            yield f"sectors[{i}]", gate["point"]
    for i, corner in enumerate(raw.get("corners") or []):
        for key in ("apex", "entry"):
            if isinstance(corner, dict) and isinstance(corner.get(key), dict):
                yield f"corners[{i}].{key}", corner[key]
    for i, p in enumerate(raw.get("outline") or []):
        if isinstance(p, dict):
            yield f"outline[{i}]", p


def check_location(path: Path, track: dict, report: Report):
    rel = path.relative_to(TRACKS)
    if len(rel.parts) != 2:
        report.error(path, "a track file lives at tracks/<country>/<slug>.json")
        return
    folder, name = rel.parts[0], rel.stem
    if name != track["slug"]:
        report.error(path, f"file name '{name}' differs from slug '{track['slug']}'")
    if folder == EXAMPLE_DIR:
        if track.get("example") is not True:
            report.error(path, f'files under tracks/{EXAMPLE_DIR}/ must carry "example": true')
    else:
        if track.get("example"):
            report.error(path, f'"example": true is allowed only under tracks/{EXAMPLE_DIR}/')
        if folder != track["country"].lower():
            report.error(path, f"directory '{folder}' differs from country {track['country']} (expected tracks/{track['country'].lower()}/)")


def check_precision(path: Path, raw: dict, report: Report):
    coarse = [where for where, p in geo_points(raw) if min(decimals(p.get("lat")), decimals(p.get("lon"))) < MIN_DECIMALS]
    if coarse:
        report.error(path, f"{len(coarse)} coordinate(s) with fewer than {MIN_DECIMALS} decimals (first: {coarse[0]}); "
                           f"python3 tools/format_track.py {path.relative_to(ROOT).as_posix()} rewrites them")


def check_sources(path: Path, track: dict, report: Report):
    sources = [track["source"]] + ([track["outlineSource"]] if "outlineSource" in track else [])
    osm = any(s["kind"] == "osm" for s in sources)
    if osm:
        if track["license"] != "ODbL-1.0":
            report.error(path, 'data derived from OpenStreetMap must carry "license": "ODbL-1.0"')
        for s in sources:
            if s["kind"] == "osm" and "openstreetmap" not in s.get("attribution", "").lower():
                report.error(path, 'an osm source needs "attribution": "© OpenStreetMap contributors"')
    elif track["license"] == "ODbL-1.0":
        report.warn(path, "ODbL-1.0 without an osm source: is the licence right?")
    for s in sources:
        if s["kind"] == "other":
            report.warn(path, f"source kind 'other' ({s['details']!r}): moderator, check that it is allowed")
        if "racechrono" in s["details"].lower():
            report.warn(path, "the source mentions RaceChrono: own laps recorded with it are fine, its track library is not")
    updated = dt.date.fromisoformat(track["updated"])
    if updated > dt.date.today() + dt.timedelta(days=1):
        report.error(path, f"updated {track['updated']} is in the future")


def check_geometry(path: Path, track: dict, report: Report):
    circuit = "finish" not in track
    frame = Frame(track["center"]["lat"], track["center"]["lon"])
    outline = track["outline"]
    first, last = frame.xy(outline[0]), frame.xy(outline[-1])
    end_gap = ((first[0] - last[0]) ** 2 + (first[1] - last[1]) ** 2) ** 0.5
    if circuit and end_gap > CLOSE_GAP_M:
        report.error(path, f"a circuit's outline must close: its ends are {end_gap:.0f} m apart (max {CLOSE_GAP_M})")
    line = Path2(frame, outline, closed=circuit)

    gap = line.max_gap()
    if gap > MAX_POINT_GAP_M:
        report.error(path, f"outline has a {gap:.0f} m gap between points (max {MAX_POINT_GAP_M})")
    elif gap > WARN_POINT_GAP_M:
        report.warn(path, f"outline has a {gap:.0f} m gap between points (recommended ≤ 10)")

    nearest_center = min(((x ** 2 + y ** 2) ** 0.5 for x, y in line.xy), default=0)
    if nearest_center > CENTER_MAX_M:
        report.error(path, f"center is {nearest_center:.0f} m from the outline (max {CENTER_MAX_M})")

    def place(name: str, gate: dict):
        x, y = frame.xy(gate["point"])
        hit = line.project(x, y, gate["heading"], tolerance=60)
        if hit is None:
            report.error(path, f"{name}: no part of the outline runs along heading {gate['heading']}° (reversed?)")
            return None
        s, offset, seg_heading = hit
        if offset > GATE_OFFSET_M:
            report.error(path, f"{name}: {offset:.0f} m off the outline (max {GATE_OFFSET_M})")
        if angle_diff(gate["heading"], seg_heading) > GATE_HEADING_DEG:
            report.error(path, f"{name}: heading {gate['heading']}° vs the track's {seg_heading:.0f}° there (max ±{GATE_HEADING_DEG}°)")
        lo, hi = WIDTH_WARN
        if not lo <= gate["width"] <= hi:
            report.warn(path, f"{name}: width {gate['width']} m, typical is {lo}–{hi}")
        return s

    start = place("startFinish", track["startFinish"])
    sectors = [place(f"sectors[{i}]", g) for i, g in enumerate(track["sectors"])]
    finish = None if circuit else place("finish", track["finish"])
    if start is None or None in sectors or (not circuit and finish is None):
        return

    if circuit:
        rel = [(s - start) % line.length for s in sectors]
        run = line.length
        if track["direction"] != ("ccw" if line.signed_area() > 0 else "cw"):
            report.error(path, f"direction '{track['direction']}' does not match the outline (it runs {'ccw' if line.signed_area() > 0 else 'cw'})")
    else:
        rel = [s - start for s in sectors]
        run = finish - start
        if run <= 0:
            report.error(path, "finish comes before the start along the outline (outline reversed?)")
            return
    if any(b <= a for a, b in zip(rel, rel[1:])) or any(not 0 < r < run for r in rel):
        report.error(path, "sectors are not in lap order between start and finish: " + ", ".join(f"{r:.0f} m" for r in rel))
        return
    marks = [0.0] + rel + [run]
    labels = ["startFinish"] + [f"sectors[{i}]" for i in range(len(rel))] + ["startFinish" if circuit else "finish"]
    for (a, la), (b, lb) in zip(zip(marks, labels), zip(marks[1:], labels[1:])):
        if b - a < GATE_SPACING_M:
            report.error(path, f"{la} → {lb}: {b - a:.0f} m apart (min {GATE_SPACING_M})")
        elif b - a < GATE_SPACING_WARN_M:
            report.warn(path, f"{la} → {lb}: {b - a:.0f} m apart (recommended ≥ {GATE_SPACING_WARN_M})")

    diff = abs(track["lengthM"] - run) / run
    if diff > LENGTH_ERROR:
        report.error(path, f"lengthM {track['lengthM']} vs {run:.0f} m along the outline ({diff:.0%}, max {LENGTH_ERROR:.0%})")
    elif diff > LENGTH_WARN:
        report.warn(path, f"lengthM {track['lengthM']} vs {run:.0f} m along the outline ({diff:.0%})")

    numbers = [c["number"] for c in track["corners"]]
    if len(set(numbers)) != len(numbers):
        report.error(path, "corner numbers repeat")
    corner_s = []
    for c in track["corners"]:
        x, y = frame.xy(c["apex"])
        s, offset, _ = line.project(x, y)
        if offset > CORNER_OFFSET_M:
            report.error(path, f"corner {c['number']}: apex {offset:.0f} m off the outline (max {CORNER_OFFSET_M})")
        corner_s.append((s - start) % line.length if circuit else s - start)
    if any(b <= a for a, b in zip(corner_s, corner_s[1:])):
        report.warn(path, "corners are not listed in lap order")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("files", nargs="*", type=Path)
    parser.add_argument("--no-index", action="store_true", help="skip the index.json check")
    args = parser.parse_args()

    report = Report()
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    validator = jsonschema.Draft202012Validator(schema, format_checker=jsonschema.Draft202012Validator.FORMAT_CHECKER)
    every = track_files()
    chosen = {p.resolve() for p in args.files} if args.files else set(every)
    for p in chosen - set(every):
        report.error(p, "not a .json file under tracks/")

    tracks: dict[Path, dict] = {}
    for path in every:
        try:
            raw = load_raw(path)
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            report.error(path, f"not valid JSON: {e}")
            continue
        track = to_plain(raw)
        problems = sorted(validator.iter_errors(track), key=lambda e: list(e.absolute_path))
        if problems:
            if path in chosen:
                for e in problems[:20]:
                    where = "/".join(str(p) for p in e.absolute_path) or "(root)"
                    report.error(path, f"schema: {where}: {e.message}")
            continue
        tracks[path] = track
        if path in chosen:
            check_location(path, track, report)
            check_precision(path, raw, report)
            check_sources(path, track, report)
            check_geometry(path, track, report)

    by_slug, by_id = {}, {}
    for path, track in tracks.items():
        for key, seen in (("slug", by_slug), ("id", by_id)):
            other = seen.setdefault(track[key].lower(), path)
            if other != path:
                report.error(path, f"{key} '{track[key]}' is already used by {other.relative_to(ROOT).as_posix()}")
    for path, track in tracks.items():
        parent = track.get("variantOf")
        if parent is None or path not in chosen:
            continue
        target = by_slug.get(parent)
        if parent == track["slug"]:
            report.error(path, "variantOf points at itself")
        elif target is None:
            report.error(path, f"variantOf '{parent}': no such track")
        else:
            if tracks[target].get("variantOf"):
                report.warn(path, f"variantOf '{parent}' is a variant itself: point at the main layout")
            if tracks[target]["country"] != track["country"]:
                report.error(path, f"variantOf '{parent}' is in another country")

    if not args.no_index:
        import build_index
        current = (ROOT / "index.json").read_text(encoding="utf-8") if (ROOT / "index.json").exists() else ""
        try:
            fresh = build_index.build()
        except (KeyError, TypeError, ValueError) as e:
            report.error(ROOT / "index.json", f"cannot be built until the track files are valid ({e!r})")
        else:
            if current != fresh:
                report.error(ROOT / "index.json", "out of date: run python3 tools/build_index.py and commit the result")

    print(f"{len(chosen)} file(s) checked: {report.errors} error(s), {report.warnings} warning(s)")
    return 1 if report.errors else 0


if __name__ == "__main__":
    sys.exit(main())
