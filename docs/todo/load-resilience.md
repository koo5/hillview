# Load resilience: the API under stress, and a test suite that does not flake

## Context

Two full Playwright runs on 2026-10-25 and 2026-10-30 ran while the host was
loaded (load average 30–40; a QEMU VM at ~6 cores, virtiofs and a recon worker
competing for the disk). The first run lost 5 tests, the second 17. In both,
almost every failure was the same shape: the test died at login or at a photo
upload, before the thing it tests ran, because an API request took tens of
seconds or never answered. Only the `api`, `caddy` and `postgres` containers
are involved on the server side; Caddy was never the slow part.

The measurements that matter, all from the API's own request log in one
loaded window (times are server-side, so the browser is ruled out):

| step | normal | loaded |
|---|---|---|
| bcrypt password check in `authenticate_user` (sync, on the event loop) | 0.2 s | 0.2 s |
| audit-row commit in `SecurityAuditService.log_event`, inside the login route | ms | 24.3 s |
| `POST /api/debug/recreate-test-users` | 0.9 s | 38 s |
| `POST /api/debug/clear-database` | 0.02 s | 66 s |

The login route logged "Authentication successful", then nothing for 24 s,
then "Security Event: login_success". The only thing between those lines is
the audit insert and its `commit()`. Postgres logged `checkpoint starting`
in that gap. `pg_stat_activity` showed one active and four idle connections,
so the pool (`POOL_SIZE` / `MAX_OVERFLOW` in `backend/common/database.py`)
was nowhere near exhausted, and the API process itself was idle.

Conclusion: under host load the API is not CPU-bound and not pool-starved.
It waits on Postgres commits, and Postgres waits on a disk that other
workloads own. Every downstream symptom follows from that single wait:
the token POST taking 20–40 s, `register-client-key` never answering, the
web client then reporting "Login failed" with correct credentials
(`completeAuthentication` aborts the login when key registration fails),
photo processing exceeding the 30 s test cap, the Mapillary stream going
silent for 60 s.

Two things in the 2026-10-30 run were real bugs rather than load, both
fixed the same day: a foreign-key race in `clear_mapillary_cache_tables`
between its two deletes and the Mapillary cache writer (now a `LOCK TABLE`
for the transaction), and a console error from `simplePhotoWorker` when the
session ends while it asks for a token. One failure stays unexplained: the
WebKit "cancel a label edit" spec clicked Save, `saveEditBody` logged, the
API was healthy, and no request ever left the browser. It passed on rerun.

## The API under stress

Ordered by leverage over risk.

**Stop paying fsync on every commit in dev and test.** Set
`synchronous_commit = off` on the dev Postgres. A crash then loses at most
the last second of commits, which is nothing for a database the suite wipes
fifty times an hour. Every commit stops waiting for the disk, which is the
24 s above. Raise `max_wal_size` (currently 1 GB) so checkpoints come less
often, and set `log_min_duration_statement` to about one second so the next
slow commit shows up in the Postgres log by itself instead of needing a
trace dig. Production keeps `synchronous_commit = on`; if the audit writes
turn out to dominate there too, `SET LOCAL synchronous_commit TO off` on
just those sessions is the targeted version.

**Take best-effort writes off the request path.** `log_successful_login`
inserts and commits an audit row before the token response is sent. A login
should never wait on a log line: hand the audit write to a background task
(FastAPI `BackgroundTasks`, or a small queue drained by one task) and keep
the request path to the writes that decide the outcome. Audit the other
routes for the same pattern — anything that is recording rather than
deciding belongs in the background.

**Keep the single event loop unblocked.** `verify_password` and
`hash_password` in `backend/common/auth_utils.py` are synchronous bcrypt
calls made from async handlers; `cleanup_upload_directories` in
`debug_utils.py` walks and `rmtree`s upload directories synchronously.
On a healthy machine that is a few hundred milliseconds. On a starved one
it is seconds during which every other request on the loop queues behind
it, which is how a `register-client-key` that normally takes 10 ms "never
answers". Wrap them in `anyio.to_thread.run_sync`, as photo artifact
deletion in `photos.py` already is. The alternative, several uvicorn
workers, is closed off while `AuthRateLimiter` and the OAuth nonce state
live in process memory (prod deliberately runs one worker for the same
reason), so the one loop has to stay clean.

**Give the stack priority over the neighbours.** Nothing in
`docker-compose.yml` reserves CPU or IO for `postgres` and `api`. Either
`cpu_shares` / `cpus` on those two services, or renicing the VM and the
recon worker, addresses the actual contention instead of working around
it. Cheap, and it also makes the dev experience less dependent on what else
the box is doing.

**Observe it, don't infer it.** The request log already prints durations,
which is what made this diagnosis possible. Add a warning when a commit
exceeds a threshold (a SQLAlchemy `after_commit`/`before_commit` timing, or
just the Postgres slow-statement log above) so the next incident reads
"slow commit" in one line rather than a trace reconstruction.

## A test suite that does not flake

**The suite is its own worst load source.** Fifty `clear-database` calls and
a `recreate-test-users` per spec file in a twenty-minute window is heavy
write churn, and that churn triggers the checkpoints that stall the logins.
Isolating spec files with unique users and leaving the rest of the data
alone would remove most of the writes the suite generates for itself.
The backend integration tests have the same tension with the shared dev
database.

**Report "backend stalled" instead of "test failed".** A global `beforeEach`
that times one request to `/api/debug` and, above a couple of seconds, skips
the test with that reason (`test.skip(true, 'backend stalled: 4.1 s')`)
turns infrastructure failures into a separate, labelled count. That is more
honest than the `@stress` tag added on 2026-10-30, which only records where
earlier failures happened to land: a loaded machine fails whichever test
logs in next, not a fixed set.

**Retry once locally.** `retries` is `2` on CI and `0` otherwise in
`tests-playwright/playwright.config.ts`. One local retry with
`trace: 'on-first-retry'` (already configured) would have absorbed every
login-stall failure in both runs and left a trace for the genuine ones.

**Scale every wait, not most.** `waitForPhotoProcessing` in
`helpers/photoUpload.ts` defaults to a bare 30 s and ignores `T()`, so it
is the one wait that does not widen with `PW_TIMEOUT_MULT`. While there,
the config could derive the multiplier from `os.loadavg()` at startup
instead of relying on the person running the suite to remember the knob.

**Do not fail a login because key registration stalled.**
`completeAuthentication` in `auth.svelte.ts` aborts the whole login when
`registerClientPublicKey` throws, mirroring Kotlin. Under load the token
POST succeeded in 259 ms and the key POST hung, and the user-facing result
was "Login failed. Please check your credentials." A bounded retry on the
registration, with the login treated as complete once the token is stored,
is what a real user on a bad connection needs too; photo sync already waits
for the key through the auth generation, so the ordering it protects is
kept.

**Keep the stale-token forensics recipe.** The unresolved Firefox and
WebKit cases were only diagnosable because the run had `--trace on`: the
`.network` rows with status -1 are the requests still pending, the
`screencast-frame` entries show the page at any moment, and the API log's
per-request durations say which side was slow.

## Decisions and state (2026-10-30)

Done:

- The Postgres commit, WAL and checkpoint knobs are env vars on the
  `postgres` service (docker-compose.yml, `.env.example`), each defaulting to
  the Postgres default: `synchronous_commit`, `fsync`, `full_page_writes`,
  `wal_writer_delay`, `commit_delay`, `max_wal_size`, `checkpoint_timeout`,
  `checkpoint_completion_target`, `log_min_duration_statement`. The main dev
  box runs `POSTGRES_SYNCHRONOUS_COMMIT=off` and nothing else, because its
  database holds the prod dump. dev4-3, whose database is throwaway test
  data, also runs `fsync=off` and `full_page_writes=off`. Those do not shorten
  a commit any further, but they remove the flush storm at each checkpoint
  and the burst of full-page images after it, which is the IO a contended
  disk chokes on. The price is that an OS or host crash (not a Postgres or
  container crash) can corrupt the cluster.
- `verify_password` and `get_password_hash` now run via `asyncio.to_thread`
  at their three call sites (`authenticate_user`, `register_user`,
  recreate-test-users), so bcrypt no longer blocks the event loop.
- "slow commit" warning in `backend/common/database.py`: a `before_commit` /
  `after_commit` pair on `Session` logs any commit over `DB_SLOW_COMMIT_MS`
  (default 1000).
- `waitForPhotoProcessing` default is `T(30000)` like its sibling waits.
- Login no longer fails over client key registration. `completeAuthentication`
  returns once the tokens are stored and starts the registration in the
  background (`frontend/src/lib/clientKeyRegistration.ts`). A consumer that
  cannot heal a missing key awaits `ensureClientKeyRegistered()`. Uploads
  only kick it without waiting (a review on 2026-10-30 found that awaiting let
  a stalled registration hold every photo about a minute and then fail it).
  `requestUploadAuthorization` heals a 409
  `client_key_not_registered` by re-registering and retrying once, the same
  contract Kotlin's `PhotoUploadLogic` uses, which also covers the service
  worker (no access to the main thread's state) and a server that lost the
  key. The login page no longer says "check your credentials" for a failure
  after the token exchange.

  Retries: a registration run retries network failures and 5xx on a doubling
  delay (1, 2, 4, 8, 16, 32 s), then gives up and waits to be re-kicked by the
  next consumer or by connectivity returning (`onReconnect`). A 4xx other than
  409 is a wrong request and is not retried; a session ending stops the run.
  Deferring registration entirely to the first request that needs the key was
  checked and rejected: the key has several consumers (upload authorize and
  finalize, push-token ownership on Android), each checking it separately and
  not all surfacing a missing key the same way. Photo streams were briefly a
  fourth, through the planned signed stream credential; since 2026-10-30 they
  send the access token in an Authorization header instead
  (docs/todo/stream-auth-client-signed-credential-todo.md).

Declined or deferred:

- The debug cleanup sweep stays synchronous: it is debug-only, and tests are
  sequenced after it, not run concurrently with it.
- Audit writes stay on the request path for now.
- No skipping of tests under load, and no wait scaling from system load —
  load average does not track IO load anyway. Where a wait is too stiff,
  make it more generous outright.
- One local retry: maybe; not done.

## Suggested order

Postgres `synchronous_commit` and the background audit write first: most
leverage, least risk, both measurable against the same log lines. Then the
event-loop hygiene (bcrypt in threads, done), the local retry, then the
per-file user isolation once there is a free afternoon, since it touches
every spec's fixture.
