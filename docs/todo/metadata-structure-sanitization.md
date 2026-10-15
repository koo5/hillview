# Metadata pipeline and structure sanitization

Parked plan, opened 2026-09-27. Nothing here is built. The point of collecting it is
that these are one rehaul, not five drive-bys — each is individually small and
individually not worth a migration, and doing them separately means five migrations
and five rounds of updating the same hundred call sites.

## Start here: `exif_data` should be `metadata`

What the column actually holds, measured on a real prod photo (`ce9ffa98`):

| subkey | contents |
|---|---|
| `data` | **73 tags** — the actual exiftool dump, plus `UserComment` |
| `gps` | 5 — latitude, longitude, altitude, **bearing**, **pitch** |
| `debug` | 7 parser flags — `found_gps_tags`, `has_bearing`, `parsing_errors`, … |
| `exif` | **empty** — a vestige of the commented-out `result['exif'] = exif_dict` at `photo_processor.py:564` |

The EXIF dump is one subkey of four, and the column is named after it. `metadata`
with `metadata.exif` as the dump is what the thing actually is.

**Rename cost, counted:** ~107 references — `backend/api` 47, `backend/worker` 49,
`enrich` 7, `shared-kt` 2, `backend/common` 1, `scripts` 1, and **zero in either
frontend**. Neither web nor Android reads the raw column; they read the curated
`exif` and the typed provenance projections. So it is a server-side rename plus an
alembic column rename.

One caveat that makes it a contract change rather than an internal one:
`exif_data` is a KEY in the owner endpoint's response (`photo_routes.py:986`). Any
owner-endpoint consumer sees the rename. The public endpoint does not ship it at
all, so public consumers are unaffected.

## The structural inversion: our provenance lives inside the camera's dump

Provenance — `attitude`, `fix`, `lens`, `inertial`, `location_source`, … — is a JSON
**string** at `exif_data['data']['UserComment']`. Our data, text-encoded, nested
inside the camera's tag set, inside a JSON column.

It is faithful to the FILE format and backwards as a data model. The UserComment is
the EXIF-legal carrier for an app's own stamp, and the fast-write path has the worker
synthesize what a written EXIF would have said — so the nesting is a transport
detail that became the storage shape. What it costs: double encoding, a
`_user_comment()` parse on every read, and the "both forms coexist in one column"
caveat at `photo_routes.py:1572`.

The shape to aim at: `metadata.provenance` as a first-class sibling,
`metadata.exif` as the dump, and the UserComment demoted to what it is — something
written into a JPEG on the way out.

## `gps` is not GPS

It carries bearing and pitch, which no receiver produces. `docs/one-state.md` says
it plainly and `recon-capture-metadata.md` decided to live with the name because
renaming it alone was not worth a migration. A rehaul is exactly when it becomes
cheap. `stamp` or `pose` says what it is.

And `gps.pitch` should not survive the move at all — audited 2026-09-27: nothing in
`frontend/src`, `frontend2`, `shared-kt` or `enrich` reads it, it is a pure waypoint
inside `process_uploaded_photo` (written `:1750`, read back `:1891`), and 12 995 prod
rows show zero cases where it carries anything the `photos.pitch` column lacks. The
full audit is in `recon-capture-metadata.md`, "Removing `gps.pitch`".

`gps.bearing` is NOT in the same position and must survive: fallback check at
`:1838`, feeds `compass_angle` at `:1890`, and `GPSImgDirection` is a real EXIF
source for it.

## The four-list contract is the recurring tax

A new provenance key has to appear in the app serializer, `BrowserMetadata`,
`PROVENANCE_KEYS`, and the typed projection — or it is dropped silently at one end or
the other. Pydantic dropping undeclared keys is what swallowed `location_age_ms` and
`exposure` for weeks with nothing anywhere saying so, and
`test_every_provenance_key_can_get_through` exists because of it.

The interesting question for the rehaul is whether four lists can become one
declared schema with generated projections. `capture_timing` is pre-declared as an
untyped dict specifically to dodge the tax once (see
`captured-at-is-the-exposure.md`); that is a workaround, not a fix.

## Naming drift to fix in the same pass

- `compass_angle` in the worker's processing result (`:1890`) versus `bearing`
  everywhere else.
- `motion` → `inertial` already happened for exactly this reason; same class of fix.

## Related, deliberately separate

- **What a public photo publishes** (`what-a-public-photo-publishes.md`) — the
  owner/public projection asymmetry and the consent question. A rehaul of the shape
  is the moment to get the visibility rules right, but they are a product decision,
  not a refactor.
- **`captured-at-is-the-exposure.md`** — shipping `capture_timing` inside this
  structure. It should not wait for the rehaul.

## Open

- Does the rehaul migrate old rows' inner shape, or only rename the column and leave
  historical rows as they are? Leaving them means every reader handles both forms
  forever, which is the thing this plan exists to stop.
- Is `debug` still worth storing per photo? Seven parser flags on every row.




========
notes:
concerning avoiding surprises, we want to store almost-full dumps of original exif data, if any are present. some values could be replaced with {nuked:true}, those that we knowingly copy elsewhere, or want to kill of because of size.
