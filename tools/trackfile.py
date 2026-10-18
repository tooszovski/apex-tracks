"""Shared helpers: reading and writing track files, flat-earth geometry around a track."""

from __future__ import annotations

import json
import math
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TRACKS = ROOT / "tracks"
SCHEMA = ROOT / "schema" / "track.schema.json"
INDEX = ROOT / "index.json"
EXAMPLE_DIR = "_example"
EARTH_RADIUS = 6_371_008.8


def track_files() -> list[Path]:
    return sorted(p for p in TRACKS.rglob("*.json"))


def load_raw(path: Path) -> dict:
    """Numbers as Decimal: keeps the written number of decimals for the precision check."""
    with path.open(encoding="utf-8") as f:
        return json.load(f, parse_float=Decimal)


def to_plain(value):
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, dict):
        return {k: to_plain(v) for k, v in value.items()}
    if isinstance(value, list):
        return [to_plain(v) for v in value]
    return value


def decimals(value) -> int:
    if isinstance(value, Decimal):
        exponent = value.as_tuple().exponent
        return -exponent if isinstance(exponent, int) and exponent < 0 else 0
    return 0


# MARK: - Canonical formatting

KEY_ORDER = [
    "$schema", "formatVersion", "example", "id", "slug", "name", "localName", "country", "city", "center",
    "startFinish", "finish", "sectors", "corners", "outline", "surface", "lengthM", "direction", "variantOf",
    "source", "outlineSource", "license", "author", "contributors", "raceChronoID", "notes", "updated",
]


def _coord(x) -> str:
    text = f"{float(x):.7f}"
    return text[:-1] if text.endswith("0") else text


def _point(p: dict) -> str:
    return f'{{"lat": {_coord(p["lat"])}, "lon": {_coord(p["lon"])}}}'


def _is_point(v) -> bool:
    return isinstance(v, dict) and set(v) == {"lat", "lon"}


def _dump(value, indent: int) -> str:
    pad, inner = "  " * indent, "  " * (indent + 1)
    if _is_point(value):
        return _point(value)
    if isinstance(value, dict):
        if not value:
            return "{}"
        items = [f"{inner}{json.dumps(k, ensure_ascii=False)}: {_dump(v, indent + 1)}" for k, v in value.items()]
        return "{\n" + ",\n".join(items) + "\n" + pad + "}"
    if isinstance(value, list):
        if not value:
            return "[]"
        return "[\n" + ",\n".join(inner + _dump(v, indent + 1) for v in value) + "\n" + pad + "]"
    if isinstance(value, Decimal):
        value = float(value)
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return json.dumps(value, ensure_ascii=False)


def canonical(track: dict) -> str:
    ordered = {k: track[k] for k in KEY_ORDER if k in track}
    ordered.update({k: v for k, v in track.items() if k not in ordered})
    return _dump(ordered, 0) + "\n"


# MARK: - Geometry

class Frame:
    """Local east/north metres around an origin; good to well under a metre over a track's extent."""

    def __init__(self, lat: float, lon: float):
        self.lat0, self.lon0 = lat, lon
        self.my = math.pi / 180 * EARTH_RADIUS
        self.mx = self.my * math.cos(math.radians(lat))

    def xy(self, p: dict) -> tuple[float, float]:
        return ((p["lon"] - self.lon0) * self.mx, (p["lat"] - self.lat0) * self.my)

    def geo(self, x: float, y: float) -> dict:
        return {"lat": self.lat0 + y / self.my, "lon": self.lon0 + x / self.mx}


def bearing(dx: float, dy: float) -> float:
    return math.degrees(math.atan2(dx, dy)) % 360


def angle_diff(a: float, b: float) -> float:
    return abs((a - b + 180) % 360 - 180)


class Path2:
    """Polyline of the outline in local metres; a circuit is closed by joining the last point to the first."""

    def __init__(self, frame: Frame, points: list[dict], closed: bool):
        self.xy = [frame.xy(p) for p in points]
        if closed and self.xy and self.xy[0] != self.xy[-1]:
            self.xy.append(self.xy[0])
        self.cum = [0.0]
        for (ax, ay), (bx, by) in zip(self.xy, self.xy[1:]):
            self.cum.append(self.cum[-1] + math.hypot(bx - ax, by - ay))
        self.length = self.cum[-1]

    def segments(self):
        for i, ((ax, ay), (bx, by)) in enumerate(zip(self.xy, self.xy[1:])):
            yield i, ax, ay, bx, by

    def project(self, x: float, y: float, heading: float | None = None, tolerance: float = 180):
        """(s, offset, segment heading) of the nearest place, among segments running within `tolerance` of `heading`."""
        best = None
        for i, ax, ay, bx, by in self.segments():
            dx, dy = bx - ax, by - ay
            len2 = dx * dx + dy * dy
            if len2 == 0:
                continue
            seg_heading = bearing(dx, dy)
            if heading is not None and angle_diff(heading, seg_heading) > tolerance:
                continue
            f = min(max(((x - ax) * dx + (y - ay) * dy) / len2, 0), 1)
            px, py = ax + f * dx, ay + f * dy
            d = math.hypot(x - px, y - py)
            if best is None or d < best[1]:
                best = (self.cum[i] + f * math.sqrt(len2), d, seg_heading)
        return best

    def max_gap(self) -> float:
        return max((b - a for a, b in zip(self.cum, self.cum[1:])), default=0)

    def signed_area(self) -> float:
        return 0.5 * sum(ax * by - bx * ay for _, ax, ay, bx, by in self.segments())
