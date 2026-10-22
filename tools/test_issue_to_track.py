"""The issue bot gets the track out of an issue form body and nothing else: python3 -m unittest discover tools"""

import copy
import json
import unittest
from decimal import Decimal

import issue_to_track as bot
from trackfile import ROOT, TRACKS, load_raw, to_plain

EXAMPLE = TRACKS / "_example" / "example-circuit.json"
ATTACHMENT = "https://github.com/user-attachments/files/17000001/igora-drive.json"


def sample_json(**changes) -> str:
    track = to_plain(load_raw(EXAMPLE))
    track.pop("author")
    track.update(changes)
    return json.dumps(track, ensure_ascii=False, indent=2)


def form_body(track_json: str, notes: str = "_No response_") -> str:
    """What GitHub writes for the New track form (render: json wraps the field in a fence)."""
    return (
        "### Track and layout name\n\nExample Circuit — Full\n\n"
        "### Country (ISO 3166-1 alpha-2) and town\n\nZZ, Nowhere\n\n"
        "### What is marked\n\n- [X] Start/finish\n- [X] Sectors\n\n"
        "### Data source\n\nMy own GPS session (own-gps)\n\n"
        "### Source details\n\nRaceBox Mini S, 25 Hz, 2026-08-12\n\n"
        f"### Track JSON\n\n```json\n{track_json}\n```\n\n"
        f"### Notes\n\n{notes}\n\n"
        "### Confirmations\n\n- [X] own data\n- [X] licence\n- [X] no personal data\n"
    )


def no_network(url):
    raise AssertionError(f"unexpected download of {url}")


class ExtractTests(unittest.TestCase):
    def test_json_block(self):
        track, where = bot.extract_track(form_body(sample_json()), no_network)
        self.assertEqual(track["slug"], "example-circuit")
        self.assertIn("Track JSON", where)
        # Coordinates stay Decimal, so the precision check sees what the driver wrote.
        self.assertIsInstance(track["center"]["lat"], Decimal)

    def test_json_block_with_crlf_and_extra_fence(self):
        body = form_body("```json\n" + sample_json() + "\n```").replace("\n", "\r\n")
        track, _ = bot.extract_track(body, no_network)
        self.assertEqual(track["slug"], "example-circuit")

    def test_attachment_link(self):
        seen = []

        def get(url):
            seen.append(url)
            return sample_json(slug="from-file").encode()

        body = form_body(f"[igora-drive.json]({ATTACHMENT})")
        track, where = bot.extract_track(body, get)
        self.assertEqual(seen, [ATTACHMENT])
        self.assertEqual(track["slug"], "from-file")
        self.assertIn(ATTACHMENT, where)

    def test_attachment_link_in_notes_when_section_empty(self):
        body = form_body("_No response_", notes=f"File: {ATTACHMENT}")
        track, _ = bot.extract_track(body, lambda url: sample_json().encode())
        self.assertEqual(track["slug"], "example-circuit")

    def test_gist_link(self):
        gist_id = "0123456789abcdef0123456789abcdef"

        def get(url):
            self.assertEqual(url, f"https://api.github.com/gists/{gist_id}")
            return json.dumps({"files": {"README.md": {"filename": "README.md", "content": "hi"},
                                         "track.json": {"filename": "track.json", "content": sample_json()}}}).encode()

        body = form_body(f"Too long, see https://gist.github.com/someone/{gist_id}")
        track, where = bot.extract_track(body, get)
        self.assertEqual(track["slug"], "example-circuit")
        self.assertIn("gist", where)

    def test_no_json(self):
        with self.assertRaisesRegex(bot.SubmissionError, "no track JSON"):
            bot.extract_track(form_body("_No response_"), no_network)
        with self.assertRaisesRegex(bot.SubmissionError, "holds no JSON"):
            bot.extract_track(form_body("I will send it later"), no_network)
        with self.assertRaisesRegex(bot.SubmissionError, "no track JSON"):
            bot.extract_track("", no_network)

    def test_invalid_json(self):
        with self.assertRaisesRegex(bot.SubmissionError, "not valid: .* line"):
            bot.extract_track(form_body('{"slug": "x",}'), no_network)
        with self.assertRaisesRegex(bot.SubmissionError, "not an object"):
            bot.extract_track(form_body("[1, 2]"), no_network)

    def test_too_large(self):
        big = '{"notes": "' + "x" * (bot.MAX_BYTES + 1) + '"}'
        with self.assertRaisesRegex(bot.SubmissionError, "larger than"):
            bot.extract_track(form_body(big), no_network)

    def test_disallowed_host_is_not_downloaded(self):
        body = form_body("[track.json](https://evil.example.com/user-attachments/files/1/track.json)")
        with self.assertRaisesRegex(bot.SubmissionError, "evil.example.com.* is not downloaded"):
            bot.extract_track(body, no_network)

    def test_host_allowlist(self):
        for url in (ATTACHMENT, "https://objects.githubusercontent.com/x/track.json",
                    "https://github-production-user-asset-6210df.s3.amazonaws.com/1/track.json",
                    "https://api.github.com/gists/0123456789abcdef0123"):
            self.assertTrue(bot.host_allowed(url), url)
        for url in ("http://github.com/user-attachments/files/1/t.json", "https://evil.example.com/t.json",
                    "https://github.com.evil.example.com/t.json", "https://user@github.com/t.json",
                    "https://github.com:8443/t.json", "file:///etc/passwd", "https://169.254.169.254/latest"):
            self.assertFalse(bot.host_allowed(url), url)
        with self.assertRaisesRegex(bot.SubmissionError, "not allowed|only from"):
            bot.fetch("https://evil.example.com/t.json")


class AuthorTests(unittest.TestCase):
    def test_fill_author_when_missing_or_empty(self):
        track = json.loads(sample_json())
        self.assertTrue(bot.fill_author(track, "driver-1"))
        self.assertEqual(track["author"], "driver-1")
        track["author"] = "  "
        self.assertTrue(bot.fill_author(track, "driver-1"))
        self.assertEqual(track["author"], "driver-1")

    def test_keep_given_author(self):
        track = json.loads(sample_json(author="marker"))
        self.assertFalse(bot.fill_author(track, "driver-1"))
        self.assertEqual(track["author"], "marker")


class PathTests(unittest.TestCase):
    def test_path_from_country_and_slug(self):
        self.assertEqual(bot.target_path({"slug": "igora-drive", "country": "RU"}), TRACKS / "ru" / "igora-drive.json")

    def test_path_cannot_escape(self):
        for slug, country in (("../../x", "RU"), ("ok", "../"), ("Igora", "RU"), ("ok", "ru"), (None, "RU")):
            with self.assertRaises(bot.SubmissionError, msg=(slug, country)):
                bot.target_path({"slug": slug, "country": country})


class MessageTests(unittest.TestCase):
    def test_validator_output(self):
        log = ("ERROR   tracks/zz/a.json: startFinish: 25 m off the outline (max 20)\n"
               "WARNING tracks/zz/a.json: startFinish: width 60 m, typical is 15–50\n"
               "1 file(s) checked: 1 error(s), 1 warning(s)\n")
        errors, warnings = bot.parse_validator_output(log)
        self.assertEqual(errors, ["tracks/zz/a.json: startFinish: 25 m off the outline (max 20)"])
        self.assertEqual(len(warnings), 1)
        errors, warnings = bot.parse_validator_output("::error file=tracks/zz/a.json::lengthM 3500 vs 2644 m\n"
                                                      "::warning file=index.json::w\n")
        self.assertEqual((errors, warnings), (["tracks/zz/a.json: lengthM 3500 vs 2644 m"], ["index.json: w"]))

    def test_untrusted_text_is_inert(self):
        text = bot.render_failure(["source 'x' mentions @someone ![img](https://e.x/i.png) `rm`"], [], "driver-1")
        self.assertIn("`source 'x' mentions @someone ![img](https://e.x/i.png) 'rm'`", text)
        self.assertTrue(text.startswith("@driver-1,"))

    def test_pr_body(self):
        body = bot.render_pr_body(7, "https://github.com/tooszovski/apex-tracks/issues/7", "driver-1",
                                  "tracks/ru/igora-drive.json", ["w1"], ["note"])
        self.assertTrue(body.startswith("Closes #7\n"))
        self.assertIn("- `w1`", body)
        self.assertIn("issues/7", body)


if __name__ == "__main__":
    unittest.main()
