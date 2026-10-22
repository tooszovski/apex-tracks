#!/usr/bin/env python3
"""Turns a "New track" issue into a track file; used by .github/workflows/issue-to-pr.yml.

    python3 tools/issue_to_track.py extract --event "$GITHUB_EVENT_PATH" --out "$RUNNER_TEMP/bot"
    python3 tools/issue_to_track.py report  --event "$GITHUB_EVENT_PATH" --out "$RUNNER_TEMP/bot" \\
                                            --validate-log validate.txt --validate-status 0

`extract` reads the issue form body from the event payload, gets the track JSON (the "Track JSON" section, else the
first attached .json file, else a gist), puts the issue author in `author` when the file has none and writes the
file to tracks/<country>/<slug>.json. `report` turns the validator output into the issue comment (on errors) or the
PR body (on success). The issue body is untrusted: it is only parsed as text and JSON, never run, and only files
from GitHub's attachment and gist hosts are downloaded, with a size limit.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from decimal import Decimal
from pathlib import Path
from typing import Callable

from trackfile import ROOT, TRACKS, canonical

MAX_BYTES = 2 * 1024 * 1024
MAX_MESSAGE = 300
SECTION = "Track JSON"
SLUG = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
COUNTRY = re.compile(r"^[A-Z]{2}$")
HANDLE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9]|-(?=[A-Za-z0-9])){0,38}$")

# Where an attached file may be linked from. The form puts drag-and-dropped files on github.com/user-attachments;
# older uploads used the repository's /files/ path and the user-images host.
ATTACHMENT = re.compile(
    r"https://(?:github\.com/user-attachments/files/|github\.com/tooszovski/apex-tracks/files/"
    r"|user-images\.githubusercontent\.com/|objects\.githubusercontent\.com/)[^\s)\]>\"'<]+?\.json(?![\w.])",
    re.IGNORECASE)
GIST = re.compile(r"https://gist\.github\.com/(?:[A-Za-z0-9-]+/)?([0-9a-f]{20,40})\b", re.IGNORECASE)
GIST_RAW = re.compile(r"https://gist\.githubusercontent\.com/[A-Za-z0-9-]+/[0-9a-f]{20,40}/raw/[^\s)\]>\"'<]+",
                      re.IGNORECASE)
# Hosts a download may start on or be redirected to (attachments redirect to object storage).
FETCH_HOSTS = ("github.com", "api.github.com", "gist.githubusercontent.com", "user-images.githubusercontent.com",
               "objects.githubusercontent.com", "private-user-images.githubusercontent.com")
FETCH_HOST_PATTERNS = (re.compile(r"^github-production-[a-z0-9-]+\.s3\.amazonaws\.com$"),
                       re.compile(r"^[a-z0-9-]+\.githubusercontent\.com$"))


class SubmissionError(Exception):
    """A problem the submitter has to fix; the message goes to the issue comment."""


# MARK: - Downloads

def host_allowed(url: str) -> bool:
    try:
        parts = urllib.parse.urlsplit(url)
        if parts.scheme != "https" or parts.username or parts.password or parts.port not in (None, 443):
            return False
    except ValueError:
        return False
    host = (parts.hostname or "").lower()
    return host in FETCH_HOSTS or any(p.match(host) for p in FETCH_HOST_PATTERNS)


class _Redirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not host_allowed(newurl):
            raise SubmissionError(f"the download was redirected to a host that is not allowed ({urllib.parse.urlsplit(newurl).hostname})")
        new = super().redirect_request(req, fp, code, msg, headers, newurl)
        # The token is for api.github.com only; never send it to the storage host.
        if new is not None and urllib.parse.urlsplit(newurl).hostname != "api.github.com":
            new.remove_header("Authorization")
        return new


def fetch(url: str, max_bytes: int = MAX_BYTES) -> bytes:
    if not host_allowed(url):
        raise SubmissionError(f"downloads are allowed only from GitHub attachments and gists, not {url}")
    headers = {"User-Agent": "apex-tracks-issue-bot", "Accept": "*/*"}
    token = os.environ.get("GH_TOKEN")
    if token and urllib.parse.urlsplit(url).hostname == "api.github.com":
        headers["Authorization"] = f"Bearer {token}"
        headers["Accept"] = "application/vnd.github+json"
    opener = urllib.request.build_opener(_Redirects())
    try:
        with opener.open(urllib.request.Request(url, headers=headers), timeout=30) as resp:
            data = resp.read(max_bytes + 1)
    except urllib.error.URLError as e:
        raise SubmissionError(f"cannot download {url}: {e}") from None
    if len(data) > max_bytes:
        raise SubmissionError(f"{url} is larger than {max_bytes // (1024 * 1024)} MB")
    return data


# MARK: - The issue body

def form_section(body: str, label: str) -> str | None:
    """The text under '### <label>' in an issue form body, up to the next '### ' heading."""
    lines = body.replace("\r\n", "\n").split("\n")
    for i, line in enumerate(lines):
        if line.strip() == f"### {label}":
            rest = []
            for line2 in lines[i + 1:]:
                if line2.startswith("### "):
                    break
                rest.append(line2)
            return "\n".join(rest).strip()
    return None


def strip_fences(text: str) -> str:
    """The form wraps the field in ```json … ```; a driver may paste a fenced block into it as well."""
    text = text.strip()
    while True:
        m = re.fullmatch(r"(`{3,}|~{3,})[^\n]*\n(.*?)\n?\1\s*", text, re.DOTALL)
        if not m:
            return text
        text = m.group(2).strip()


def parse_track(text: str, where: str) -> dict:
    if len(text.encode("utf-8")) > MAX_BYTES:
        raise SubmissionError(f"the JSON in {where} is larger than {MAX_BYTES // (1024 * 1024)} MB")
    try:
        track = json.loads(text, parse_float=Decimal)
    except json.JSONDecodeError as e:
        raise SubmissionError(f"the JSON in {where} is not valid: {e.msg} at line {e.lineno}, column {e.colno}") from None
    if not isinstance(track, dict):
        raise SubmissionError(f"the JSON in {where} is not an object with track fields")
    return track


def gist_json(gist_id: str, get: Callable[[str], bytes]) -> str:
    try:
        meta = json.loads(get(f"https://api.github.com/gists/{gist_id}"))
        files = list((meta.get("files") or {}).values())
    except (json.JSONDecodeError, AttributeError):
        raise SubmissionError(f"gist {gist_id} cannot be read") from None
    json_files = [f for f in files if isinstance(f, dict) and str(f.get("filename", "")).lower().endswith(".json")]
    if json_files:
        entry = json_files[0]
    elif len(files) == 1 and isinstance(files[0], dict):
        entry = files[0]
    else:
        raise SubmissionError(f"gist {gist_id} must hold one .json file")
    if entry.get("truncated") or entry.get("content") is None:
        return get(str(entry.get("raw_url", ""))).decode("utf-8")
    return entry["content"]


def extract_track(body: str, get: Callable[[str], bytes] = fetch) -> tuple[dict, str]:
    """(track, where it came from). Order: the JSON in the "Track JSON" section, the first attached .json, a gist."""
    body = body or ""
    section = form_section(body, SECTION)
    if section is not None:
        inner = strip_fences(section)
        where = f'the "{SECTION}" section'
        if inner.startswith("{"):
            return parse_track(inner, where), where
        if inner.startswith("["):  # a JSON array, or a Markdown link to an attached file
            try:
                json.loads(inner)
            except json.JSONDecodeError:
                pass
            else:
                raise SubmissionError(f"the JSON in {where} is not an object with track fields")
    m = ATTACHMENT.search(body)
    if m:
        url = m.group(0)
        try:
            text = get(url).decode("utf-8-sig")
        except UnicodeDecodeError:
            raise SubmissionError(f"the attached file {url} is not UTF-8 text") from None
        return parse_track(text, f"the attached file {url}"), f"the attached file {url}"
    m = GIST_RAW.search(body)
    if m:
        return parse_track(get(m.group(0)).decode("utf-8-sig"), f"the gist {m.group(0)}"), f"the gist {m.group(0)}"
    m = GIST.search(body)
    if m:
        url = m.group(0)
        return parse_track(gist_json(m.group(1), get), f"the gist {url}"), f"the gist {url}"
    other = re.search(r"https?://[^\s)\]>\"'<]+\.json\b", body, re.IGNORECASE)
    if other:
        raise SubmissionError(f"{other.group(0)} is not downloaded: attach the file to the issue (drag it into the form) "
                              f"or link a gist")
    if section is not None and strip_fences(section) not in ("", "_No response_"):
        raise SubmissionError(f'the "{SECTION}" section holds no JSON object, no attached .json file and no gist link')
    raise SubmissionError(f'no track JSON: paste it into the "{SECTION}" section, attach the .json file or link a gist')


def fill_author(track: dict, login: str) -> bool:
    """The app leaves `author` out when the driver gave no handle: the issue author marked it. True if filled."""
    if isinstance(track.get("author"), str) and track["author"].strip():
        return False
    track["author"] = login
    return True


def target_path(track: dict) -> Path:
    slug, country = track.get("slug"), track.get("country")
    if not isinstance(slug, str) or not SLUG.match(slug) or len(slug) > 64:
        raise SubmissionError('"slug" is missing or not Latin kebab-case (for example "igora-drive")')
    if not isinstance(country, str) or not COUNTRY.match(country):
        raise SubmissionError('"country" is missing or not an ISO 3166-1 alpha-2 code in upper case (for example "RU")')
    return TRACKS / country.lower() / f"{slug}.json"


# MARK: - Messages

def code(text: str) -> str:
    """Untrusted text as an inline code span: no mentions, links or markup."""
    text = " ".join(str(text).split()).replace("`", "'")
    if len(text) > MAX_MESSAGE:
        text = text[:MAX_MESSAGE - 1] + "…"
    return f"`{text}`"


LINE = re.compile(r"^(ERROR|WARNING)\s+(\S+): (.*)$")
ANNOTATION = re.compile(r"^::(error|warning) file=([^:]+)::(.*)$")


def parse_validator_output(text: str) -> tuple[list[str], list[str]]:
    """validate.py's output, plain or as GitHub annotations → (errors, warnings)."""
    errors, warnings = [], []
    for line in text.splitlines():
        m = LINE.match(line) or ANNOTATION.match(line)
        if m:
            (errors if m.group(1).lower() == "error" else warnings).append(f"{m.group(2)}: {m.group(3)}")
    return errors, warnings


def render_failure(errors: list[str], warnings: list[str], login: str) -> str:
    lines = [f"@{login}, the bot could not turn this submission into a pull request. Please fix the following and "
             f"edit the issue (or attach a corrected file); a moderator will then add `accepted` again.", "",
             "**Errors**", ""]
    lines += [f"- {code(e)}" for e in errors] or ["- `unknown error, see the workflow log`"]
    if warnings:
        lines += ["", "**Warnings** (for the moderator to look at)", ""] + [f"- {code(w)}" for w in warnings]
    lines += ["", "The rules: [CONTRIBUTING.md](../blob/main/CONTRIBUTING.md). Labelled `needs-changes`; without an "
                  "answer the submission is closed after 30 days."]
    return "\n".join(lines) + "\n"


def render_pr_body(number: int, issue_url: str, login: str, path: str, warnings: list[str], notes: list[str]) -> str:
    lines = [f"Closes #{number}", "",
             f"Track submitted by @{login} in [#{number}]({issue_url}), turned into a file by the issue-to-pr bot: "
             f"`{path}` and `index.json`. The validator passed.", ""]
    if notes:
        lines += ["**Notes**", ""] + [f"- {n}" for n in notes] + [""]
    lines += ["**Validator warnings**", ""]
    lines += [f"- {code(w)}" for w in warnings] or ["- none"]
    lines += ["", "**Moderator**: check the lines and the outline against satellite imagery or a recorded lap, look "
                  "for duplicates and the source (CONTRIBUTING.md → By a moderator), then approve and merge. To rebuild "
                  "this PR from an edited issue, remove `accepted` from the issue and add it again (this replaces the "
                  "branch)."]
    return "\n".join(lines) + "\n"


# MARK: - Commands

def load_issue(event_path: Path) -> dict:
    event = json.loads(event_path.read_text(encoding="utf-8"))
    issue = event["issue"]
    login = issue["user"]["login"]
    if not HANDLE.match(login.removesuffix("[bot]")):
        raise SystemExit(f"unexpected issue author login {login!r}")
    return {"number": int(issue["number"]), "body": issue.get("body") or "", "login": login,
            "url": issue["html_url"]}


def set_output(**values):
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a", encoding="utf-8") as f:
            for k, v in values.items():
                f.write(f"{k}={v}\n")


def cmd_extract(args) -> int:
    issue = load_issue(args.event)
    args.out.mkdir(parents=True, exist_ok=True)
    result = {"ok": False, "path": "", "errors": [], "notes": []}
    try:
        track, where = extract_track(issue["body"])
        result["notes"].append(f"JSON taken from {where}.")
        if fill_author(track, issue["login"]):
            result["notes"].append(f"The file had no `author`: set to the issue author @{issue['login']}.")
        elif track["author"] != issue["login"]:
            result["notes"].append(f"`author` in the file is {code(track['author'])}; the issue author is @{issue['login']}.")
        path = target_path(track)
        if path.exists():
            raise SubmissionError(f"{path.relative_to(ROOT).as_posix()} already exists in the database: choose another "
                                  f"slug for a new layout, or use the Fix a track form for a change")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(canonical(track), encoding="utf-8")
        result.update(ok=True, path=path.relative_to(ROOT).as_posix())
    except SubmissionError as e:
        result["errors"].append(str(e))
    (args.out / "extract.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    set_output(ok=str(result["ok"]).lower(), path=result["path"])
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def cmd_report(args) -> int:
    issue = load_issue(args.event)
    result = json.loads((args.out / "extract.json").read_text(encoding="utf-8"))
    errors, warnings = list(result["errors"]), []
    if result["ok"]:
        log = args.validate_log.read_text(encoding="utf-8") if args.validate_log and args.validate_log.exists() else ""
        v_errors, warnings = parse_validator_output(log)
        errors += v_errors
        if args.validate_status != 0 and not v_errors:
            errors.append("the validator failed without a message: see the workflow log")
    ok = not errors
    if ok:
        text = render_pr_body(issue["number"], issue["url"], issue["login"], result["path"], warnings, result["notes"])
        (args.out / "pr-body.md").write_text(text, encoding="utf-8")
    else:
        text = render_failure(errors, warnings, issue["login"])
        (args.out / "failure.md").write_text(text, encoding="utf-8")
    set_output(ok=str(ok).lower())
    print(text)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("extract", "report"):
        p = sub.add_parser(name)
        p.add_argument("--event", type=Path, required=True, help="the issues event payload ($GITHUB_EVENT_PATH)")
        p.add_argument("--out", type=Path, required=True, help="directory for the bot's files")
        if name == "report":
            p.add_argument("--validate-log", type=Path)
            p.add_argument("--validate-status", type=int, default=0)
    args = parser.parse_args()
    return cmd_extract(args) if args.command == "extract" else cmd_report(args)


if __name__ == "__main__":
    sys.exit(main())
