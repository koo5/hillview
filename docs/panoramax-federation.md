# Panoramax Federation

Hillview joins the [Panoramax](https://panoramax.fr) federation by exposing a
GeoVisio-compatible **read-only STAC API** that the federation's meta-catalog
(api.panoramax.xyz) harvests. Owners' opted-in photos then appear on the
shared Panoramax map alongside every other instance's.

## Components

| Piece | Where | What it does |
|---|---|---|
| Read API + sequencer | `backend/panoramax/` | FastAPI container serving `/api/configuration`, `/api/collections`, `/api/collections/{id}/items`; an in-process sequencer synthesizes sequences |
| DB schema | migration `033_add_panoramax_schema` | `panoramax.sequences` + `panoramax.sequence_photos` + triggers on `photos`/membership |
| DB role | `docker/postgres/initdb.d/create-panoramax-role.sh` (fresh clusters) / `backend/scripts/provision_panoramax_role.sh` (existing) | `panoramax_ro`: SELECT on `photos`/`users`/`photo_ratings`/`flagged_photos`, read-write on the `panoramax` schema only |
| Compose service | `docker-compose.yml`, profile `panoramax`, port 127.0.0.1:8058 | `docker compose --profile panoramax up -d --build panoramax` |
| Frontend self-dedup | `PanoramaxSourceLoader.ts` (`isOwnInstanceItem`) | drops our own photos when they come back through the meta-catalog |

## Naming: `p1.geovisio.hillview.cz`

The `p1` scope is the first contribution scope. `geovisio` identifies the
STAC dialect this read API implements. The service is not yet deployed or
registered. The canonical production host is `p1.geovisio.hillview.cz`.

**The `rstrip("/api")` caveat is not binding for us.** The catalog canonicalises
the registered URL with a *character-class* strip, so the URL must not end in
any of `/`, `a`, `p`, `i`. Every `*.hillview.cz` host is safe because `.cz`
ends in `z` (and a trailing slash is simply stripped, as intended). It would
bite on a `.app`/`.ai` domain, or on a path-suffixed URL: `.../p1` survives,
`.../cc-osm-map` is silently mangled to `.../cc-osm-m`.

**Can one host serve two scopes?** In the catalog, instances are keyed by a
unique `name` while `url` has no unique constraint — but two instances sharing
a URL would harvest identical data, so a second scope needs a distinct URL:
another subdomain, or a path prefix (`geovisio.hillview.cz/arr`, minding the
rstrip). Two further things must change before a second scope goes live:

- **provider ids collide.** `providers.id` is a *global* primary key in the
  catalog and the upsert is `ON CONFLICT (id) DO UPDATE SET name` — it never
  reassigns `instance_id`. We currently publish the raw Hillview user UUID as
  the provider id, so the same user appearing in two instances would stay
  attached to whichever instance was harvested first. Derive per-scope ids
  (e.g. `uuid5(scope_ns, owner_id)`) at that point.
- collection ids are already safe (each scope has its own `sequences` rows).

The federation's own convention, stated by a maintainer while reviewing an
applicant, is "same domain name for website and API; `/api` route to the API,
`/` leads to a website" — two domains are accepted as long as `/api/*` works
on the registered one. Hence `/` on this service **redirects to
`PANORAMAX_VIEWER_URL`** (hillview.cz) rather than serving STAC JSON: the
catalog attaches a `rel=via` link to every harvested item pointing at the
registered instance URL, presented to users as "Link to the original instance".
The web viewer shows it as "Origin instance" and appends the explorer's own
query string to it, so `/?…&pic=<item id>` arrives here: for a photo we serve,
`/` redirects to that photo on the viewer's map
(`/?lat=…&lon=…&zoom=18&bearing=…&photo=hillview-<id>`, the frontend's
`constructPhotoMapPath` shape); any other `pic` gets the plain redirect. On a
dev vhost the registered URL ends in `/geovisio` with no slash, which the
`handle_path /geovisio/*` route does not match: the vhost also needs
`redir /geovisio /geovisio/?{query} 308`.


## Scope and licensing

Intake is what the contributor grants Hillview (`Photo.legal_rights`); outflow
is the licence Hillview publishes on every read (`license`). These are separate:

| Intake | Outflow |
| --- | --- |
| `full1` | `arr`, or `panoramax` when the owner turns sharing on |
| `ccbysa4+osm` | `ccbysa4+osm` |
| `panoramax_in` | `panoramax`, regardless of sharing or federation eligibility |

The `panoramax` wording is still a placeholder. The federation's declared SPDX
`CC-BY-SA-4.0`, URL and configuration description remain provisional until
that wording is settled. Installed Tauri clients show unfamiliar outflow ids
as unknown until their next release; the prototype controls are in frontend2.

### How our grant compares

`ccbysa4+osm` covers derived-data use for OpenStreetMap contributions only.
It does not authorize the LO 2.0 / CC-BY derived-data uses the federation
catalog makes, including its metadata exports. We therefore do **not**
federate photos under that intake. Hillview needs the wider `full1` or
`panoramax_in` intake to publish under a Panoramax-compatible outflow.
The final photo and metadata terms must be settled before registration.

A photo is **eligible for selection** iff (one definition in
`backend/panoramax/app/eligibility.py`, used by sequencer and API):

- Its intake is `full1` or `panoramax_in` (scope `p1`).
- `panoramax_owner_share` is on (default **off**).
- `panoramax_moderator_approved` is on (default **on**).
- The owner's `panoramax_contributor` flag is on (default **on**).
- The detector ran and no object has `blurred = true`. NULL detections,
  skipped anonymization and manual anonymization do not qualify. The
  completed detections migration makes each object's `blurred` explicit;
  the column is PostgreSQL `json`, not `jsonb`.
- It has a capture time (`captured_at`). Without one, `effective_at` is the
  upload time: it would be published as the Panoramax `datetime` and would
  order an upload batch as if it were a walk (a 2026-10-30 mirror of prod had
  2,654 of 10,920 published photos like that, one "sequence" jumping 68 km in
  97 s).
- All existing gates pass: not deleted, public, processing completed, geometry,
  capture/upload effective time and renditions present, owner active and not a
  test user, no thumbs-down rating and no unresolved flag.

Sharing changes the outflow of a `full1` photo even when another gate excludes
it from federation. Approval and contributor flags affect eligibility only.
Only selected representatives are served. Photo share, approval and detection changes bump sequence timestamps; the
sequencer prunes membership on its next pass while reads filter immediately.

`PhotoLicenseHistory` records intake changes. The FK-free append-only
`PhotoOutflowLicenseHistory` records publication changes with `grant_change`
or `panoramax_share` as their cause. Original grants/outflows are derived from
the upload choices, with the first change snapshotting the original value.
A version-bump re-upload still recreates the photo without either history;
this existing intake-history gap also applies to flags and outflow history.

The capture default is saved across restarts and copied into each photo's
Room row. Card edits update that row and an account-keyed outbox wish, so
unuploaded photos authorize with the new choice and already uploaded photos
receive an idempotent PATCH. Pre-choice photos retain a null intake and adopt
the global licence at upload, with no migration or dialog.

## Representative views: 5 m cells and bearing sectors

Eligibility is permission to compete, not a promise that every eligible photo
appears in the catalog. On each collector pass, `app/selection.py` chooses one
photo per **(grid SRID, 5 m easting cell, 5 m northing cell, bearing sector)**
across all contributors, before constructing owner sessions.

- Grid coordinates come from PostGIS `ST_Transform` into local WGS84 UTM
  projections, with UPS for the polar caps. Cells are 5 × 5 projected metres;
  projection scale varies slightly on the ground. Regular six-degree longitude
  zones are used, rather than MGRS's exceptional Norway/Svalbard boundaries.
  Each zone and hemisphere has its own origin; cells are clipped at projection
  boundaries. This is a grid, not a five-metre radius/distance exclusion rule.
- The default is eight 45° sectors centered on N, NE, E, etc. North wraps
  through zero: [337.5°, 22.5°). `PANORAMAX_BEARING_BUCKETS` changes the number
  of sectors (1–360). Missing/non-finite bearings share one extra unknown
  bucket, separate from a real north-facing photo.
- Prefer a capture with the sun above the geometric horizon, then one with
  unknown capture time, then a night capture. Within that class, prefer the
  newest capture; unknown capture times use the existing effective/upload-time
  fallback for recency only. Equal scores use the smallest photo id, so input
  order and arrival order never affect a winner. A newer night photo does not
  displace an older daytime photo; night photos still fill otherwise empty
  buckets.
- Daylight uses the capture's UTC date/time and location in NOAA's approximate
  solar-position equations. It accounts for longitude, seasons and polar
  day/night without time-zone lookup. It does not measure exposure, cloud,
  terrain shadow, or actual image quality. Upload time never masquerades as a
  known daytime capture.

The projection reference is [NGA's UTM/UPS description](https://earth-info.nga.mil/?action=coordsys&dir=coordsys);
daylight follows [NOAA's general solar-position equations](https://gml.noaa.gov/grad/solcalc/solareqns.PDF).

No new winners table or migration is needed: `panoramax.sequence_photos`
already persists the selected set. Recompute the winners deterministically and
diff membership as before. Repeated passes do not change ranks or timestamps.
A better/newer winner replaces the previous member; if a winner withdraws or
fails moderation, the next-best eligible candidate takes its place. Normal
membership triggers, departed-photo identity, and catalog tombstones carry
these changes downstream. Full collector passes serialize per scope with a
transaction-level advisory lock.

Selection is refreshed on the collector's cadence (default 300 seconds).
The API reads persisted selection, rather than ranking the entire library on
each request, and still applies eligibility immediately. An ineligible winner
is hidden immediately; its replacement becomes visible after the next pass.
Edits to position/bearing and the arrival of a better candidate likewise take
effect in selection on that next pass.

Verified 2026-10-29: 127 collector unit tests and 15 real PostGIS/API integration
tests pass, including global winners, cell boundaries, date line/poles,
withdrawal fallback, recency/bearing edits, and contributor removal. Both real
catalog e2e modes pass. In the 50,000-photo corpus, 40,546 photos were eligible
and 39,223 selected (1,323 suppressed); the full catalog had 39,235 items
including the 12 worker-uploaded seed photos, with zero harvest errors. The
unchanged full collector pass took 3.0 seconds and changed no timestamps.

## Sequences

Synthesized from selected winners, persisted, per-owner **time-gap sessions** (default 15 min, env
`PANORAMAX_SESSION_GAP_HOURS` = 0.25; 3 h until 2026-10-30) — not one ever-growing collection per user,
because the meta-catalog's incremental sync re-fetches **all** items of any
changed collection (collection-level granularity), making giant collections an
unbounded recurring cost. No distance splitting: the catalog only draws lines
between consecutive items <75 m apart, so sparse sequences render as dots.

Lifecycle invariants:

- Sequence ids are real UUIDs (the catalog casts `content->>'id'` into UUID
  primary keys — same for item ids, which are photo UUIDs).
- A sequence that loses all members flips to `status='deleted'` (trigger) and
  is **never hard-deleted**: the harvester learns about deletions *only* by
  listing `status IN ('deleted','ready') AND updated > <ts>` — tombstones must
  keep being served with a bumped `updated_at`.
- `owner_id` is `ON DELETE SET NULL` so tombstones survive account deletion
  (membership rows cascade away; the membership trigger tombstones the
  sequence in the same statement).
- Any relevant `photos` UPDATE (visibility, license, geometry, heading,
  capture time, sizes, title/description, processing state, soft-delete) bumps
  the owning sequence's `updated_at` via trigger — the only channel through
  which member changes propagate to the catalog. Serve-time filtering makes
  out-of-scope photos vanish from `/items` immediately, before the sequencer's
  next pass prunes membership.
- The sequencer is a full deterministic recompute diffed against stored state
  (photos have no updated-at column to drive anything cheaper); an unchanged
  owner produces zero writes, so `updated_at` only moves on real change.
  Session→sequence identity: keep the UUID of the sequence you overlap most.
- **Tombstones revive under their own id.** Live membership alone can't do
  that — an emptied sequence has no membership rows left to overlap with — so
  the membership trigger keeps `panoramax.departed_photos` (the last
  sequence of every photo that left and hasn't returned; `photo_id` is the
  PK, rows skipped for hard-deleted photos) and the sequencer counts those as
  overlap too, live membership winning. A user deactivated and reactivated, a licence flipped
  and flipped back, a single-photo sequence flagged and cleared: all come back
  as the *same* collection uuid, which the catalog re-harvests in place
  instead of drop-and-reimport under a new id. Found by the heavy e2e mode
  (the light run only ever restored a photo into a still-live sequence).

## Meta-catalog harvester contract (verified against its source)

Repo: `gitlab.com/panoramax/server/meta-catalog` (local checkout:
`/home/koom/repos/panoramax/server/meta-catalog/0/meta-catalog`).

- **Mandatory endpoints**: `/api/configuration` (`add-instance` aborts without
  it; content stored verbatim, no fields inspected), `/api/collections`
  (filter + `rel=next` paging), `/api/collections/{id}/items` (`limit` +
  `rel=next`). Users/map/RSS/search are NOT consumed — the catalog regenerates
  them.
- **Incremental sync** (~2 min cadence, ≥5 min per-instance floor) sends
  exactly `?filter=status IN ('deleted','ready') AND updated > '<iso>Z'`
  (CQL2-text; `backend/panoramax/app/cql.py` parses it with pygeofilter — the
  same grammar library the reference GeoVisio server uses — then accepts only
  the `status`/`updated` conjunction we can execute, 400 on anything else), then
  re-fetches ALL items of each changed collection; item deletions are detected
  by diff.
- **Tombstone flag mismatch to be aware of**: the CQL2 queryable is `status`,
  but the JSON field the harvester checks is `geovisio:status == "deleted"`
  (harvest.py `sync_collection`).
- Items are ingested with `(content->>'id')::uuid`, `(content->>'collection')::uuid`,
  `ST_GeomFromGeoJSON(content->'geometry')` **NOT NULL**, and
  `properties.datetime` parsed by Postgres — all four must be present/valid.
- Collections need `id`, `created`, a `rel=self` link (items are fetched at
  `<self>/items`), and `providers[*]` with `{id: <UUID — global PK>, name:
  <NOT NULL>}`; we use the owner's user UUID + username. **Never share
  provider or collection UUIDs across instances.**
- Ordering property: `properties["geovisio:rank_in_collection"]` (int,
  1-based).
- Instances are keyed by unique `name`; `url` carries no unique constraint, but
  two instances sharing a URL would harvest identical data, so a second scope
  needs its own URL (see the naming section).
- Asset hrefs that are absolute are kept verbatim → we point straight at the
  existing pics/CDN **WebP** derivatives (`hd`→`full`, `sd`→2048-ish,
  `thumb`→640-ish, with fallback chains for fast-mode/narrow photos — see
  `stac.pick_assets`). See the WebP caveat below.

### ⚠️ WebP: what actually breaks

The viewer's compatibility spec lists `image/webp` alongside `image/jpeg`, and
the meta-catalog stores whatever asset types you declare, so WebP harvests
fine. The upstream history is worth knowing, because it is often misread as an
anti-WebP stance: WebP was the **primary storage format** in API 1.4.0
(*"Internal storage format for pictures is now WebP, offering same quality with
reduced disk usage"*, with four `*_webp` STAC assets), was dropped from STAC in
2.0.0, and on-the-fly JPEG→WebP conversion was removed in 2.7.0 as *"too
slow"* — the changelog adding *"WebP might do an unexpected come-back in the
future 😉"*. The performance objection was therefore about **transcoding per
request**, a cost we do not have: every WebP we serve is a pre-generated static
file. Their reference ladder is `hd` = untouched original, `sd` = fixed 2048px
at quality 75, `thumb` = 500px at quality 75 (a 500×300 centre-crop for 360°),
tiles at 95; the thumbnail is a plain PIL resize, **not** an EXIF-embedded one
(there is no vips or exiftool anywhere in their API).

Not every photo is WebP, though: older photos and the Tigris pool carry JPEG
files (4,146 of the 10,920 photos a 2026-10-30 mirror of prod published), and
`stac.pick_assets` declares each asset's type from its file suffix, so those
assets are `image/jpeg` and the JPEG-only client paths below work for them.

We are nonetheless the only WebP producer in the federation. The federation
itself imposes no format requirement and the meta-catalog is format-agnostic
(it stores hrefs verbatim and 308-redirects), but **three places in the
official clients hardcode `image/jpeg`**:

- `web-viewer` `API.js:471-475` — the thumbnail lookup requires JPEG for both
  the `thumbnail` role and its `visual` fallback, so map hover popups get a
  `null` URL and are silently removed. (Inconsistent with `picture.js:343`,
  which *does* accept `image/webp` for the same `visual` role — the main photo
  texture therefore displays fine.)
- `cli` `download.py:96` — filters assets on `type == "image/jpeg"` with no
  `else`, so `panoramax-cli download` yields zero pictures from us, silently.
- viewer fast-mode preload — cosmetic only.

Browsing via the federation is unaffected: the meta-catalog advertises its own
`item-preview`/`collection-preview` endpoints (typed `image/jpeg`, redirecting
to whatever we stored), and the viewer prefers those over per-item assets. The
breakage only hits a viewer pointed **directly** at our instance — which our
landing page currently guarantees, since it declares no `item-preview` link.

Cheapest fixes, in order: declare `item-preview`/`collection-preview` links on
our landing page; or generate real JPEG for the `thumb` tier only (500px q75 ≈
15 KiB/photo); or full JPEG derivatives for the federated subset (largest change —
the worker is WebP-only end to end, including `.webp` DZI tiles).

Size-wise WebP is currently costing us rather than saving: at `WEBP_QUALITY_SIZES = 97`
our 2048px derivative is 304 KiB against 182 KiB for Panoramax's 2048px JPEG at
quality 75, and our 640px thumb is 47 KiB against their 15 KiB 500px thumb. The
format's ~25-34% advantage also lands at its low end for complex natural scenes.

### ⚠️ Asset CORS

`api.panoramax.xyz` fetches assets in the browser, so the asset host must send
permissive CORS — this has broken at least three instances right after they
joined. The web viewer draws a photo as a WebGL texture, so without the header
the picture stays black (Firefox names the CORS block in its console; Chromium
stays silent). Current state: both asset hosts send
`Access-Control-Allow-Origin: *` ✅ — `pics.hillview.cz` from its Caddy vhost,
the Tigris bucket (`pics4.t3.storage.dev`) from a bucket CORS rule (origins
`*`, methods GET and HEAD), added 2026-10-30 after a dev mirror of prod with
every photo shared published 274 photos from that pool and drew them black.
The viewer fetches assets with plain anonymous GETs (no preflight, no
credentials), so nothing beyond that rule is needed.

The **instance API itself** is also CORS-open (added 2026-08-30), but this is
**optional, not a federation requirement** — the earlier claim that the viewer
relies on it was wrong. The harvester is server-side (no CORS); the federated
viewer reads the meta-catalog, not instances; the per-item `rel=via` link to
us is a navigation, not a fetch; and our own hillview.cz frontend reads
`api.panoramax.xyz`, never this endpoint. So nothing in the normal flow needs
it; `main.py`'s `CORSMiddleware` (`allow_origins=['*']`, GET/HEAD/OPTIONS, no
credentials) is a zero-cost hedge for a third-party STAC browser pointed
straight at us, harmless because everything served is public and anonymous.
The prod Caddy vhost for `p1.geovisio.hillview.cz` needs no CORS config of its
own either way. The genuinely required CORS is the asset-host header above;
the dev box's `/pics` route in `~/caddy/Caddyfile` sends
`Access-Control-Allow-Origin: *` now, matching prod.

## Deployment

1. Set in `.env`: `PANORAMAX_DB_PASSWORD=<secret>`, and for prod
   `PANORAMAX_BASE_URL=https://p1.geovisio.hillview.cz`. Leaving the password
   empty (the compose default — it can't be `:?`-required, since compose
   interpolates before applying profiles and would then break every command
   for everyone) makes the container exit at boot with a message naming the
   variable; same for an unknown `PANORAMAX_SCOPE`.
2. Role: fresh clusters get `panoramax_ro` from initdb automatically; existing
   deployments run `./backend/scripts/provision_panoramax_role.sh` (after the
   api container has applied migration 033 — grants reference the schema).
3. `docker compose --profile panoramax up -d --build panoramax` (dev:
   `./compose.sh --profile panoramax up -d --build panoramax`).
   On a dev box behind Caddy the service is reachable at
   `https://<vhost>/geovisio/api/…`: the vhost snippet has
   `handle_path /geovisio/* { reverse_proxy localhost:8058 }` and the
   machine's `hosts.toml` entry sets `PANORAMAX_BASE_URL=https://<vhost>/geovisio`
   (rendered into `.env` by `scripts/set_host.py`) so self/next links
   round-trip through Caddy. (Editing the bind-mounted
   Caddyfile replaces its inode; `caddy reload` then still reads the old
   file — recreate the caddy container.)
4. Caddy vhost (lives outside the repo, `~/caddy/Caddyfile` on the VM). See the
   naming section for the `rstrip("/api")` caveat — any `*.hillview.cz` host is
   safe:

   ```caddy
   https://p1.geovisio.hillview.cz {
       reverse_proxy localhost:8058
   }
   ```

Env knobs: `PANORAMAX_SCOPE` (default `p1`), `PANORAMAX_BEARING_BUCKETS` (8),
`PANORAMAX_SESSION_GAP_HOURS` (0.25), `PANORAMAX_SEQUENCER_INTERVAL_S` (300), `PANORAMAX_SEQUENCER_ENABLED`
(true — set false to run the API without the in-process sequencer),
`PANORAMAX_INSTANCE_NAME` (Hillview), `PANORAMAX_VIEWER_URL`
(the stack's `FRONTEND_URL` if set, else `https://hillview.cz` — where `/`
redirects humans arriving from the catalog's per-item `rel=via` link), `PANORAMAX_LOGO_URL`
(`https://hillview.cz/favicon.png` — `/api/configuration`'s `logo`, which the
meta-catalog stores and serves at `/api/instances/<name>/logo`; the web
viewer's picture panel always asks explore.panoramax.fr for it, so it shows
only once we are registered there).

## Registration

A free-form issue on the meta-catalog GitLab project (no template exists):
instance URL, unique name, logo, whether the instance accepts external
contributions (ours: **no** — uploads go through hillview.cz), geographic
coverage, and a 24/7-availability *goal* (explicitly no SLA expected).
Approval is a manual decision by two maintainers, who then run
`stac-harvester add-instance`. Turnaround observed in past requests: same-day
to ~3 weeks.

**We would be the first non-official server implementation in the federation.**
Every currently federated instance runs the official Panoramax API. The
project's stated position is standards-based (*"any compliant server can be a
part of Panoramax"*), and the viewer docs explicitly support third-party STAC
APIs — but there is no precedent, so expect scrutiny. The one existing
non-official implementation (PanoCommons, Wikimedia Commons imagery on
PgSTAC/stac-fastapi, built by a Panoramax maintainer) is *not* federated, and
would fail the harvester contract today: no `/api/configuration`, non-UUID
collection ids, no `created`/`updated`/`geovisio:status`.

What reviewers have actually blocked or chased on past requests:

- **Blurring** — faces and licence plates must be anonymised; one instance was
  held up until it reprocessed its sequences. We comfortably exceed this: the
  worker blurs *whole* persons and vehicles (`person`, `bicycle`, `car`,
  `motorcycle`, `bus`, `truck` — `worker/detections.py`), and all 23,973
  currently-federated photos carry a detection record (6,400 with detected
  objects), i.e. none were uploaded with anonymisation skipped.
- **`/api/configuration` completeness** — name, description, logo, contact,
  colour, geographic coverage. Chased in nearly every thread.
- **Asset CORS** — see above.
- **URL scheme** — see the naming section.
- **Anonymous upload / open registration** — maintainers probe this (one
  literally created a test collection on an applicant's instance). Ours is
  read-only, so it is moot, but say so.
- **Verify the data actually lands.** Harvesting has silently failed to start
  after approval at least twice due to catalog-side misconfiguration. After
  being added, check `api.panoramax.xyz` for our collections rather than
  assuming.

Neighbours for reference: two Czech instances are already federated —
`pano.mahdi.cz` and `pano.kasik-gis.eu`, both single-user, CC-BY-SA-4.0, both
running the official Panoramax API.

## Frontend self-duplicate filtering

Once federated, api.panoramax.xyz serves our own photos back through the
`panoramax` source. `PanoramaxSourceLoader.isOwnInstanceItem()` drops items
whose `rel=via` link (added per-item by the catalog's `/api/search`, href =
origin instance URL) matches `ownPanoramaxInstanceUrls`, falling back to
asset-URL-prefix matching against `ownPhotoAssetUrlPrefixes` (pics hosts +
CDN) when no via link exists. Drops are counted like the hidden-content drops
(`droppedSelf`). Cross-source id-dedup is deliberately not the primary
mechanism: the hillview source caps photos per bbox, so the native copy may be
absent while the federated copy loads.

## Verification plan

Unit: `./backend/panoramax/run_unit_tests.sh` (CQL subset, session
splitting/identity/diffing, STAC serialization incl. asset fallbacks and
tombstones) and `frontend`: `bun run test:unit -- src/lib/sources/PanoramaxSourceLoader.test.ts`.

A **browsable mirror of prod**: restore a prod dump into the dev DB and let the
api start (it migrates the dump), then
`./backend/panoramax/scripts/share_all_photos_dev.py` turns on the one
eligibility flag that defaults off and runs a sequencer pass (it refuses on a
stack without `DEBUG_ENDPOINTS`). On the meta-catalog's box, `stac-harvester
harvest <instance>` and then `stac-harvester refresh-database-views`: the
harvester only marks map grid cells expired, so the map stays empty until the
refresh. The meta-catalog API's own landing page is the explorer
(explore.panoramax.fr runs the same page). Its web viewer calls the
origin-absolute `/api`, so it needs the root of its own hostname, not a path
prefix.

End-to-end against the **real harvester**, fully scripted:

```bash
./backend/panoramax/scripts/e2e_federation.sh            # full run
./backend/panoramax/scripts/e2e_federation.sh --heavy    # + production-shaped 50k-photo corpus
./backend/panoramax/scripts/e2e_federation.sh --no-seed  # reuse existing photos
./backend/panoramax/scripts/e2e_federation.sh --keep-up  # leave the catalog running
./backend/panoramax/scripts/e2e_federation.sh --keep-load     # --heavy: leave the corpus in the DB
./backend/panoramax/scripts/e2e_federation.sh --cleanup-load  # remove a kept corpus
./backend/panoramax/scripts/e2e_federation.sh --down     # tear the catalog down
```

It brings up the hillview stack, seeds opted-in photos through the real upload path
(`scripts/seed_photos.py`, laid out as N time-gap sessions so the sequencer's
splitting is asserted), starts the meta-catalog stack from the local checkout
(`META_CATALOG=`, default `/home/koom/repos/panoramax/server/meta-catalog/0/meta-catalog`),
installs the harvester CLI, registers the instance, and then asserts: full
harvest with **zero harvest errors** (the check that matters — the harvester
reports "imported" even when every collection failed), collection/item counts
matching the DB, providers and computed geometries present, edit propagation
via incremental harvest, deletion propagation into `deleted_items`, sequence
tombstoning plus tombstone visibility through the CQL status filter, restore,
and pystac validation.

**Heavy mode** (`--heavy`; `LOAD_PHOTOS=50000 LOAD_USERS=40 LOAD_YEARS=3
LOAD_SEED=1` to tune) adds a production-shaped corpus written straight into
the DB by `scripts/generate_load.py` — the worker path is skipped because 50k
photos through YOLO and derivative generation is a day's work, and everything
the federation service reads is a database row anyway. The corpus has
heavy-tailed users with home areas, sessions ranging from singles to walks of
hundreds of photos over the span, second-to-minute gaps and a random-walk
track inside a session, and inter-session gaps always > 2× the split threshold.
Four percent of consecutive captures deliberately repeat a position/direction
to exercise thinning. Exclusions cover grants, sharing, moderation, blurring,
visibility and processing, plus inactive/test/non-contributor users. The
generator evaluates the publication policy using actual PostGIS cell coordinates;
it independently derives expected sessions and ranks from those selected ids.
On top of the light phases it asserts: sequencer output equals these fixture
expectations (selected memberships, sessions, singles, nothing for the excluded users),
ineligible and grid-suppressed samples are absent from the catalog,
and a second pass changes nothing; every `/api/collections` page and every
`/items` page of the largest sequence walks cleanly with no duplicates and
strictly increasing ranks; 200 random edits across users make the `updated`
filter return exactly the touched sequences and land in the catalog after one
incremental harvest; deactivating the heaviest user tombstones all their
sequences, the catalog drops them, and reactivating revives the **same**
uuids. It prints timings for the sequencer passes, harvests and page
latencies, and removes the corpus at the end unless `--keep-load`.

Two things it does that are worth knowing: it points the seeder straight at
`localhost:8056` (the API advertises the deployment's public `WORKER_URL`,
which may not resolve locally), and it clears `users.is_test` on the seeded
user, because eligibility deliberately excludes test accounts.

Running it in a fresh worktree needs three gitignored files copied from a
working checkout: `.env`, `backend/api/app/.env` (holds `JWT_PRIVATE_KEY` —
without it the API mints ephemeral keys and the worker 401s every upload),
`backend/worker/.env`, plus `backend/worker/models/` (~48 MB of YOLO weights,
needed to build the worker image).

## State of play (2026-08-28)

Built and verified end-to-end against the real harvester in both e2e modes;
committed on branch `enrich` (`3ce4880b`) except the later changes listed
below; **not yet deployed or registered**.

Verified working (light mode, real dev data at the time): full harvest of 120
collections / 23,973 items with zero harvest errors; incremental harvest picks
up exactly the trigger-bumped collection; soft-delete propagates to
`deleted_items`; emptied sequences tombstone, stay listable through the CQL
status filter and **revive under the same uuid**; restore round-trips; pystac
validates both shapes. The `panoramax_ro` role was probed directly:
`UPDATE`/`DELETE` on `photos` and `users` are denied, writes succeed only
inside the `panoramax` schema.

Verified at scale (heavy mode, 2026-08-28: 50,000 generated photos, 40 users,
3 years, 44,704 eligible, 1,783 expected sequences incl. 624 singles, largest
543 photos): sequencer matches the independent expectation exactly and a
second pass writes nothing; full harvest of 1,786 collections / 44,716 items
with zero errors in **28 s**; sequencer full pass **18 s**, no-op pass 1.7 s;
collections page (100) avg 24 ms, items page avg 10 ms; 200 random edits →
`updated` filter returns exactly the 150 touched sequences → one incremental
harvest (5.6 s) lands all 200; deactivating the heaviest user (148 sequences
/ 4,226 items) tombstones everything in 2.3 s, the catalog drops it in 0.9 s,
reactivation revives the same 148 uuids and the catalog has the items back
after an 8.6 s incremental harvest. 75 backend unit tests pass.

Changes since the commit: CQL parsing moved to pygeofilter; migration
renumbered **030 → 033** (the dev2026-07-07 merge added 030–032 on 029,
leaving two alembic heads that would have failed the api prestart);
`panoramax.departed_photos` + identity-map merge so tombstones revive (heavy
mode found that they never did); `generate_load.py` + `--heavy`; the registration
drafts document.

Open decisions, in rough priority order:

1. **Metadata licence** — see the licensing section and
   [panoramax-registration-drafts.md](panoramax-registration-drafts.md).
2. **WebP** — accept the two client breakages, add `item-preview` links, or
   generate JPEG thumbs (see the WebP section).
3. **Prod deploy + registration** — Caddy vhost, then the GitLab issue.
4. **Tigris CORS** — before any federated photo is written to that pool.
5. Optionally lower `WEBP_QUALITY_SIZES` from 97; it is what makes our
   derivatives heavier than Panoramax's JPEGs.
