# Hillview – Copilot Coding Agent Instructions

## Project Summary

Hillview is a full-stack photo-mapping application. Users upload geotagged photos that are displayed on an interactive map. The project has three main parts: a FastAPI/PostgreSQL backend, a SvelteKit + Tauri v2 frontend (web + Android), and an Android app built with Tauri's WebView.

## Repository Layout

```
/
├── backend/               # FastAPI + PostgreSQL API
│   ├── api/app/           # Core FastAPI app (api.py, auth.py, photo_routes.py, user_routes.py)
│   ├── common/            # Shared models, database config, config.py
│   ├── worker/            # Photo-processing worker (EXIF, thumbnails)
│   ├── tests/             # pytest integration & unit tests
│   ├── scripts/migrate.sh # Alembic migration runner
│   ├── pyproject.toml     # uv workspace (Python ≥ 3.12, ruff linter)
│   └── docker-compose.yml # Docker services
├── frontend/              # SvelteKit + Tauri v2 Android app
│   ├── src/               # Svelte source (routes, components, stores)
│   ├── src-tauri/         # Tauri Rust layer & Android config
│   ├── test/specs/        # WebDriverIO/Appium Android tests
│   ├── tests-playwright/  # Playwright web tests
│   ├── package.json       # Bun scripts
│   └── .github/workflows/ci.yml  # Frontend CI pipeline
├── docs/                  # Project documentation (database-migrations.md)
├── CLAUDE.md              # Detailed project instructions (read this for full context)
└── docker-compose.yml     # Root-level Docker Compose
```

## Backend – Build, Test & Lint

All commands run from the **`backend/`** directory unless stated otherwise.

```bash
# Start all services (preferred – also starts PostgreSQL + PostGIS)
docker compose up --build --remove-orphans -d api

# Verify backend health
curl http://localhost:8055/api/debug

# Run full test suite (sets up environment automatically)
./tests/run_tests.sh

# Run specific integration tests
./tests/run_integration_tests.sh integration/test_content_filtering.py -v

# Run unit tests
./api/app/run_unit_tests.sh tests/unit/test_photo_ratings.py -v

# Lint (ruff, configured in pyproject.toml – excludes alembic versions)
pip install ruff && ruff check .

# Database migrations
./scripts/migrate.sh upgrade head       # apply pending
./scripts/migrate.sh current            # check status
./scripts/migrate.sh revision --autogenerate -m "description"  # new migration
```

**Requirements**: Python ≥ 3.12, PostgreSQL with PostGIS extension, Docker.  
**Import conventions**: modules inside `api/app/` use relative imports (`from dsl_utils import y`); shared modules use `from common.models import ...`.

## Frontend – Build, Test & Lint

All commands run from the **`frontend/`** directory.

```bash
# Install dependencies (always run first)
bun install

# Start dev server (web)
bun run dev                    # port 8212 by default

# Type-check (svelte-check + tsc)
bun run check

# Build for production
bun run build

# Unit tests (Vitest)
bun run test:unit

# Playwright web tests
bun run test:playwright

# Android integration tests (requires emulator + backend running)
bun run test:appium
bun run test:appium:test0      # fastest: single optimised test
bun run test:appium:fast       # skip app clear

# Full CI validation (mirrors CI pipeline)
bun run validate               # with Android
bun run validate:quick         # skip Android
```

**CI pipeline** (`frontend/.github/workflows/ci.yml`) runs on PRs to `main`/`master`/`develop`:
1. `bun install` → `bun run check` → `bun run build` → `bun run test:unit`
2. Android emulator tests (macOS runner, API 29)

## Key Configuration Files

| File | Purpose |
|---|---|
| `backend/pyproject.toml` | uv workspace, ruff linter config |
| `backend/api/app/requirements.txt` | App Python deps |
| `frontend/package.json` | All frontend scripts |
| `frontend/tsconfig.json` | TypeScript config |
| `frontend/svelte.config.js` | SvelteKit adapter (node/static) |
| `frontend/vite.config.ts` | Vite build config |
| `frontend/wdio.conf.ts` | WebDriverIO / Appium test config |
| `frontend/src-tauri/tauri.conf.json` | Tauri production config |
| `frontend/src-tauri/tauri.android-dev.conf.json` | Tauri Android dev config |

## Architecture Notes

- **Database**: PostgreSQL + PostGIS; all DB operations are async (SQLAlchemy `AsyncSession`).
- **Auth**: JWT (30-min expiry) + OAuth2 (Google, GitHub). Mobile OAuth returns via deep link `cz.hillview://auth`.
- **Android packages**: `cz.hillviedev` (dev), `cz.hillview` (prod). Dev builds use `./scripts/android/dev.sh`.
- **Emulator networking**: `localhost` → `10.0.2.2`; set `VITE_BACKEND_ANDROID` env var for emulator builds.
- **Photo processing**: Async worker extracts EXIF (GPS, compass angle), generates thumbnails.
- **Mapillary**: Optional caching layer; enable with `ENABLE_MAPILLARY_CACHE=true`.

## Test Credentials (development only)

- `test` / `StrongTestPassword123!`  
- `admin` / `StrongAdminPassword123!`  
- `testuser` / `StrongTestUserPassword123!`

Run `./debug.sh recreate` (from `backend/`) to recreate test users.

## Common Pitfalls

- Always run `bun install` before any `bun run *` frontend command.
- Always start the backend (`docker compose up -d api`) before Android integration tests.
- Never delete commented-out code – the project owner keeps it for reference.
- Always use well-scoped `data-testid` attributes for new UI elements.
- Android tests use `retries: 0` and `bail: 1`; the first failure stops the suite.
- `"error sending request"` in Android tests = backend unreachable from emulator.
