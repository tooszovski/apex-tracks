## What changes

<!-- New track / fix / tooling. Link the submission: Closes #… -->

## Author checklist

- [ ] One file — one layout: `tracks/<country>/<slug>.json`, slug equals the file name
- [ ] `name` (official, Latin script) and `localName` are filled in
- [ ] Start/finish is on the timing line, `heading` is the direction of travel, the width covers the track but not a neighbouring straight
- [ ] Sectors are in lap order, at least ~150 m apart, not in a braking zone
- [ ] Corners are numbered as on the official map (if there is one)
- [ ] The outline is a clean lap (≤ 2000 points, spacing ≤ 10 m), closed for a circuit
- [ ] `source` honestly states where the data comes from; nothing is copied from RaceChrono or other apps
- [ ] Anything from OpenStreetMap ⇒ `license: "ODbL-1.0"` and `attribution`
- [ ] `python3 tools/format_track.py <file>`, `python3 tools/build_index.py`, `python3 tools/validate.py` — no errors

## Moderator checklist

- [ ] CI is green
- [ ] Lines and outline checked against satellite imagery and/or a recorded lap
- [ ] No duplicate of this layout; `variantOf` points at the main one
- [ ] Validator warnings looked at
