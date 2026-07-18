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
# mirror the dev data (append = new rows; reconcile = changes + missing-stamps)
curl -s -X POST localhost:8070/api/sync/run -H 'Content-Type: application/json' -d '{"mode":"append"}'
curl -s -X POST localhost:8070/api/sync/run -H 'Content-Type: application/json' -d '{"mode":"reconcile"}'
curl -s localhost:8070/api/sync/status | jq
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
