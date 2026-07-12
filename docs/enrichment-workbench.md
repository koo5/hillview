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

Full detail + next steps: plan file `~/.claude/plans/imperative-crafting-wombat.md`.
Next: M3 (matching/view-pie bench + Remoulade), or calibration bench, or graduation adapter.

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
