# Hillview

Photo mapping app: photos with position and bearing, browsed on a map, on the
web and as an Android app. Each area has its own CLAUDE.md with its commands,
conventions and the docs worth reading there — this file only holds what is
true everywhere.

## Layout

- `frontend/` — SvelteKit + Tauri v2: the web app and the current Android app → `frontend/CLAUDE.md`
- `frontend2/` — the KMP/Compose rewrite of the Android app → `frontend2/CLAUDE.md`
- `shared-kt/` — Kotlin compiled as source into both Android apps → `shared-kt/CLAUDE.md`
- `shared/` — Svelte/TS modules (`$zoomview`, `$terrain`) used by both `frontend/` and `enrich/web`
- `backend/` — FastAPI + PostgreSQL/PostGIS: api, photo worker, Panoramax federation, analyzer → `backend/CLAUDE.md`
- `enrich/` — the enrichment workbench: terrain renders, matching, 3-D reconstruction → `enrich/CLAUDE.md`
- `scripts/` — repo-wide tooling: dependencies, pano pipeline, EXIF backfill, geotagging
- `docs/` — design docs, runbooks and field notes; each area's CLAUDE.md points at its own. `docs/todo/` holds parked plans
- `docker-compose.yml` + `docker-compose.dev.yml`, `docker/`, `caddy/` — the stack

## Running the stack

The compose files live at the repo root, not in `backend/`. `compose.sh` is the
dev wrapper — it pins the env-file order and the dev overlay, which are easy to
get wrong by hand:

```bash
./compose.sh up --build --remove-orphans -d api
curl http://localhost:8055/api/debug
```

Then the frontend, from `frontend/`. Test credentials are in `backend/CLAUDE.md`.

## Rules that hold everywhere

- **[One state](docs/one-state.md)**: one user-facing location/orientation state, written and read by everything, with no direct hardware side-channels. The load-bearing architectural rule of both apps — read it before touching position or heading.
- **Never delete commented-out code** — preserve it in edits, the user keeps it for reference.
- Always use well-scoped `data-testid` attributes, following the project's style.
- **Dependencies** go through `scripts/deps.py`, with its 14-day cooloff (see the script's docstring):
  ```bash
  scripts/deps.py audit                      # every lockfile
  scripts/deps.py backend pillow==12.3.0     # or --all; cargo / frontend subcommands likewise
  ```

@STRUCTURAL_TOOLS.md
