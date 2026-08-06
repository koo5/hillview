# Enrichment Workbench

Admin-only workbench for the vision/enrichment subproject: mirrors live Hillview data,
runs enrichment (annotation parsing → geocoding → anchoring → matching → 3D), stores derived
facts as RDF quads with provenance + curation status, and gives each workstream a bench UI.
Design: [`docs/enrichment-workbench.md`](../docs/enrichment-workbench.md).

## Stack

| service | what | host (127.0.0.1) |
|---|---|---|
| `workbench-db` | Postgres+PostGIS — mirrors, runs, sync state | `:15432` |
| `oxigraph` | RDF quad store — facts, provenance, curation | `:7878` |
| `api` | FastAPI — sync, parse runs, curation verbs, SPARQL passthrough | `:8070` |
| `web` | SvelteKit bench UI | `:8071` |

The `api` container also joins the main stack's **`hillview_network`** (external) to read the
dev Hillview Postgres at `postgres:5432` (alias on that network: `enrich-api`). The main
stack must be up first (`docker compose up -d postgres` at the repo root) so the network exists.

## Run

```bash
cp .env.example .env         # dev defaults work as-is
docker compose up -d workbench-db oxigraph api
# web: either `docker compose up -d web`, or the fast loop:
cd web && bun install && bun run dev    # http://localhost:8071
```

## Smoke tests

```bash
# schema landed?
psql -h 127.0.0.1 -p 15432 -U enrich -d enrich -c '\dt'
# oxigraph answers?
curl -s -X POST localhost:7878/query \
  -H 'Content-Type: application/sparql-query' \
  --data 'SELECT * WHERE { GRAPH ?g { ?s ?p ?o } } LIMIT 3'
# api healthy (checks workbench-db + hillview db + oxigraph)?
curl -s localhost:8070/api/health | jq
# mirror the dev data — one pass: new rows in, edits carried, vanished rows
# stamped missing (never deleted), workbench-native rows untouched
curl -s -X POST localhost:8070/api/sync/run -H 'Content-Type: application/json' -d '{}'
curl -s localhost:8070/api/sync/status | jq
```

## Recon bench (`/recon`)

> **Deploying UI changes:** `web` is a BUILT image, so nothing you change under `web/src` shows
> up at the normal address until `docker compose up -d --build web`. And use the **Caddy front
> (:8765)**, not the container port — `:8071` serves the app but has no `/api` proxy, so the bench
> loads with zero runs and no viewer. (`:8071/api/recon/runs` → 404, `:8765/api/recon/runs` → 200.)

Browses MASt3R-SfM reconstructions and their **structure** metrics — reprojection error in
pixels, which is the number that actually says whether a solve is good. The GPS residual is
shown beside it to be disagreed with: across the archived runs the two rank with a Spearman
correlation of 0.07. Method, traps and results:
[`docs/reconstruction-field-notes.md`](../docs/reconstruction-field-notes.md).

Two sources of runs. **Bench runs** are enqueued from `/recon` (or the API): the API selects
the cluster from the live `photo_mirror` with PostGIS and ships the worker an explicit frame
manifest, so the worker needs no DB credentials and a run records the frames it actually
used. **Imported runs** come from the archived experiments in `scripts/enrich/runs` (mounted
into the api container read-only as `/recon-archive`). Either way only the sparse layer is
stored — `metadata.json`, `metrics.json`, `points.ply`, the renders and the log, ~16 MB —
never the 1.8–2.7 GB forward-pass cache, which stays on the worker: regenerable, and needed
only to re-solve.

**RabbitMQ's ack deadline is the one that bites.** Its default `consumer_timeout` is **30 minutes**,
and a reconstruction routinely runs longer (the first 28-frame dense walk took 32 min). When the
deadline passes the broker closes the channel, which kills the worker on its ack *and requeues the
message* — so a job that already finished re-runs, forever. The compose file now sets it to 12 h via
`RABBITMQ_SERVER_ADDITIONAL_ERL_ARGS` (`RABBITMQ_CONSUMER_TIMEOUT_MS` to override); it must be at
least as generous as the actor's own `time_limit` or it silently overrides it. Symptom to recognise:
`PRECONDITION_FAILED - delivery acknowledgement on channel N timed out`, with the runs list showing
`0 consumers` and messages still queued.

The worker (`recon/run_worker.sh`) drives `reconstruct.py` as a **subprocess**, deliberately:
it has no callable entry point, raises `SystemExit`, and leaves a monkey-patched
`sparse_ga.forward_mast3r` behind, so repeated in-process runs are not idempotent. It has its
own queue and systemd unit (`MemoryHigh=12G / MemoryMax=16G`) because a walk-sized
reconstruction runs 50 min – 1.3 h and would blow the matching queue's 30-minute limit.
Progress is reported by parsing reconstruct.py's stdout, and metrics are computed on the
worker before upload.

```bash
# start the worker (another manual step after a reboot, like the matcher)
recon/run_worker.sh
journalctl --user -u enrich-recon -f

# preview a cluster before committing — the selection IS the experiment
curl -s -X POST localhost:8070/api/recon/preview -H 'Content-Type: application/json' \
  -d '{"lat":50.1172,"lon":14.4893,"radius_m":300,"limit":8,
       "after":"2026-06-15 18:28:30","before":"2026-06-15 18:29:00"}' | jq '.n_frames'

# then enqueue it (same body; params are whitelisted on both ends)
curl -s -X POST localhost:8070/api/recon/runs -H 'Content-Type: application/json' \
  -d '{"name":"my-run","lat":50.1172,"lon":14.4893,"radius_m":300,"limit":8,
       "params":{"dense":true,"win":4,"mask_anon":true}}' | jq
```

`shared_intrinsics: true` (the default) solves ONE focal for the cluster, which is what a single
camera physically has. Expect the median reprojection to rise and p90 to fall: a per-frame focal is
a free parameter the optimizer uses to absorb error, and it will happily invent a 119° fisheye on a
phone to do it. `/recon/preview` decides "one camera" from EXIF Make/Model, else the per-device
`client_public_key_id`, else owner + frame dimensions, and the form warns if the selection turns out
to be mixed-source. `dense: true` is what makes the reprojection metric computable (it needs
per-pixel depth);
`stride` defaults to 1 because **you cannot subsample a sweep** — at ~14 m spacing the solve
collapsed to 81 m of drift. The runs list reports the queue's consumer count, so a bench with
no worker attached says so instead of looking merely slow.

**The Doppelganger control.** `inject` adds photo ids to the cluster as impostors. They are
excluded from the GPS alignment fit and scored against a baseline computed over real-real pairs
only, so an impostor cannot dilute the baseline it is judged against; the bench shows a verdict
per impostor (`rejected` ≥5× the real error, `registered` ≤2×, and `no-matches` under 100
correspondences — which is *not* a pass, since nothing had to be rejected). Use
`params.pairs = "complete"` for a full-strength test: with the default sliding-window pairing an
appended impostor only meets the tail of the cluster.

```bash
curl -s -X POST localhost:8070/api/recon/runs -H 'Content-Type: application/json' \
  -d '{"name":"doppelganger","lat":50.11693,"lon":14.48842,"radius_m":60,"limit":8,
       "after":"2026-06-15 18:35:10","before":"2026-06-15 18:35:27",
       "inject":["f05f60ee-6747-4854-8494-2e4ac975502f"],
       "params":{"dense":true,"pairs":"complete","mask_anon":true}}' | jq
```

```bash
# compute the metrics first (per run dir; writes metrics.json beside metadata.json)
cd ../scripts/enrich
systemd-run --user --scope -p MemoryMax=12G -- .venv/bin/python recon_metrics.py runs/walk_dense
.venv/bin/python recon_metrics.py --self-test              # validates the metric itself
.venv/bin/python recon_metrics.py --compare runs/*/        # cross-run table

# runs predating July 2026 need their intrinsics recovered first (scene.npz did not save
# principal points, and guessing them at the image centre inflates the metric ~5x)
systemd-run --user --scope -p MemoryMax=16G -- .venv/bin/python recon_resolve.py runs/walk_dense

# then import into the bench (idempotent — re-run after recomputing metrics)
curl -s -X POST localhost:8070/api/recon/import -H 'Content-Type: application/json' -d '{}' | jq
curl -s localhost:8070/api/recon/runs | jq '.runs[] | {name, metrics: .metrics.reproj_px.median}'
```

## Data model in one breath

Postgres holds **mirrors** (`photo_mirror`, `annotation_mirror` — append + non-destructive
reconcile; rows are never deleted, only `missing_since`-stamped) and **runs**. Oxigraph holds
**facts**: each fact triple sits alone in a content-addressed named graph
(`https://rdf.hillview.cz/id/fact/{sha256[:16]}`), the meta graph links fact→run
(`prov:wasGeneratedBy`) and fact→annotation (`hv:about`), and the curation graph carries
`hv:status` decisions about fact-graph URIs. Same fact re-emitted ⇒ same URI ⇒ curation
survives re-runs. No RDF-star, no blank nodes. **Identifiers live under `rdf.hillview.cz`**
(distinct from web addresses; the subdomain can later serve an RDF viewer) — web pages are
referenced explicitly via `hv:webPage`/`hv:wikipediaPage`. Vocabulary:
[`vocab/hv.ttl`](vocab/hv.ttl).

## OOM protection (don't remove)

Layered: (1) **earlyoom** system service (`/etc/default/earlyoom`) — thresholds tuned for
the box's generous 29G swap (`-m 8,4 -s 95,80`) so it kills the fattest *preferred* process
(python/node/bun — all auto-restarting) within minutes of real memory pressure instead of
letting the box thrash for days; avoids infra + the claude agent. (2) every container in
this stack and the main stack carries `mem_limit`. (3) the matcher worker runs in a systemd
unit with `MemoryHigh=8G / MemoryMax=10G` (`matcher/run_worker.sh`) plus an in-process
`ram_gate()` that fails jobs visibly instead of blocking. Ad-hoc heavy work should follow
suit: `systemd-run --user --scope -p MemoryMax=<N>G …`. Tested live: a 20 GB hog was
SIGTERMed by earlyoom at the threshold with zero collateral.

**After a reboot:** docker brings both stacks back (restart policies); the one manual step
is the matcher: `matcher/run_worker.sh`. Queued match jobs wait in RabbitMQ meanwhile.

**Web dev loop:** the UI normally runs as the `enrich_web` container (production build).
To iterate: `docker stop enrich_web`, then `bun run dev` in `web/`; restart the container
when done (`docker compose up -d web` — rebuild with `--build` to ship UI changes).

## Notes / caveats

- The sync reader uses the dev credentials with `default_transaction_read_only=on`; a real
  read-only role is the prod step (see design doc M5). If the main stack's postgres ever
  moves to `network_mode: host`, point `HILLVIEW_DB_URL` at the host instead.
- Queue: none yet by decision — M0/M1 runs execute in-process. M3 adopts Remoulade
  (reference incl. untrusted-workers: `~/repos/koo5/accounts-assessor`).
- The older inspector (`scripts/enrich/viz_app.py`, :8765) and its reports stay untouched
  as the bridge until benches absorb them.
