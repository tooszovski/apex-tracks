# Markup and moderation rules

Markup from this database ends up in every driver's app: a wrong start line means wrong laps for everyone.
That is why the rules are strict and the checks are automated wherever possible (`tools/validate.py`).

The easiest way is to mark the track in the Apex app (from your own session) and tap "Send to the database" — the app
builds the file in the right format. Below is what the file must contain if you edit it by hand or review a submission.

## The file

- **One layout — one file:** `tracks/<country>/<slug>.json`.
  - `<country>` is the ISO 3166-1 alpha-2 code in lower case (`ru`, `kz`, `de`); `country` in the file is the same
    code in upper case.
  - `slug` is Latin kebab-case and equals the file name: `igora-drive`, `adm-raceway`, `moscow-raceway-fim`.
- **Layouts of one venue** (full, short, club, reverse) are separate files with a common slug prefix.
  The main layout has no `variantOf`; the others point at it: `"variantOf": "igora-drive"`.
  A reverse layout is a layout of its own too (another direction, other lines).
- `id` is a UUID, assigned once and never changed (the app recognises its own copy of the track by it).
- Format: [`schema/track.schema.json`](schema/track.schema.json); sample:
  [`tracks/_example/example-circuit.json`](tracks/_example/example-circuit.json) (synthetic, in the middle of the
  ocean, not part of the index).
- Before committing: `python3 tools/format_track.py <file>` — rewrites the file in one layout (key order, one outline
  point per line, 6–7 decimals in coordinates) so that review diffs stay readable.

## Names

- `name` — the official name in Latin script, with the layout after a dash: `Igora Drive — Full`, `ADM Raceway — Club`.
- `localName` — the name as used locally, in the local script (e.g. Cyrillic for a Russian track).
- `city` — the nearest town and region: `Priozersk, Leningrad Oblast`.

## Coordinates

- WGS 84, decimal degrees, **at least 6 decimals** (≈ 0.1 m). `format_track.py` writes 6–7 decimals.
- `center` — the middle of the track (the app uses it to find tracks near the driver); no further than 3 km from the outline.

## Start/finish (`startFinish`)

- Placed **on the timing line** (the painted line across the track / the transponder loop), not "somewhere on the straight".
- `heading` — the compass bearing of the **direction of travel** across the line: 0° north, 90° east. The validator
  requires it to match the outline's direction at that spot within ±30°.
- `width` — the full width of the line in metres. It must cover the track with a margin for GPS error,
  but **must not reach a parallel straight or the pit lane**, or a lap will be counted in the wrong place.
  Typically **20–40 m**; 5–100 m is allowed (the validator warns outside 15–50). Lines imported from RaceChrono
  are often 100 m wide: narrow them where a parallel straight or the pit lane is near.
- The middle of the line is no further than 20 m from the outline.

## Separate finish (`finish`)

- Only for point-to-point tracks (hill climb, sprint, a gymkhana with separate start and finish).
  A circuit has no `finish` — a lap ends at the start line.
- The same rules as for the start; the finish must come after the start along the outline.

## Sectors (`sectors`)

- In **lap order**, start/finish excluded. Up to 20; usually 2–3, as in the official timing.
- At least **~150 m** between neighbouring lines (and to the start/finish); under 100 m is a validator error.
- Place them **on straights, near their end, before the braking point** — not in a braking zone or in a corner:
  that is where lines of different drivers diverge most and GPS errs most.
- If the track has official sectors, repeat them.

## Corners (`corners`)

- Numbered **as on the official track map** if there is one (numbers may skip, as on the map).
  Without a map — in lap order, starting with the first corner after the start.
- `direction` — `left` / `right`; `apex` — the apex point on the outline (no further than 30 m from it);
  `entry` — the turn-in point, optional.
- `name` — established names only ("Karussell", "Mobil 1"). Corner names and numbers may be taken from official
  track maps — coordinates may not.
- List them in lap order. An S-bend is separate corners if the map shows it so.

## Outline (`outline`)

- The line of **one clean lap** in the direction of travel (no pit lane, run-offs or turnarounds), cleaned of GPS outliers.
- At most **2000 points**; spacing between points at most **10 m** (validator: warning above 15 m, error above 30 m).
  For tracks longer than 20 km the spacing grows by itself — that is fine.
- A circuit's outline is **closed**: the last point is no further than 60 m from the first (ideally the same point).
- `lengthM` — the length along the outline (for point-to-point — from start to finish), within 5 % of what the
  validator computes. If the official length differs, put it in `notes`.
- `direction` — `cw` (clockwise) or `ccw` (counter-clockwise) for circuits, checked against the outline.

## Surface (`surface`)

`asphalt` · `gravel` · `snow` (packed snow) · `ice`. It sets which hints the coach gives: on snow and ice sliding is
the technique, not a mistake. A track that is asphalt in summer and ice in winter is two layouts.

## Sources and licences

Every file must say where the data comes from (`source`) and who marked it (`author` — a GitHub handle).

| `source.kind` | What it is | File licence |
|---|---|---|
| `own-gps` | your own session: the Apex app, a RaceBox, a phone, a logger — anything, as long as **you recorded it** | `MIT` |
| `survey` | your own on-site survey (measured lines, geodesy) | `MIT` |
| `osm` | OpenStreetMap data | **`ODbL-1.0`** |
| `other` | anything else — describe it in detail in `details`; the moderator decides | case by case |

`source.details` should be concrete: "RaceBox Mini S 25 Hz, 2026-08-12, lap 1:32.4, lines checked against satellite imagery".

**OpenStreetMap.** OSM data is distributed under the ODbL, which is share-alike: a derived database must also be
ODbL-licensed and attributed. Therefore:
- a file with anything taken from OSM gets `"license": "ODbL-1.0"` and `"attribution": "© OpenStreetMap contributors"`
  in the relevant source — the validator checks this;
- if only the outline comes from OSM and the lines and corners are yours, give `source` for your data and a separate
  `outlineSource` with `kind: "osm"` (OSM way ids in `details`). The file is still ODbL;
- it is better to replace an OSM outline with your own recorded lap once you have one — then the file can go back to
  MIT (no OSM data left in it);
- ODbL files are marked with the `license` field in `index.json`, and the app shows the OSM attribution.

**Not allowed:**
- copying tracks from the **RaceChrono** library or other commercial apps' databases (Harry's LapTimer, AiM, VBOX,
  etc.) — their terms of use forbid it. The exception is written permission from the rights holder, linked in
  `source.details`. Your own laps **recorded** with RaceChrono are your data (`own-gps`) and are fine;
- transferring coordinates from official track maps and other maps (except OSM). Only corner numbers and names come
  from track maps;
- personal data: sessions, telemetry, VINs, names. A file holds only the markup and a GitHub handle.

`raceChronoID` — the track's number in RaceChrono's library, allowed **only as a cross-reference** (so the app can
match an imported session with the track); no data is taken from the library by it.

## How it is checked

### Automatically (CI on every PR)

`tools/validate.py`:
- conformance to the JSON Schema;
- the file's path: country in the directory, slug = file name, `example` only under `tracks/_example/`;
- coordinates no coarser than 6 decimals;
- geometry: lines no further than 20 m from the outline, heading along the outline (±30°), sectors in lap order and
  at least 100 m apart, finish after start, a circuit's outline closed, no gaps over 30 m, `lengthM` and `direction`
  matching the outline, apexes on the outline;
- licence: OSM ⇒ ODbL + attribution;
- slugs and ids unique across the database, `variantOf` pointing at an existing track in the same country;
- `index.json` rebuilt (`python3 tools/build_index.py`).

`tools/format_track.py --check` — files are in the canonical layout.

### By a moderator

1. CI is green, the validator's warnings have been looked at.
2. The lines and the outline are checked **against satellite imagery** (the timing line is visible on the asphalt)
   and/or against a recorded lap.
3. No duplicate; layouts are linked with `variantOf`.
4. The source is plausible and allowed.
5. **At least one approval** from a moderator (CODEOWNERS) → merge into `main`. After the merge the track reaches every
   app user with the next database update.

### Submissions from the app

The app submits a track as an issue from the "New track" form with the JSON inside. A moderator reviews it, opens a PR
with the file (`Closes #N`) and puts the submitter in `author`. Later a bot (a GitHub Action triggered by a label) will
do this.

## Locally

```sh
pip install jsonschema
python3 tools/format_track.py tracks/ru/my-track.json
python3 tools/build_index.py
python3 tools/validate.py
python3 -m unittest discover -s tools
```
