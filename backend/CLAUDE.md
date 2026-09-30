# Hillview backend

FastAPI + PostgreSQL/PostGIS. A uv workspace (`pyproject.toml`) with members
`common/`, `api/app/`, `worker/`, `tests/` and `panoramax/`; `analyzer/` has
its own lock. Dependencies change through `scripts/deps.py` at the repo root.

## Docs

- **[Database Migrations Guide](../docs/database-migrations.md)**: Complete workflow for managing database schema changes with Alembic
- **[PostgreSQL Alpine Migration](../docs/postgres-alpine-migration.md)**: why the postgres image moved to the alpine tag + ICU collation, the dump/restore procedure, and `backend/scripts/pg_rehearse_alpine.py` to prove it on a throwaway cluster first
- **[DB sessions and cancellation](../docs/db-session-cancellation.md)**: why a request cancelled mid-statement used to leave its connection "idle in transaction" forever (asyncpg `Protocol.abort()` is a no-op after an interrupted close), the Pool "invalidate" terminate + shielded `release_session` fix, the anyio-not-asyncio repro gotcha, how to spot and clear a wedge, and the rule for what a transaction may span
- **[SSR auth ticket](../docs/ssr-auth-ticket.md)**: how the web server renders a signed-in visitor's own view — the read-only `ssr_read` token, the `hv_ssr` cookie the browser mirrors it into, the two allowlisted backend dependencies, `viewer_id` + `createSsrBackedLoad`, the `SSR_AUTH` runtime switch
- **[Native Android Auth](../docs/native-auth.md)**: Credential Manager + Google ID-token login — concepts, security reasoning, and where everything lives
- **[Panoramax Federation](../docs/panoramax-federation.md)**: The `backend/panoramax/` read API + sequencer serving CC photos to the Panoramax federation (harvester contract, deployment, registration)
- **[Photo analyzer revival](../docs/photo-analyzer-revival.md)**: the LLM photo-analysis service — where its data actually lives (`/shared/analyzer_data` vs the stale docker volume), why there is no pending migration, why coverage is the inverse of what 3-D work needs, and what to point it at instead
- **[Photo upload workflow](../docs/photo-upload-workflow.md)**: the whole upload flow across the Android client, the API and the worker — states, transitions, error handling, known edge cases (written 2026-02; check it against the code)
- **[Push notifications](../docs/push-notifications.md)**: what the backend sends (`push_notifications.py`), how Android displays it, and the knobs that control both
- **[Stream auth credential TODO](../docs/stream-auth-client-signed-credential-todo.md)**: replacing `?token=<access_token>` on stream endpoints with a client-signed credential — backend done, client wiring pending
- **[Config-permutation testing](../docs/config-testing-and-runtime-overrides.md)**: design notes, not implemented, for testing prod/dev differences — rate limits, debug gates, worker deployment modes
- **[Timestamp archeology](../docs/timestamp_archeology.md)**: why Canon and phone photos landed on two `captured_at` time scales, and the one-shot fix — read before re-running an old backfill

## Running

The compose files are at the repo root, not here; `compose.sh` is the dev wrapper:

```bash
../compose.sh up --build --remove-orphans -d api
curl http://localhost:8055/api/debug     # health
curl http://10.0.2.2:8055/api/debug      # the same, from the Android emulator
```

Swagger UI is at `http://localhost:8055/docs` — outside the `/api` prefix.

## Tests

```bash
./run_tests.sh                               # everything: api unit, worker unit, integration
./api/run_unit_tests.sh                      # api unit tests; paths are relative to api/app
./api/run_unit_tests.sh tests/unit/test_photo_ratings.py -v
./worker/run_unit_tests.sh                   # worker unit tests
./tests/run_integration_tests.sh             # integration tests, against the running stack
./tests/run_integration_tests.sh integration/test_content_filtering.py -v
./tests/run_integration_tests.sh integration/test_user_profile.py::TestAccountDeletion::test_delete_account_cascades_photos -v -s
```

Each script `uv sync`s its own workspace package first. Integration tests talk
to the live API (`API_URL`, default `http://localhost:8055/api`) and share the
dev database with whatever else is in it, so a test that asserts on global
state clears the database itself (`clear_test_database` in `tests/utils/test_utils.py`).

## Debug CLI

```bash
./debug.sh                 # prints every command
./debug.sh recreate        # recreate the test users
./debug.sh photos          # the test user's photos, with error details
./debug.sh photo <id>      # one photo in detail
./debug.sh cleanup         # delete the test user's photos
./debug.sh upload-files --license <id> <files…>
```

It runs from `backend/.venv` and never syncs it; materialize it once with
`uv sync --frozen --package hillview-tests`. The logic lives in
`tests/utils/debug_utils.py`, on top of `tests/utils/api_client.py`.

### Test users

Defined once in `common/test_users.py`; the server only creates them when
`TEST_USERS` / `DEBUG_ENDPOINTS` are enabled.

- `test` / `StrongTestPassword123!`
- `admin` / `StrongAdminPassword123!`
- `testuser` / `StrongTestUserPassword123!`
- `moderator` / `StrongModeratorPassword123!`

```bash
curl -X POST http://localhost:8055/api/auth/token \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d 'username=test&password=StrongTestPassword123!'

curl -H "Authorization: Bearer <jwt_token>" http://localhost:8055/api/photos
```

## Database

```bash
docker exec -it hillview_postgres sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB"'
```

### Migrations

**📖 See [Database Migrations Guide](../docs/database-migrations.md) for complete documentation.**

Quick reference using the migration script:
```bash
# Check migration status
./scripts/migrate.sh current

# Apply all pending migrations  
./scripts/migrate.sh upgrade head

# Create new migration after model changes
./scripts/migrate.sh revision --autogenerate -m "Description of changes"

# View migration history
./scripts/migrate.sh history
```

The migration script (`./scripts/migrate.sh`) automatically handles:
- Environment variable loading from `.env`
- Docker container networking and volume mounting
- Python path configuration
- Async/sync engine compatibility

## Layout

```
backend/
├── api/app/       # the FastAPI app: api.py registers the *_routes.py routers; alembic/
├── common/        # shared by api and worker: models.py, database.py, config.py, jwt_utils.py
├── worker/        # photo processing service: photo_processor.py, anonymize.py
├── panoramax/     # Panoramax federation read API
├── analyzer/      # LLM photo analysis service
├── tests/         # integration tests; utils/ holds the api client and debug CLI
└── scripts/       # migrate.sh, one-shot backfills and repairs
```

### Import Conventions
- Modules in `api/app/` use relative imports for sibling modules: `from dsl_utils import y`
- Shared modules use `common.` prefix: `from common.models import Photo`

### Database access
- All database operations are async, through SQLAlchemy `AsyncSession` injected as a dependency
- PostGIS is required for the spatial queries
- What a transaction may span: see [DB sessions and cancellation](../docs/db-session-cancellation.md)

## Configuration

The API loads `.env` from its working directory, which is `api/app/.env` —
dev and prod alike.

- `DATABASE_URL` - PostgreSQL connection string
- `JWT_PRIVATE_KEY` / `JWT_PUBLIC_KEY` - the ES256 token signing keys (`common/jwt_utils.py`); `SECRET_KEY` is still read by `auth.py` but signs nothing
- `ACCESS_TOKEN_EXPIRE_MINUTES` - access token lifetime, default 100
- `MAPILLARY_CLIENT_TOKEN_FILE` - Path to Mapillary API token
- OAuth credentials for Google/GitHub (`*_CLIENT_ID`, `*_CLIENT_SECRET`, `*_REDIRECT_URI`)
- `USER_ACCOUNTS` - gates the user and photo routes
- `DEBUG_ENDPOINTS` / `DEV_MODE`, `TEST_USERS` - debug routes and the fixed test users
- `ENABLE_MAPILLARY_CACHE` - Set to "true", "1", or "yes" to enable caching (disabled by default)
- `GEOIP_DB_PATH` - Path to MaxMind GeoLite2-City.mmdb (default `/app/data/GeoLite2-City.mmdb`). Used by the `/api/featured/nearest` endpoint to geolocate first-visit clients.

CORS origins are a fixed list, `get_cors_origins` in `common/config.py`.

### OAuth
- **Providers**: Google and GitHub OAuth2
- **Callback URLs**: Must include both web and mobile redirect URIs
- **Deep Links**: Mobile OAuth returns via `cz.hillview://auth` (`cz.hillviedev://auth` in dev builds)
- **Security**: Device registration required for private IP OAuth testing

### Storage Pools (`FILE_POOLS`)

Processed photos live in storage **pools**, defined by `FILE_POOLS` — a JSON array read by the API (`common/config.py`). Each entry is a pool keyed by its public base URL:

- **files pool**: `{"type":"files","url":"https://pics.hillview.cz/","path":"/app/pics"}`
- **cdn pool**: `{"type":"cdn","url":"https://cdn/","bucket":"b","endpoint":"https://s3","secrets_file":"/run/secrets/cdn","addressing_style":"virtual"}`

How it's used:

- **Writes**: when the worker is built with CDN off, it streams files to the API's `/photos/upload-file`, which writes them to the **first `files`-type pool** and returns the public URL (the worker no longer assumes a single `PICS_URL`). When the worker is built with CDN on, it uploads to its env-configured CDN directly.
- **Deletes**: each photo size's pool is resolved independently from its stored URL (longest base-URL prefix wins), so a photo's variants may span pools. DZI pyramids are deleted too — the `.dzi` descriptor and the `_files/` tile tree (`shutil.rmtree` for files pools, an S3 prefix sweep for cdn pools).
- **Adding a disk**: serve it (e.g. Caddy at `pics2.hillview.cz`) and **prepend** it as a files pool — new uploads go there, old photos stay deletable on the previous pool.
- **Fallback**: when `FILE_POOLS` is unset, the registry is synthesised from `PICS_URL`/`PICS_DIR` plus the CDN env (`CDN_BASE_URL`/`BUCKET_NAME`/`AWS_ENDPOINT_URL_S3`) if configured — so existing deployments need no new config.

**cdn credentials**: supplied via the pool's `secrets_file`, a JSON file (mount as a docker secret) containing `{"access_key_id":"...","secret_access_key":"..."}`. Use `"addressing_style":"path"` for self-hosted S3 servers (MinIO/Garage/SeaweedFS); the default `"virtual"` suits hosted providers like Tigris. Multiple cdn pools are supported (e.g. a legacy CDN kept for deletes alongside a new write CDN).

### Featured Photo GeoLite2 Database Setup

The `/api/featured/nearest` endpoint geolocates the client's IP on first visit and returns the nearest well-annotated photo so new visitors immediately land on an interesting view. IP → location lookup uses MaxMind's free **GeoLite2-City** database (not bundled — operator-provided).

1. Create a free MaxMind account at https://www.maxmind.com/en/geolite2/signup
2. Download **GeoLite2-City.mmdb** (binary format, not CSV)
3. Mount it into the api container. Either:
   - Add a docker-compose volume entry:
     ```yaml
     api:
       volumes:
         - ./backend/data/GeoLite2-City.mmdb:/app/data/GeoLite2-City.mmdb:ro
     ```
   - Or set `GEOIP_DB_PATH` to a different location and mount accordingly.

**Graceful degradation**: If the database is missing, unreadable, or the client IP is private/unresolvable, the endpoint falls back to returning the globally best-annotated photo. No setup is strictly required — it just gives a less location-relevant experience.

## Mapillary Caching

### Schema
- **CachedRegion**: Stores bounding box polygons of cached areas with completion status
- **MapillaryPhotoCache**: Stores individual Mapillary photos with PostGIS Point geometry
- Spatial indexes (GIST) on geometry columns for efficient spatial queries
- Pagination cursor tracking for incremental cache population

### Behaviour
- **Immediate Response**: Returns cached photos instantly from PostGIS spatial queries
- **Smart Region Detection**: Uses PostGIS to calculate uncached areas within requested bbox
- **Background Population**: Asynchronously fetches and caches missing data using Mapillary pagination
- **Spatial Optimization**: Leverages PostGIS `ST_Within`, `ST_Intersects` for efficient geometry operations
- **Rate Limiting**: Maintains existing rate limiting while reducing API calls through caching
