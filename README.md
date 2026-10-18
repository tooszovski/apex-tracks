# Apex Tracks — an open database of race-track markup

An open database of race tracks for the **Apex** iOS app (lap timing and a telemetry-based driving coach).
It holds what is needed to time laps and analyse a session: the start/finish line, sector lines, numbered and named
corners, the lap outline and the surface. Drivers mark the tracks themselves; moderators review them.

The data and the tooling are open (MIT) and can be used outside the app as well.

## How it works

```
a driver marks a track in the app
        │  "Send to the database"
        ▼
an issue from the "New track" form (JSON inside)  ── or a PR with the file directly
        │  moderator: CI + check against satellite imagery / a recorded lap
        ▼
PR → approval → merge into main
        │
        ▼
index.json + tracks/…/*.json  ──►  the app downloads the database and offers tracks near the driver
```

1. A driver laps the track with Apex, places the start/finish and sector lines in the app and adjusts the corners.
2. On the track page, "Send to the database" checks the markup with the same rules as CI and opens a prefilled issue
   form in this repository. No personal data is sent: only the markup and, optionally, a GitHub handle.
   A PR with the file is welcome too.
3. A moderator reviews the markup (CI plus satellite imagery or a recorded lap) and merges it.
4. After the merge the track is listed in `index.json`; the app fetches the index and the track files and offers the
   track to every user. A driver's own markup always takes priority: updating it from the database is an explicit action.

## What's inside

| Path | What it is |
|---|---|
| `tracks/<country>/<slug>.json` | one track layout ([format](schema/track.schema.json)) |
| `tracks/_example/` | a synthetic sample in the middle of the ocean, not part of the index |
| `index.json` | the list of tracks: slug, name, country, centre, path, sha256, date — built by `tools/build_index.py` |
| `schema/track.schema.json` | JSON Schema (draft 2020-12) of a track file |
| `tools/validate.py` | checks: schema, geometry, licences, uniqueness, index freshness |
| `tools/format_track.py` | rewrites a file in the canonical layout |
| [`CONTRIBUTING.md`](CONTRIBUTING.md) | markup and moderation rules — **read before submitting** |

## Using the data outside the app

```sh
curl -s https://raw.githubusercontent.com/tooszovski/apex-tracks/main/index.json
curl -s https://raw.githubusercontent.com/tooszovski/apex-tracks/main/tracks/<country>/<slug>.json
```

- Coordinates are WGS 84 decimal degrees; a line's `heading` is the compass bearing of the direction of travel
  (0° is north); `width` is the full width of the line in metres.
- `sha256` in the index is computed over the file's bytes: download only what has changed.
- The format is versioned by `formatVersion`; incompatible changes only come with a new number.
- Files with `"license": "ODbL-1.0"` contain OpenStreetMap data: using them requires the attribution
  "© OpenStreetMap contributors", and a derived database must be ODbL-licensed as well.

## Licence

[MIT](LICENSE) — tooling, schema and data. Exception: files with `"license": "ODbL-1.0"` (derived from OpenStreetMap)
are available under the [ODbL 1.0](https://opendatacommons.org/licenses/odbl/1-0/), © OpenStreetMap contributors.

## Credits

- The drivers who mark and check the tracks — each file names its `author` and `contributors`.
- The OpenStreetMap contributors, for the data where it is used.
