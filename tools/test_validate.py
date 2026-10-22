"""The validator catches the mistakes it is there for: python3 -m unittest discover tools"""

import copy
import json
import unittest

import jsonschema

import validate
from trackfile import SCHEMA, TRACKS, load_raw, to_plain

EXAMPLE = TRACKS / "_example" / "example-circuit.json"


class Collect(validate.Report):
    def __init__(self):
        super().__init__()
        self.annotate = False
        self.messages = []

    def _emit(self, level, path, message):
        self.messages.append((level, message))


def run(mutate=None):
    track = copy.deepcopy(to_plain(load_raw(EXAMPLE)))
    if mutate:
        mutate(track)
    report = Collect()
    validate.check_location(EXAMPLE, track, report)
    validate.check_sources(EXAMPLE, track, report)
    validate.check_geometry(EXAMPLE, track, report)
    return [m for level, m in report.messages if level == "error"]


class ValidatorTests(unittest.TestCase):
    def test_example_is_clean(self):
        self.assertEqual(run(), [])

    def test_reversed_start_line(self):
        def flip(t):
            t["startFinish"]["heading"] = (t["startFinish"]["heading"] + 180) % 360
        self.assertTrue(any("startFinish" in m for m in run(flip)))

    def test_sectors_out_of_order(self):
        self.assertTrue(any("lap order" in m for m in run(lambda t: t["sectors"].reverse())))

    def test_sector_too_close_to_start(self):
        def near(t):
            t["sectors"][0] = {"point": t["outline"][10], "heading": t["startFinish"]["heading"], "width": 30}
        self.assertTrue(any("apart" in m for m in run(near)))

    def test_line_off_the_track(self):
        def off(t):
            t["sectors"][0]["point"] = {"lat": t["sectors"][0]["point"]["lat"] + 0.001, "lon": t["sectors"][0]["point"]["lon"]}
        self.assertTrue(any("off the outline" in m for m in run(off)))

    def test_wrong_direction(self):
        self.assertTrue(any("direction" in m for m in run(lambda t: t.update(direction="ccw"))))

    def test_open_circuit(self):
        self.assertTrue(any("must close" in m for m in run(lambda t: t.update(outline=t["outline"][:-60]))))

    def test_wrong_length(self):
        self.assertTrue(any("lengthM" in m for m in run(lambda t: t.update(lengthM=3500))))

    def test_osm_needs_odbl(self):
        def osm(t):
            t["outlineSource"] = {"kind": "osm", "details": "way 123", "attribution": "© OpenStreetMap contributors"}
        self.assertTrue(any("ODbL" in m for m in run(osm)))
        def osm_ok(t):
            osm(t)
            t["license"] = "ODbL-1.0"
        self.assertEqual(run(osm_ok), [])

    def test_example_flag_required(self):
        self.assertTrue(any("example" in m for m in run(lambda t: t.pop("example"))))

    def test_gate_width_limits(self):
        validator = jsonschema.Draft202012Validator(json.loads(SCHEMA.read_text(encoding="utf-8")))
        track = to_plain(load_raw(EXAMPLE))
        for width, valid in ((100, True), (101, False), (4, False)):
            t = copy.deepcopy(track)
            t["startFinish"]["width"] = width
            self.assertEqual(validator.is_valid(t), valid, width)


if __name__ == "__main__":
    unittest.main()
