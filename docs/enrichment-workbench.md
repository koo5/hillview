# Enrichment Workbench — design

Status: **M0 built & running, M1 in progress** · updated 2026-07-07
Supersedes the *architecture* section (§4) of [`vision-subsystem.md`](vision-subsystem.md) as the
concrete build plan; the technique catalogue and empirical findings there (and in
[`reconstruction-field-notes.md`](reconstruction-field-notes.md)) remain the reference.
The stack lives in [`../enrich/`](../enrich/); its [README](../enrich/README.md) has run/smoke
commands. (Sections below marked *(superseded)* describe the original sketch; the **Decisions**
and **Build status** blocks are authoritative.)

## Decisions (authoritative)

- **UI stack: SvelteKit** (Svelte 5 runes, adapter-node, Bun) — matches `frontend/`, so bench
  UIs/components can graduate into Hillview admin/user features.
- **Live data: local dev backend first** — mirror-sync reads the local docker-compose Postgres
  over the shared `hillview_network` (`HILLVIEW_DB_URL`); read-only prod role over a tunnel is
  deferred (only the sync path cares). The dev DB is seeded from a prod CSV dump via
  `enrich/db/seed_dev_from_dump.sh`.
- **First bench: Annotations** — head of the pipeline (annotation text → structured facts).
  Then geocode curation, calibration, matching/view-pie, recon.
- **No hand-rolled job queue yet** — M0/M1 runs execute in-process (API async task + CLI).
  M3 adopts **Remoulade** (already used in `~/repos/koo5/accounts-assessor`, whose
  *untrusted-workers* mechanism fits rented GPU boxes). Luigi (pics-side) is a different,
  batch-DAG concern.
- **Facts layer = Oxigraph (RDF quads) + Postgres (mirrors/runs/spatial).** NOT "EnrichDB"
  (name collision). **No RDF-star, no reification, no blank nodes** (user ruling): each fact is
  ONE triple alone in a **content-addressed named graph** `fact:{sha256(canonical-ntriples)[:16]}`.
  Provenance and curation are plain triples *about the fact-graph URI* (meta graph:
  `prov:wasGeneratedBy`/`hv:about`; curation graph: `hv:status`). Same fact re-emitted ⇒ same
  URI ⇒ **curation survives re-runs by construction**.
- **IRI namespace = `rdf.hillview.cz`** — deliberately distinct from the web app's
  `hillview.cz`, so URIs read as identifiers, not addresses (the subdomain can later serve a
  dereferencing RDF viewer). Web pages are referenced *explicitly* via `hv:webPage` /
  `hv:wikipediaPage`.
- **Sync is monotonic (mirror only gains information)** — two tiers: **append** (watermark on
  `COALESCE(record_created_ts, uploaded_at)` / `created_at`; inserts new rows only) +
  **reconcile** (source-side `md5(to_jsonb(row))` row-hash → upsert changed rows; rows gone
  from source get `missing_since` stamped, **never deleted**; cleared on reappearance). The
  source has no updated-at column (`analysis`/`geocode`/`deleted`/`is_current` mutate
  silently), so only reconcile catches mutations — that's by design.
- **Analyzer** (`scripts/analyzer`) is already a *production* component (manual script); its
  workstream is just containerization in the **main** stack (profile service), decoupled from
  the workbench DB/queue.

## Build status (2026-07-07)

Implemented & verified in `enrich/`:

- **M0-1 ✅** compose (`hillview-enrich`): `workbench-db` (postgis :15432), `oxigraph` 0.5.0
  (:7878), `api` (FastAPI :8070), `web` (SvelteKit :8071, host-run in dev). Schema
  `enrich/db/init/001_schema.sql`: `photo_mirror`, `annotation_mirror` (both +
  `row_hash`/`missing_since`), `runs`, `sync_state`. Vocab `enrich/vocab/hv.ttl`.
- **M0-2 ✅** API: `config`/`db` (two async engines — workbench rw + hillview **read-only**
  via `default_transaction_read_only`)/`tables`/`graph` (Oxigraph HTTP-SPARQL client)/`runs`
  + `health`. `/api/health` = all three deps green. *(Gotcha: multi-statement schema SQL needs
  the raw asyncpg connection — prepared statements reject it.)*
- **M0-3 ✅** two-tier sync (`app/sync.py`, routers `sync`+`runs`, CLI `python -m app.sync`).
  Backfilled **28,458 photos / 650 annotations** == source. Full correctness gauntlet passes:
  idempotent reconcile, monotone append, insert→append, mutate→reconcile, delete→missing_since
  (row kept), reappear→cleared.
- **M0-4 ✅** SvelteKit web: dashboard (health pills, mirror counts, append/reconcile buttons,
  sync-state + run history). `bun run check` clean; CORS ok.
- **M1-1 ✅** parser (`app/parser.py`) ported from `resolve_anchors.py:parse_body` — pure,
  total (never None), `oops`/`unnamed`/`uncertain`/coords/wiki/type-guess as data. 11/11 tests.
- **M1-2 ✅** `POST /api/parse/run` (`facts.py` + `routers/parse.py`): 491 current annotations
  → **1233 facts**, each in its content-addressed graph; SPARQL count == run stats. **Re-run
  idempotence proven**: second identical run → still 1233 graphs, every fact carrying two
  `prov:wasGeneratedBy` links (provenance stacks, store doesn't bloat). Data profile: 4 oops,
  113 unnamed, 125 uncertain, 22 wiki, 4 embedded-coords.
- **M1-3 ✅** `GET /api/annotations[/{id}]` — SQL page (mirror⋈photo) + ONE SPARQL VALUES query
  for the page's facts (fact IRI, status, per-fact); filters: pano (461), status (graph-side
  pre-filter), text search, photo_id; detail adds supersession chain + hillview web link.
- **M1-4 ✅** `POST /api/facts/curate` — per-fact approve/reject/reset as plain triples about
  the fact-graph URI. **Verified: approval SURVIVES a full re-parse** (content addressing);
  per-fact granularity (labelText approved while sibling onPhoto stays proposed); status
  filter finds curated items.
- **M1-5 ✅** bench UI (`enrich/web`): `/annotations` (persisted filters, thumbnails,
  |-segmented bodies, fact chips), `/annotations/[id]` (photo+meta+history | facts with
  ✓/✗/↺ verbs + re-parse), `/runs`, `/sparql` (persisted query box + canned examples).
  All pages 200, `bun run check` clean.
- **A-1 ✅** analyzer container: `scripts/analyzer/Dockerfile` (+allowlist dockerignore,
  context=repo root, PYTHONPATH=/app/backend replaces the sys.path hack), root-compose service
  under `profiles: ["analyzer"]` (secret `openrouter_api_key`, volume `analyzer_data:/data`
  seeded with the 44,690-file session cache, `ANALYZER_MODEL` env; `--datadir` honors
  `ANALYZER_DATA_DIR`). **Verified by one-shot dry-run**: in-network DB claim, secret, image
  URL from sizes, both LLM passes, full distilled analysis — no DB write. The loop is
  intentionally NOT auto-started (free OpenRouter model is flaky; only-502 retry; user is wary
  of hammering it). Start it with: `./compose.sh --profile analyzer up -d analyzer`.
  Quirk: `--once` doesn't exit after its photo (re-enters the wait loop) — stop manually.

- **M2 ✅ (geocode bench)** — `app/geocode.py` (Nominatim @ nominatim.ueueeu.eu + Wikipedia
  coords, durable Postgres cache `geocode_cache`, polite pacing `GEOCODE_DELAY`);
  `POST /api/geocode/run` (background, progress on the run row) reads **labelText facts from
  the graph and skips rejected ones** — curation feeds downstream. Candidates are **canonical
  OSM URIs** (`hv:anchorCandidate`, the curatable fact = the anchor when approved) with
  metadata facts (`hv:coords`/`hv:displayName`/`hv:osmType`) *about the OSM URI* — identical
  metadata re-emitted for another annotation/run dedupes by content-addressing. Wikipedia
  candidates use the page URL. Plausibility (km, Δbearing vs photo) is computed LIVE in
  `GET /api/annotations/{id}/candidates` — a knob, not baked into facts. UI `/geocode`:
  annotation list | Leaflet map (tiles4.ueueeu.eu; blue photo dot + bearing ray, candidates
  colored by status) + candidate table with ✓/✗/↺.

- **M2b ✅ (calibration bench)** — `app/calibrate.py` (Theil-Sen, anchor auto-pick:
  approved > wikipedia > best in-view nominatim by cached importance) + `routers/calibrate.py`
  (`GET /api/panos`, `GET /api/panos/{id}/calibration`, `POST /api/calibrate/accept` —
  server-side refit is authoritative, run-tracked, emits `hv:calibratedBearing`/
  `hv:calibratedFov`/`hv:calibrationRms` facts about the pano). UI `/calibration`:
  pano list → live SVG scatter (Δazimuth vs rect-x, fit line + residual whiskers, click-to-
  exclude) + anchor table sorted by |residual| + **auto-kick >10°** button; fit recomputes
  client-side per toggle (`lib/theilsen.ts` mirrors the server), accept persists.
  **Ground-truth checks:** `333e8851` FOV **81.2°** (old pipeline: 80°); `f4b4d58c` raw
  136.6° (old label-fit: 138°; `.pto` truth 122° — the gap is outlier contamination, the
  point of the kick/curation workflow). Anchors improve as geocode curation proceeds —
  approved candidates always win the auto-pick.

- **M3 ✅ (matching bench + queue)** — `app/matching.py` (view-pie gate: pie = position +
  bearing±half + radius = LLM farthest×slack; same-side constraint; ALL knobs are request
  params). `routers/matching.py`: `GET /api/annotations/{id}/view_candidates` (target = the
  annotation's picked anchor, same rule as calibration), `POST /api/matching/verdict`
  (**`hv:depictedIn` facts + curation status = the growing gold set**), `POST
  /api/matching/enqueue` → **Remoulade over RabbitMQ** (`enrich_rabbitmq`, loopback :5672),
  `POST /api/matching/result` (worker callback, token auth, overlay JPEG → artifacts volume),
  results in the `match_results` table (evidence = SQL; verdicts = facts). **Matcher worker**
  (`enrich/matcher/worker.py`): runs HOST-side on `scripts/enrich/.venv` (torch + MASt3R repo +
  checkpoint), consumes the `matching` queue, POSTs back — the untrusted-worker topology
  (broker + HTTP callback only, no DB creds; cf. accounts-assessor), same shape for a future
  GPU box. Start: `cd enrich/matcher && ../../scripts/enrich/.venv/bin/python -m remoulade
  worker --threads 1`. Gotcha: PyPI remoulade needs `remoulade[rabbitmq,limits]` — broker.py
  imports "optional" extras unconditionally (the user's vendored fork in accounts-assessor
  exists for reasons). UI `/matching`: annotation picker | knob row | map (amber target ring,
  candidates colored by verdict) | candidate table (thumbnails, dist/Δ°, match button →
  inliers/raw = ratio% + overlay link, ✓/✗/↺ verdicts). Poll-refresh while jobs queued.
- **Ops (2026-07-16):** VM caddy (`~/caddy`, host-network docker) now serves the whole
  workbench on **:8765** — the port the host's caddy forwards the Yggdrasil address to
  (`http://[200:27c9:…:2906]` → VM:8765) → phone-reachable. Same-origin `/api` → :8070,
  rest → :8071; web `config.ts` defaults to relative `/api` + vite dev proxy;
  `allowedHosts: true`. Old viz_app inspector moved to **:8766** (local only).
  **Dump format 2** (2026-07): photos gained `place_parent_name/slug`, `effective_at`,
  `retry_after_minutes`; `seed_dev_from_dump.sh` is now header-driven (loads any format).

- **M3 verification (gold pairs, 2026-07-16):** the June ground truth reproduces through the
  whole new stack — `67c6c4b9 × 4b8cac8a` (true): **324/547 = 59.2%** (June: 63%);
  `× d0955198` (Doppelganger): **90/205 = 43.9%** (June: 38%). The inlier-ratio discriminator
  holds; both verdicts recorded as the first `hv:depictedIn` gold facts.
- **OOM protection (2026-07-16):** risky work is double-guarded (pattern:
  `backend/worker/throttle.py` → pics `src/lib/throttle.py`). *Belt:* `ram_gate()` in the
  matcher worker waits for `MATCHER_REQUIRED_GB` (6 GiB) free before the heavy phase and
  **fails the job visibly** after a timeout (queue jobs must not block forever). *Braces:*
  `enrich/matcher/run_worker.sh` runs the worker as a systemd transient service with
  `MemoryHigh=8G` / `MemoryMax=10G` / `MemorySwapMax=0` + `Restart=on-failure` — a runaway
  kills only the unit, RabbitMQ redelivers, `max_retries=1` caps poison loops. All enrich
  containers carry `mem_limit`s (db/oxigraph 2g, api 1.5g, rabbitmq 768m). Observed: MASt3R
  pair peaks ~5.4 GiB.

- **M2c ✅ (reverse POI placement / proto-annotations, 2026-07-17)** — the calibration
  model run backwards: `POST /api/panos/{id}/place_poi` {wikipedia_url, save, assumed_fov?}
  → wiki coords (`wikipedia_coords`, now with a REST-summary fallback for pages whose
  infobox never registers with GeoData, e.g. cs: Žižkovská televizní věž) → azimuth/km →
  invert the pano's accepted calibration (approved-first, else newest accept run):
  `x = 0.5 + ang_norm(az − centre_bearing)/fov ± rms/fov`. Out-of-frame is a first-class
  answer (`off_frame_deg`). Save mints a **proto-annotation**: pure facts under
  `/id/proto-annotation/{sha256(photo_id|wiki_url)[:16]}` (idempotent; verified: re-save
  → same IRI) — `rdf:type hv:ProtoAnnotation`, `hv:onPhoto/labelText/wikipediaPage`,
  `hv:assumedX(+Error)`, plus the wiki-page `hv:coords` triple which content-addresses to
  the SAME fact graph the geocode bench mints (cross-workflow corroboration for free).
  `GET /api/panos/{id}/protos` → FactChip-shaped rows; curation via the ordinary
  `/api/facts/curate` (verified round-trip). URL parsing is urlsplit-based, NOT parser
  `WIKI_RE` (its charset excludes `)` → truncates `Bezděz_(hrad)`), and normalizes mobile
  hosts (`cs.m.wikipedia.org` — phone pastes). UI: "Place a POI" card on `/calibration` —
  preview/save, markers + error band over the pano strip, proto table with curation chips;
  uncalibrated panos get an assumed-FOV input (compass-only estimate, flagged). Approved
  protos are future calibration anchors (bootstrapping loop); graduation to real Hillview
  annotations is the M5 push-back's job (`Title | wiki-url` round-trips through the parser).

- **Photo record page ✅ (2026-07-17)** — `/photos/{id}` + `GET /api/photos/{id}`: the
  subject-oriented counterpart to the task-oriented benches (photo IRIs finally have a page,
  like annotation IRIs got in M1). Header (pano/calibrated/missing badges, hillview.cz +
  calibration-bench links), **strip with annotation rects drawn** (first time rects render
  in the workbench; click → annotation detail) + proto markers + POI preview band, photo
  facts w/ curation chips, the **Place-a-POI card moved here** (its natural home —
  `/calibration` is a pure bench again, linking here), proto table, annotations table
  (superseded/missing toggle), match evidence both directions (as-pano / as-candidate w/
  gold verdict), position mini-map. `/calibration` selection now lives in the URL
  (`?pano=…` — shareable/reloadable, important for phone use); annotation detail links its
  photo. Benches do batch work with knobs; the photo page is where you look at one thing
  and curate — don't duplicate fitting UI there. Plus a **/photos index** in the top nav
  (`GET /api/photos`: search title/place/id-prefix, pano/annotated/calibrated filters,
  most-annotated first, paged) and inbound links wherever a photo shows: annotations-list
  thumbnails, matching bench (selected pano + candidate thumbs/ids), annotation detail.

- **Parser v2 (2026-07-17):** TYPE_KEYWORDS now match on word boundaries — v1
  substring-matched "hrad" inside "Zahradní" → castle, "vrch" in "Vrchlického", etc.
  (PARSER_VERSION "2", tests extended to 12). Full re-parse ran; 14 stale v1 typeGuess
  facts (none curated) were dropped from the graph — stale = a typeGuess fact the new
  run didn't re-emit, i.e. lacking the latest run's provenance, which is the clean
  criterion the content-addressing gives for free. Annotation detail now groups facts
  (parsed-from-body / anchor candidates with nested candidate metadata / other), the
  API exposes each fact's subject, and a "?" explainer covers where facts come from.

- **Refine-anchor flow ✅ (2026-07-17)** — the seed of the future user-facing entry UX
  (suggest-as-you-type + map pinpoint), prototyped on the annotation detail page:
  - `GET /api/annotations/{id}/suggest?q=` — **viewpoint-aware ranking** of Nominatim hits
    (q defaults to the label): score = importance + 1·in_view (view pie: distance ceiling
    by type + |Δbearing| ≤ TOL) + 0.5·type_match (typeGuess's first real consumer,
    TYPE_MATCH map) + up to 1·rect-x consistency on calibrated panos (inverted calibration
    predicts each candidate's x; compare with the drawn rect). Components returned so the
    UI shows WHY. Verified on "Zahradní město": Louny/Trutnov homonyms sink out of view.
  - `POST /api/annotations/{id}/anchor` — {point:{lat,lon}} or {candidate: nominatim-dict}
    → mints the anchorCandidate fact + approves it in one act (kind=anchor_pin run).
    Points become **`geo:` URIs** (RFC 5870), canonical 5-decimal form; coords live in the
    identifier, no metadata facts. Round-trip is IDEMPOTENT by design: pin → geo: fact →
    (future push-back) body "Label | 50.06030N, 14.49300E" → re-parse → same fact IRI.
  - **embeddedCoords are now anchor candidates**: the geocode run mints geo: candidates
    from body-embedded coords (previously parsed but ranked nowhere — author coords are
    the strongest signal). pick_anchor tier is now approved > **pinned (geo:)** >
    wikipedia > nominatim-in-view.
  - UI: Anchor section on annotation detail — suggest input + ranked table (score/km/Δ°/Δx,
    ⚓ set), CandidateMap grew `onmapclick` (+ bubblingMouseEvents:false on markers) →
    click map → 📍 pin → "⚓ pin anchor here". Body serialization concern resolved: the
    body is the portable projection ("Label | coords"), the fact store keeps full fidelity.

- **ZoomView extraction, bite 1+2 ✅ (2026-07-17)** — incremental refactor of the
  frontend's OpenSeadragonViewer monolith (2k lines, solid but test-poor → go slow,
  small reviewable bites, each extraction ADDS the missing tests):
  - Bite 1 (frontend, behavior-identical): `computeMinLevel` + `buildTileSource` moved
    verbatim to **`frontend/src/lib/zoomview/tileSource.ts`** (dependency-free, structural
    `DziPyramid` type — photoCommon untouched) + 7 behavior-pinning unit tests. Full
    frontend suite 406/406, svelte-check clean.
  - Bite 2 (workbench-only): enrich/web consumes it via **`$zoomview` alias**
    (vite resolve.alias + fs.allow; tsconfig `paths` must re-declare the generated
    `$lib` entries — "paths" replaces wholesale). New `OsdViewer.svelte` (thin OSD embed:
    DZI pyramid from mirrored `sizes.full.pyramid`, tiles straight off pics.hillview.cz,
    rect overlays in viewport coords, zoom-to-rect/fit buttons, navigator strip) on the
    **annotation detail page** — auto-zooms to the annotation's rect. openseadragon@6
    ships no types → `declare module` shim. Docker: web build context widened to repo
    root (compose `context: ..` — compose-file-relative!) + allowlist
    `Dockerfile.dockerignore` (analyzer pattern, 146 kB context).
  - Bite 3 ✅ (edge labels): `labelLayout.ts` (+tests) was ALREADY pure — git-mv'd
    utils/ → zoomview/ (history preserved). The canvas painting passes moved verbatim to
    **`zoomview/labelPaint.ts`** (`paintLabels(ctx, W, H, cmds, style)`) + 6 pinning
    tests using a recording-ctx mock (op order: clear → all leaders → all pills; dash
    toggling; roundRect fallback). Frontend 412/412. Workbench OsdViewer now draws edge
    labels (canvas overlay, viewport-change + ResizeObserver → rAF → layout → paint,
    fingerprint skip) — same pills/leader lines as the main app.
  - Bite 4 ✅ (annotorious glue): `targetToPixels`/`targetToNormalized` moved verbatim
    annotationApi.ts → **`zoomview/annotationTargets.ts`** (annotationApi re-exports, so
    importers untouched) + `toW3cAnnotation` (the W3C shape from syncAnnotationsToViewer)
    + 7 pinning tests (round-trip, non-mutation, xywh fragments, array selectors, W3C
    shape). Frontend 419/419. Workbench OsdViewer swapped its hand-rolled overlay divs
    for a **read-only annotorious mount** (dynamic import, per-kind DrawingStyle,
    clickAnnotation → onrectclick) fed through the same shared glue as production.
  - Bite 5 ✅ (viewer-init unification, completes the planned list): **`zoomview/
    viewerInit.ts`** — `OSD_VIEWER_DEFAULTS` (the main app's exact options),
    `initialSourceFor` (fallback-thumb vs main source), `swapInMainSource` (the
    addTiledImage + fully-loaded-change dance, verbatim incl. the throw-on-error) +
    7 pinning tests w/ mock viewer/world/TiledImage (immediate vs deferred fallback
    removal, partial events, single-item guard, error surface). Frontend 426/426.
    OsdViewer adopted defaults+swap and gained `fallbackUrl` — the workbench now has
    the production progressive-load path (cached 640px thumb instantly → DZI over it →
    thumb removed); annotorious rects re-sync on world add-item to stay anchored to
    full-image pixel space. `zoomview/` now = tileSource, labelLayout, labelPaint,
    annotationTargets, viewerInit — every module unit-tested.
  - Bite 6 ✅ (photo page adopts OsdViewer): the static strip + hand-rolled overlays
    replaced by the deep-zoom viewer — all annotation rects via annotorious (click →
    annotation detail, edge labels), protos + POI preview as canvas-drawn **vertical
    marks** (new `marks` prop: full-height line + label tag + translucent error band;
    projected xs folded into the repaint fingerprint so pure pans repaint; colors are
    literal hexes — canvas can't resolve CSS vars). Props are live: an `$effect` on
    rects/marks re-syncs annotorious + repaints (protos load async, POI previews appear
    on demand). Progressive load: 1024px strip (cached) → DZI. Out-of-frame protos sit
    past the image edges, visible when zoomed out.
  - Bite 7 ✅ (matching bench adopts OsdViewer — adoption arc complete): **side-by-side
    compare panel** between map and candidate table: left = the annotation region
    (pano deep-zoomed to the rect; annotation detail fetched on select for the target),
    right = the ⊙-picked candidate photo (per-row ⊙ button — deliberately NOT the
    hover-highlight `selCand`, which would churn OSD instances on every mouse move).
    `view_candidates` now returns candidate `width`/`height`. Eyeball → ✓/✗ verdict in
    one screen. All three surfaces (annotation detail, photo page, matching bench) now
    run the shared-glue OsdViewer.
  - Bite 8 ✅ (relocation to **repo-root `shared/zoomview/`**): git-mv'd out of the
    frontend; frontend consumes via `kit.alias` `$zoomview` (auto-generates tsconfig
    paths), vitest gained the shared include + `server.fs.allow` (vite's fs sandbox
    blocks out-of-root test files — 5 files silently failed until allowed). SECURITY:
    fs.allow is scoped to `['.', '../shared']`, NEVER `'..'` — the repo root holds
    secrets/ and the frontend dev server binds publicly (verified: shared module 200,
    secrets 403). Frontend docker context widened to repo root (compose `context: .`,
    COPY paths prefixed `frontend/`, shared dir → `/shared/zoomview`, allowlist
    `Dockerfile.dockerignore` mirroring frontend/.dockerignore — 2.9 MB context);
    workbench build updated the same way. Both containers rebuilt/redeployed; 426/426.
  - **Invisible-rects bug, real root cause**: annotorious's internal format REQUIRES
    pixel-space **`geometry.bounds`** — its spatial index reads
    `target.selector.geometry.bounds` directly, so a synthetic target without it
    renders nothing, silently. Production never hits this because DB targets carry
    bounds (annotorious wrote them at creation; verified in the mirror: bounds are
    pixel-space while x/y/w/h are normalized). OsdViewer now computes bounds when
    building targets from rects. (The 3.7.22 version pin made along the way was NOT
    the cause but stays — both apps should upgrade annotorious in lockstep.)
  - Annotation detail gained a **zoomview ↗ link**: hillview.cz map URL with
    `photo=hillview-{id}` + `x1..y2` viewport bounds computed from the annotation rect
    (OSD coords: x normalized to width, y scaled by aspect) — opens the production
    viewer pre-zoomed to the rect.

- **Ray-mode matching + pie visualization ✅ (2026-07-17)** — the discovery flow the
  bench was missing: a bare `?` rect has no anchor, so `view_candidates` gained modes
  (auto|target|ray). **Ray mode**: the pano's calibration turns rect-x into an azimuth
  (`centre_bearing + (x−0.5)·fov`; compass+assumed_fov fallback) — the unknown lies on
  that ray. Wedge = azimuth ± ray_half (default from rect width + rms) over
  [near_m, far_m]. `overlap=true` = viewpie×viewpie via **ray sampling** (points every
  ~step along the ray tested with the existing `in_pie` — candidates report
  `hit_range` = which ray segment they see); `overlap=false` = plain position-in-wedge.
  **Ranking by `ray_dist_m`** (min distance to the ray = proximity to the unknown) —
  dist-to-pano is meaningless in ray mode (top hits were the pano's neighbors before).
  CandidateMap draws the amber **wedge sector** + the hovered candidate's own **pie
  sector** (dest-point sector polygons). `/matching?annotation=` is URL state
  (deep-linkable; annotation fetched directly, needn't be in the picker). Bench knobs
  adapt per mode (near/far/pie∩ray vs same-side). Annotation detail: **Matching
  summary** (match_results table + bench deep link) and `hv:depictedIn` verdict facts
  regrouped into their own "matching verdicts (gold set)" section (were mislabeled
  under parsed-from-body). Verified: Zahradní město ray az 109.87° (calibrated pano),
  top candidates 17 m off the ray = photos standing at the unknown. The map also draws
  the **origin pano's own view pie** (dashed blue sector; calibrated centre/FOV when
  available, else compass ± assumed_fov/2; radius = its LLM far distance × slack —
  `pano.pie` in the response), and the hovered candidate's pie is colored by its
  verdict status. Plus **`annotation_pie`** (violet): the single annotation's EXACT
  rect slice — left..right edge through the calibration, no padding — the measurement,
  nested inside the amber padded search wedge, nested inside the pano's full pie.
  Sight-line rects (w ≈ 0, e.g. a bare `?` stroke) collapse that sector to an invisible
  hairline (half clamps at 0.3°), so CandidateMap also draws the pie's **solid center
  ray** — the assumed direction stays visible at any rect width, and the ray's near
  point is folded into fitBounds. The annotation detail page's **anchor map** gets the
  same treatment: `/annotations/{id}/candidates` now returns `photo.pie` +
  `annotation_pie`, so the pano view pie and the annotation's sight ray render right
  where anchors are pinned (pin along the ray). Batch automatching: **▶ match all N**
  button enqueues a MASt3R job for every shown candidate without one (best-ranked
  first; serial worker ≈ 30–60 s/pair warm, ~6 min cold model load); limit knob goes
  to 1000 so a whole ray-gate result set can be covered; the results poll backs off
  to 30 s when >10 jobs are queued (view_candidates is a ~3–4 s query). Bench layout:
  the annotation picker is a ☰ pop-up (default closed; auto-opens when no ?annotation
  in the URL); the left column is the candidate list in its own scroll container
  (sticky column headers), with the map + pairwise preview fixed alongside it.

- **Curated rename ✅ (2026-07-17)** — `POST /annotations/{id}/label` mints an
  hv:labelText fact and approves it in one act (kind=label_edit run), demoting any
  previously-approved label to rejected ("superseded by…"). The mirrored body is
  untouched — one-way sync holds; serializing the name back into the Hillview
  annotation is graduation's job. Downstream follows automatically: geocode iterates
  non-rejected labelText facts, so a rename redirects future geocoding; UI label
  helpers prefer approved > parser > raw body. UX: ✎ label button on the annotation
  detail header (prompt pre-filled with the current resolution). Photo-page
  annotation rows gained a `match ↗` deep link to the bench. Three one-click label
  sources all route through this verb: header ✎ (free text), 📖 wiki-attach's
  "adopt as name" (page title), and a per-row ✎ in the Nominatim suggest table
  (the hit's leading display_name component) — the same text already shown as the
  hit name; independent of ⚓ set (adopting the anchor), since name/anchor/wiki are
  separate curations.

### Graduation (M5) — design sketch (2026-07-17 discussion)

Transport = **file drop, kept deliberately**: the workbench (and any AI operating
it) never holds Hillview write credentials; a package file + human accept inside
Hillview's own admin is the trust boundary. Simplifications over the first sketch:
- **No second review bench.** Curation IS the review. The package builder exports
  approved-but-not-yet-landed facts; the workbench "review page" is just a read-only
  preview of that derived diff before dumping.
- **Hillview never parses RDF.** Package = JSON ops manifest (per-annotation:
  before/after body, precondition = expected current body/updated_at, human-readable
  summary) + the TriG fact dump riding along as provenance appendix. The Hillview
  admin page renders the JSON and applies ops mechanically under a dedicated
  **enrichment bot account** (not the personal admin — attribution + revocability).
- **No acknowledgment protocol.** The mirror sync closes the loop: after Hillview
  applies, the next sync shows the suggested body as the mirrored body and the
  ledger marks the package "landed" by observation. Conflicts = precondition
  mismatch → op skipped and listed, never clobbered.
- The op generator is the already-specified idempotent body serialization
  ("Label | geo:…") — body stays the portable projection of approved facts.

Decisions (2026-07-17): personal admin account for now (bot account later);
**double review stays** — the workbench preview teaches the operator what they're
proposing, and the Hillview-side preview verifies both systems interpret the same
package identically (two independent implementations agreeing = the check);
**RDF enters Hillview via the API server**, not the frontend — the applier is the
authoritative interpreter, and previews must render ITS interpretation (a JSON
projection endpoint), or the frontend/backend could drift apart, defeating the
cross-check. Long game: the pipeline prototypes "user draws a rect → what is
this? → jobs → suggestions" as a native Hillview flow.

- **Graduation preview page ✅ (2026-07-17)** — `/graduation` + GET
  `/api/graduation/suggestions`: for every annotation with an APPROVED labelText /
  anchorCandidate fact, serialize the facts into the body format (in-place segment
  edits: name ← approved label, coords ← anchor at 5 dp, wiki appended; unmodeled
  segments — context, non-wiki URLs — preserved verbatim; parse_body round-trip +
  idempotency pinned by app/tests/test_graduation.py, suite 20 passing). Response
  splits `suggestions` (changes non-empty) from `landed` (facts already reflected —
  how mirror-sync loop-closure will mark packages as landed). Anchor coords resolve
  from geo: URIs directly or the candidate's hv:coords fact (OSM/wikipedia).
  Verified live: 6 pending (e.g. `?` → `Plynárna Michle - komín 1 | 50.05422N,
  14.46877E`), 2 already-reflected. Nothing writes from this page; export (.trig +
  ops manifest) is next.

- **Wikipedia attach ✅ (2026-07-17)** — `POST /annotations/{id}/wikipedia` {url}:
  mints + approves an hv:wikipediaPage fact (kind=wiki_attach run) — the "I found
  the POI's wiki page" gesture on the annotation detail (📖 attach input in the
  Anchor section). URL parsing via shared `geocode.parse_wikipedia_url` (extracted
  from proto's place_poi: urlsplit-based, keeps `)` titles, normalizes `xx.m.`
  mobile hosts). If the page has coordinates (GeoData → REST fallback, cached), an
  anchorCandidate + coords fact is minted as PROPOSED alongside — adoptable as the
  anchor with one ⚓ click, but an existing pin stays authoritative. The page
  TITLE is also minted as a PROPOSED labelText (feeds geocode; ✎ adopt-as-name
  button runs it through the label verb to approve — deliberately NOT
  auto-approved: verified live that a `?` chimney with the user's precise
  "Plynárna Michle - komín 1" label keeps it over the generic wiki title
  "Plynárna Michle"; auto-approve would have clobbered the better name).
  Graduation serializes approved wikipediaPage facts into the body's wiki segment
  (approved page fact wins over a wiki-URL anchor; appended only when the body
  has no wiki segment); the proposed wiki label stays out of graduation until
  adopted. Suite 21 passing. Cleanup caution learned: content-addressed facts
  dedupe ACROSS features (e.g. wiki-coords shared by geocode + protos), so
  run-provenance-based cleanup must GROUP BY fact and check COUNT(DISTINCT ?run)
  = 1 before DROP GRAPH.

- **Package export ✅ (2026-07-17)** — `POST /api/graduation/export`
  {annotation_ids?, note?} (empty = all pending; the /graduation review IS the
  selection) → the graduation package: `{package, format_version:1, source,
  created_at, run_id, counts, ops[], provenance_trig}`. Each op =
  `{op:"set_annotation_body", annotation_id, photo_id, precondition:{body:<mirrored
  body>}, body:<suggested>, summary, facts:[fact IRIs]}` — the ops manifest is
  AUTHORITATIVE for the apply; the body precondition means a concurrent Hillview
  edit → skip, never clobber. `provenance_trig` = fully-expanded TriG (no prefixes,
  robust for any parser) of the cited fact graphs + their meta (about/wasGeneratedBy)
  + curation (status/curator/decidedAt) subsets, incl. non-geo anchors' coords
  metadata graphs → self-contained enough for Hillview to re-derive & cross-check.
  Read-only w.r.t. facts (landing observed via mirror sync, nothing marked); logs a
  kind=export run. `_compute_suggestions()` refactored out of the GET handler so both
  share one code path (internal `fact_iris` stripped from the GET view via `_public`).
  Serializer validated by round-tripping the TriG back through Oxigraph: quad count
  unchanged (53449→53449) = parses AND matches existing data faithfully. Frontend:
  ⬇ export-package button on /graduation streams the JSON as a browser download
  (`hillview-enrichment-<ts>.json`). Verified: 11 ops / 28 facts across geo:/OSM/wiki
  anchors. NEXT: Hillview-side admin page (pyoxigraph parse the appendix, render the
  applier's own interpretation as the cross-check, apply ops under admin).

- **Hillview-side applier ✅ (2026-07-17)** — the package's destination: the
  production Hillview app (backend + frontend), NOT the workbench. **RDF enters
  Hillview here** (first `pyoxigraph` use). Backend `backend/api/app/graduation.py`
  + `graduation_routes.py` (admin router `/api/admin/graduation`, `require_admin()`):
  `GET /packages` lists files in the incoming drop-dir; `GET /packages/{f}` previews
  each op with THREE bodies — precondition (what the workbench saw), current (live
  Hillview, resolved by following the supersede chain to the head), suggested — plus
  status (clean|conflict|already_applied|missing|deleted), the annotation's photo
  (sizes/pyramid) + target for OSD, and provenance parsed from the TriG appendix
  (pyoxigraph, best-effort: fact→predicate/object + curation status/curator/decidedAt);
  `POST /packages/{f}/apply` {annotation_ids} supersedes the current head (new row,
  body=suggested, target=head's — body-only op, admin-authored, event_type='updated'),
  then archives the file to applied/ once every op is reflected. **Per the user's
  change: conflicts are NOT skipped** — the UI warns + shows all three versions and
  applies over the current head anyway. Frontend `/admin/graduation` (Svelte, admin-
  gated like other admin pages): package list → op list (status badge + checkbox,
  applicable = clean|conflict) → focused-op detail with a single mounted OSD viewer
  (photo + the annotation rect, zoomed) because "annotations can't be recognized from
  uids or `?` labels", three bodies (conflict-highlighted), provenance facts, bulk
  Apply. Copied the workbench's tested `OsdViewer.svelte` into frontend/src/lib/
  components (deps openseadragon/@annotorious already present; $zoomview alias too).
  Drop-dir = `/app/data/graduation/{incoming,applied}` (host backend/data/…, bind-
  mounted; must be writable by the api container uid 1001 — chmod 777 in dev).
  pyoxigraph added to api pyproject; dev-installed into the running container
  (`pip install --user` + container restart to clear the boot-time path cache).
  Verified live end-to-end on throwaway annotations: clean apply (supersede),
  conflict apply (all 3 versions, was_conflict flag, applies anyway), already_applied
  idempotency, archive-on-complete; provenance shows approved labelText/anchorCandidate
  with curator+timestamp. Frontend rebuilt (measured host build 2.94 GB peak < 4G
  before the docker build; image built then container recreated, 2 s downtime).

Full detail + next steps: plan file `~/.claude/plans/imperative-crafting-wombat.md`.
Next: RDF cross-check (Hillview independently RE-DERIVES the body from the TriG facts
and diffs vs the manifest — the two-interpreters agreement; needs the parser +
suggest_body ported to Hillview); enrichment bot account for apply attribution;
pano source-frame work; GPU-box matcher.

## Why (the reframe)

The 2026-06 experiments produced working *engines* — annotation parsing, Nominatim/Wikipedia
geocoding, pano anchor calibration, MASt3R pair matching + view-pie gating, MASt3R-SfM
reconstruction — but as scripts over CSV dumps emitting static HTML. What was missing is the
**spine** (a real DB, live data, jobs/runs) and the **cockpit** (interactive benches to fiddle,
curate and tune). The workbench is the product; the scripts become its workers.

## Architecture

```
hillview Postgres (source of truth; local dev now, prod later)
        │  mirror-sync (read-only poll; analyzer-style skip_locked jobs)
        ▼
   EnrichDB — Postgres + PostGIS (+ pgvector later)
   mirrors · runs · jobs · facts (status+provenance) · configs
        ▲                                   ▲
   workers (containers)                workbench
   · analyzer (LLM, containerized)     · api: FastAPI (thin, EnrichDB-only)
   · geocoder (Nominatim/Wikipedia)    · web: SvelteKit — one bench per workstream
   · matcher / recon (MASt3R, GPU-ready)
        │
        └── push-back adapter → hillview API (ships only APPROVED facts:
            place names, annotation locations, suggest-on-draw)
```

Lives in **`enrich/`** at the repo root (sibling of `backend/`, `frontend/`), its own compose
stack. Heavy deps (torch, MASt3R) stay in worker images, never in the Hillview api image.
Worker images must also run on a rented GPU box pointing at the same EnrichDB.

## The two spine ideas

1. **Every derived fact is a row with provenance and a status.**
   `facts(subject_type, subject_id, kind, payload jsonb, source, run_id, confidence,
   status: proposed → approved | rejected → pushed, note)`.
   Curating Nominatim results = flipping status on candidate rows in a map UI. "The anchor set"
   = `kind='anchor' AND status='approved'`. Push-back ships only approved facts. This is what
   turns fiddling into accumulating value.

2. **Runs and jobs are first-class.**
   Every sweep (parse pass, geocode pass, matching sweep, reconstruction) is a `runs` row with
   its params jsonb + artifact dir; workers claim `jobs` via `FOR UPDATE SKIP LOCKED` (the
   analyzer's own pattern, promoted system-wide). The static reports become run-detail pages;
   a jobs dashboard shows queue/running/failed + worker heartbeats. Reproducibility for free.

## Schema (M0)

- `photo_mirror`, `annotation_mirror` — synced subsets of the main tables (id, geometry,
  bearing, sizes, analysis, body/target…), `synced_at`.
- `runs(id, kind, params jsonb, status, started_at, finished_at, artifacts_dir, note)`
- `jobs(id, kind, subject, params jsonb, status, claimed_by, heartbeat_at, run_id, error)`
- `facts(...)` as above, unique on (subject, kind, source) where it makes sense.
- `configs(name, kind, params jsonb, updated_at)` — named tuned parameter sets (e.g. view-pie).

## Benches

| Bench | What you see / fiddle | Verbs | Graduates to |
| --- | --- | --- | --- |
| **Annotations** (first) | all annotations live; body text → parsed structure (label, type guess, embedded coords/URLs, `?` uncertainty, `oops` markers); LLM `analysis` viewer | approve/fix parse, flag | cleaner annotation model in Hillview |
| **Geocode** | per-label Nominatim/Wikipedia candidates on a map; query-variant + filter knobs | accept/pick/reject candidate → anchor fact | user/admin "locate this label" feature |
| **Calibration** | per-pano Theil-Sen azimuth fit; toggle anchors in/out; bias/FOV refit live | exclude anchor, accept calibration | trustworthy pano poses |
| **Matching / view-pie** | candidate gate with sliders (VIEW_HALF, SAME_SIDE, slack…) live on map; MASt3R pair viewer | record verdict (true/false pair) → gold set grows while browsing; save config | suggest-on-draw in zoomview |
| **Recon** | pick cluster (map + time window), launch as job, watch; report + 3D viewer per run | launch, compare runs | 3D layer, walk→world |
| **Jobs/Runs dashboard** | queue, running, failed, worker heartbeats; run history with params | retry, cancel | — |

## Workers

- **analyzer** — the existing `scripts/analyzer` LLM loop, containerized; claims `jobs
  (kind='llm_analyze')` from EnrichDB, still writes `analysis` back to the Hillview DB (the app
  consumes it), mirrors into EnrichDB. Its progress becomes visible in the dashboard.
- **geocoder** — `resolve_anchors`/`annotation_geocode` logic as a job kind; emits candidate
  facts (status=proposed) for the Geocode bench.
- **matcher / recon** — wraps the `scripts/enrich` engines (`viz_app` matching internals,
  `reconstruct.py`) as job kinds; GPU-ready image; artifacts land in the run's dir and are
  served by the workbench.

## Staging

- **M0 — skeleton**: `enrich/` compose (enrichdb + api + web), schema, mirror-sync from the
  local dev DB, import existing CSV-derived assets (annotation_anchors, run metadata). Existing
  viz_app (:8765) and static reports stay untouched as the bridge.
- **M1 — Annotations bench**: mirror-backed annotation browser + parser worker + curation verbs.
- **M2 — Geocode bench** (+ geocoder worker, candidate curation on a map).
- **M3 — Matching bench** (view-pie knobs live, pair viewer, verdict recording), **analyzer
  container** + jobs dashboard.
- **M4 — Recon bench** (job-launched `reconstruct.py`, run browser, 3D viewer port).
- **M5 — push-back adapter** + first graduated feature (annotation location / place names);
  prod live-data decision.

## Relationship to existing assets

Scripts in `scripts/enrich/` remain the computational engines, invoked by workers rather than
rewritten. `viz_app.py` keeps serving as the inspector bridge until each of its views is
absorbed by a bench. Static HTML reports become run artifacts. The docs stay the spec:
`vision-subsystem.md` (techniques, findings), `reconstruction-field-notes.md` (empirical log).
