# Database sessions, cancellation, and the stranded-transaction wedge

How a request that gets cancelled mid-flight can leave its database connection
open and "idle in transaction" forever, why the obvious guard against it does
not work, what `common/database.py` does about it, and the rule for sessions
and transactions that keeps it from coming back through a different door.

## What it looked like

A Playwright run in September 2026 took 5.1 hours instead of 1.8 and failed 20
Mapillary specs. Every one of them was a `POST /api/debug/clear-database` that
never returned, burning the full per-test timeout. In `pg_stat_activity` the
picture was one abandoned session and a queue behind it:

```
idle in transaction  21h54m  UPDATE cached_regions SET last_updated=…   <- head of line
active, Lock                 DELETE FROM cached_regions   blocked by the one above
active, Lock                 DELETE FROM cached_regions   blocked by the one above that
…                            25 deep, one per hung test, nine minutes apart
```

`clear_database` in `debug_routes.py` runs `DELETE FROM cached_regions`, so it
queued behind the abandoned transaction's row lock, and so did every call after
it. The connection pool filled up with the waiters, which stalled unrelated
endpoints too, and `uvicorn --reload` could no longer restart: it waits for
in-flight requests, and those requests were waiting on the lock. A code edit
during that state silently takes the dev API down.

The abandoned session belonged to the Mapillary SSE stream's cache writer. The
stream had been cancelled by the client going away, mid-statement.

## Why a cancelled request strands its transaction

None of this is Mapillary-specific. Any request cancelled while a statement is
in flight used to do it. The chain, traced against asyncpg 0.30.0 and
SQLAlchemy 2.0.36:

- The client disconnects. Starlette cancels the handler through an anyio cancel
  scope. Inside a cancelled scope **every await raises `CancelledError` at
  once**, not just the first one — this is the property that defeats every
  naive cleanup.
- The `CancelledError` surfaces inside `db.execute`. SQLAlchemy treats a
  `BaseException` during a statement as "connection state unknown" and
  invalidates the connection, then closes it through the asyncpg adapter's
  `terminate()`.
- That adapter tries to be polite first: `await conn.close(timeout=2)`. asyncpg's
  `Protocol.close()` sets `closing = True`, sends a cancel request for the
  running statement over a side connection, and awaits it.
- The cancelled scope interrupts that await. asyncpg's `Connection.close()`
  catches it and falls back to `_abort()`, which calls `Protocol.abort()` — and
  `Protocol.abort()` begins with `if self.closing: return`. It is a no-op after
  an interrupted close. The transport is never aborted. `_cleanup()` then cancels
  the pending cancel request as well.

Net effect: no cancel reaches the server, no `ROLLBACK` is ever sent, and the
socket stays `ESTABLISHED` with nothing referencing it. The server finishes the
statement and waits for its client indefinitely, holding every lock the
transaction took.

It also explains why the earlier guard in `cache_photos` in `cache_service.py` —
`except BaseException: await self.db.rollback()` — never helped: its rollback is
one more await inside the same cancelled scope, so it raises before reaching the
socket. Any cleanup that awaits without a shield has the same problem.

## The bug, in detail

Versions: asyncpg 0.30.0, SQLAlchemy 2.0.36, anyio 4.x, Starlette 1.3 / FastAPI
0.141. The guard that makes it a no-op is unchanged on asyncpg's master branch as
of September 2026. `backend/scripts/repro_asyncpg_cancel_strand.py` reproduces it
against any Postgres with nothing but SQLAlchemy, asyncpg and anyio, and prints
both the broken and the worked-around outcome side by side:

```
without workaround: backend state='idle in transaction'    client socket=ESTAB
with workaround:    backend state=None                     client socket=gone
```

The chain, with the method names as they appear in the two libraries:

**In SQLAlchemy**, a `BaseException` raised while a statement is executing makes
`Connection._handle_dbapi_exception` invalidate the connection: the pool's
`_ConnectionRecord.invalidate` fires the `"invalidate"` event, then closes the
record with `terminate=True`, which for asyncpg means the adapter's
`AsyncAdapt_asyncpg_connection.terminate`:

```python
def terminate(self):
    if util.concurrency.in_greenlet():
        try:
            # try to gracefully close; see #10717
            self.await_(self._connection.close(timeout=2))
        except (asyncio.TimeoutError, asyncio.CancelledError, OSError,
                self.dbapi.asyncpg.PostgresError):
            self._connection.terminate()
```

The graceful attempt comes first, and it is an await.

**In asyncpg**, `Connection.close()` calls `Protocol.close()`, which is
`async def close(self, timeout)` in `protocol/protocol.pyx`:

```python
if self.closing:
    return
self.closing = True
…
if self.waiter is not None:
    # If there is a query running, cancel it
    self._request_cancel()
    await self.cancel_sent_waiter          # <- the cancelled scope interrupts here
```

`_request_cancel` schedules `Connection._cancel`, a task that opens a second
connection to send the wire-protocol cancel request. Inside a cancelled anyio
scope the `await` raises at once. `Connection.close()` catches
`(Exception, asyncio.CancelledError)`, calls `self._abort()` and re-raises.
`_abort` calls `Protocol.abort()`:

```python
def abort(self):
    if self.closing:
        return
    self.closing = True
    self._handle_waiter_on_connection_lost(None)
    self._terminate()
    self.transport.abort()
    self.transport = None
```

`closing` is already `True` from the interrupted `close()`, so `abort()` returns
on its first line. `self.transport.abort()` never runs. Then `_cleanup()` runs
`_clean_tasks()`, which cancels every pending entry in `self._cancellations` —
including the cancel request that was on its way to the server.

Back in SQLAlchemy, the adapter catches the `CancelledError` and calls
`self._connection.terminate()`, asyncpg's `Connection.terminate()` — but that
begins with `if not self.is_closed()`, and `is_closed()` is true once `_aborted`
was set, so it only runs `_cleanup()` again.

**Observable result**, from tracing every one of those methods and checking the
kernel:

- `Connection._cancel_current_command` ran; `connect_utils._cancel` was entered
  and raised `CancelledError` — the server never received the cancel.
- `Connection._abort` ran; `_SelectorSocketTransport.abort` never did.
- Four seconds later the asyncio transport still had `is_closing() == False`,
  `_conn_lost == 0`, and an open socket; `ss -tan` showed the connection
  `ESTABLISHED`; `pg_stat_activity` showed the backend `idle in transaction`,
  waiting on `Client`, with `select pg_sleep(3)` as its last statement.
- The pool reported zero checked-out connections. Nothing referenced the socket
  any more; it was simply never closed.

Two things about the reproduction are load-bearing. The cancellation has to be an
anyio cancel scope — a bare `task.cancel()` is one-shot, the teardown awaits
succeed, and the connection is released cleanly, which is why the bug hides from
naive tests. And a statement has to be in flight; a request cancelled between
statements takes the milder path through the teardown.

If this is ever reported upstream, the one-line summary is: `Protocol.abort()`
is a no-op after an interrupted `Protocol.close()`, because both set the same
`closing` flag, so a `CancelledError` inside `close()` leaves the transport open
and cancels the in-flight cancel request. SQLAlchemy is a bystander that happens
to call the polite close first.

## The fix

Two pieces, both in `common/database.py`.

**Hard-terminate on invalidate.** A listener on SQLAlchemy's `Pool` class for
the `"invalidate"` event calls the driver connection's own synchronous
`terminate()`. asyncpg's `Connection.terminate()` aborts the transport outright
as long as `closing` is not yet set — and at invalidate time, before the polite
close has started, it is not. This is the change that closes the hole. It lives
on the `Pool` class rather than on one engine because the bug is the driver's:
an engine a script or a test creates for itself gets the same protection.

**A shielded teardown.** `get_db` releases its session through
`release_session`, which runs `close()` inside `anyio.CancelScope(shield=True)`
with a bounded wait, and invalidates the connection if the close does not
finish. This covers the other shape, a cancel that lands *between* statements,
where the old teardown's `except Exception` skipped the rollback (a
`CancelledError` is not an `Exception`) and its `await db.close()` raised before
doing anything. The docstring of `get_db` carries the convention below.

Nothing graceful is lost by terminating on invalidate. An invalidated connection
is unusable by definition, and Postgres rolls the transaction back when the
backend exits.

## Reproducing and testing it

`test_get_db_cancellation` in `api/app/tests/unit/` is the regression test. It
was red against the old code and is green against the new one. Two details in it
are load-bearing:

- **The cancellation must come from an anyio cancel scope**, the way Starlette
  does it. A bare asyncio `task.cancel()` does **not** reproduce the bug: asyncio
  cancellation is one-shot, so the cleanup awaits after the first
  `CancelledError` succeed, and the connection is released cleanly. That is very
  likely why the May 2026 guard looked correct when it was written.
- **A statement must be in flight** when the cancel arrives (`select pg_sleep(3)`
  in the test). A request cancelled while idle between statements is the milder
  shape and does not exercise the driver bug.

It needs the dev postgres, `localhost:25432`, and skips if none is reachable. It
builds its own one-connection `QueuePool` engine, because the unit-test
`conftest.py` forces `NullPool` on the module engine and that masks the failure
mode; the probe that inspects `pg_stat_activity` uses a separate `NullPool`
engine so it cannot be starved by the connection under test.

When something like this needs tracing again, the recipe that worked: wrap
`asyncpg.Connection.close`, `_abort`, `_cleanup`, `terminate` and
`_cancel_current_command` plus `_SelectorSocketTransport.abort` and
`_force_close` with print tracers; read the backend's `client_port` from
`pg_stat_activity` and look for it in `ss -tanp`; inspect the transport's
`is_closing()`, `_conn_lost` and `_sock` afterwards. Those three views together
distinguish "asyncpg thinks it closed" from "the kernel agrees".

## Recognising and clearing a wedge

```sql
select pid, state, wait_event_type, pg_blocking_pids(pid) as blocked_by,
       now() - xact_start as age, left(query, 60)
  from pg_stat_activity
 where datname = 'hillview'
   and (state = 'idle in transaction' or wait_event_type = 'Lock')
 order by xact_start;
```

An `idle in transaction` row with an empty `blocked_by` and a long age is the
head of the line; everything with it in their `blocked_by` is queued behind it.
`select pg_terminate_backend(<pid>)` on the head releases the rest. The only
loss is a transaction that was already abandoned.

If the API has stopped logging and `docker logs hillview_api` ends in
`Waiting for background tasks to complete`, the reload is stuck behind such a
queue; clearing the head lets it finish.

## The rule for sessions and transactions

A transaction should span exactly the work that must be all-or-nothing, and
that work should be entirely inside the database. SQLAlchemy opens one
implicitly on the first statement and keeps it until commit or close, so a
session handed to a helper is an open transaction handed to it — and nothing at
the call site says so; `db` reads as "the database", not "a pooled connection
with a transaction open on it".

Helpers that need the database open their own short session,
`async with SessionLocal() as db`, or take a factory. They never accept a live
session from a caller that will hold it across a network call, a stream, or a
file sweep. Commit or close as soon as the reads are done.

A review of the API found the rule broken in the same way in several places,
each of which becomes harmless to cancellation with the fix above but still
holds a transaction across something outside the database:

- `stream_mapillary_images` in `mapillary_routes.py` passes its request session
  into the long-lived `generate_stream`, which writes through it. The hillview
  `stream` endpoint keeps its request session, and an idle read transaction,
  open for as long as the client stays connected.
- `send_push_to_client` in `push_notifications.py` selects a registration,
  spends up to 30 seconds talking to Firebase or a UnifiedPush endpoint, then
  writes through the same session in `_unregister_stale_endpoints`. Nothing
  there can be atomic; the transaction stands in for a local variable.
- `generate_stream` emits `: heartbeat` only while awaiting Mapillary. Its
  database writes are silent, and a write is the step that can block on a lock,
  so the client watchdog in `StreamSourceLoader.ts` reads the silence as death
  and disconnects — which used to strand the next transaction. That feedback
  loop is how one leak became a 25-deep queue.
- `clear_database` and `set_featured` in `debug_routes.py` drive `get_db` with
  `async for … break`, which abandons the generator at its yield so the close
  runs at garbage collection. `clear_database` also deletes photo files inside an
  open transaction, through `_delete_size` in `photos.py`, which is synchronous
  on the event loop and, for `cdn` pools, uses a boto3 client with no timeouts.

## Guardrails

Planned, once the streams no longer hold a request session:
`idle_in_transaction_session_timeout` of about five minutes, set through the
API engine's `connect_args` so it applies to this app's connections only. It
kills sessions that are idle *inside* a transaction — the leak's shape — and
nothing else: a long-running active statement, such as a `clear-database` over
a prod-sized photo table, is never idle and is untouched.

It waits for the stream work because today the Mapillary handler legitimately
sits idle in a transaction while awaiting Mapillary, whose client timeout is 300
seconds.

Deliberately **not** `lock_timeout` — the preference is to wait behind
legitimate long work rather than fail — and **not** `statement_timeout`, which
is the one that would kill the long delete.
