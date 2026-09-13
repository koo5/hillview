from sqlalchemy import event
from sqlalchemy.orm import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.pool import NullPool, Pool
import anyio
import logging
import os
from dotenv import load_dotenv

log = logging.getLogger(__name__)

load_dotenv()

# Database configuration
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://hillview:hillview@localhost/hillview")

# Connection pool configuration
POOL_SIZE = int(os.getenv("DB_POOL_SIZE", "20"))
MAX_OVERFLOW = int(os.getenv("DB_MAX_OVERFLOW", "10"))
POOL_TIMEOUT = int(os.getenv("DB_POOL_TIMEOUT", "30"))
POOL_RECYCLE = int(os.getenv("DB_POOL_RECYCLE", "3600"))  # Recycle connections after 1 hour

# Backstop against a leaked transaction: Postgres itself aborts any of THIS app's
# sessions left idle inside a transaction for longer than this, releasing the locks
# and the connection. Defence in depth behind the code that now never holds a
# transaction across an await (see docs/db-session-cancellation.md) — if a future
# change regresses that, one connection self-heals instead of wedging the pool the way
# the Mapillary strand did. Deliberately NOT statement_timeout (a legitimately long
# clear-database DELETE is *active*, not idle, and must not be killed) and NOT
# lock_timeout (we prefer to wait behind genuine work). Value is milliseconds; the one
# server-side operation that legitimately idles in a transaction is gone (streams no
# longer hold a session), so five minutes is pure slack. Overridable via env for a test
# that wants to prove the mechanism on a short fuse.
IDLE_IN_TXN_TIMEOUT_MS = os.getenv("DB_IDLE_IN_TXN_TIMEOUT_MS", "300000")
_CONNECT_ARGS = {"server_settings": {"idle_in_transaction_session_timeout": IDLE_IN_TXN_TIMEOUT_MS}}

# Only create async engine if not in alembic sync mode
if not os.getenv("ALEMBIC_SYNC_MODE"):
	_echo = os.getenv("DB_ECHO", "false").lower() == "true"
	if os.getenv("DB_NULLPOOL", "").lower() in ("1", "true", "yes"):
		# Tests: use NullPool so each connection is closed (and the close awaited)
		# when its session closes, instead of lingering in a shared pool. Pooled
		# asyncpg connections that outlive the sync TestClient's event loop get
		# GC'd at teardown and emit "coroutine 'Connection._cancel' was never
		# awaited". NullPool avoids that; production keeps the QueuePool below.
		engine = create_async_engine(DATABASE_URL, poolclass=NullPool, echo=_echo, connect_args=_CONNECT_ARGS)
	else:
		# Create async engine with connection pooling
		engine = create_async_engine(
			DATABASE_URL,
			pool_size=POOL_SIZE,
			max_overflow=MAX_OVERFLOW,
			pool_timeout=POOL_TIMEOUT,
			pool_recycle=POOL_RECYCLE,
			pool_pre_ping=True,  # Test connections before using them
			echo=_echo,
			connect_args=_CONNECT_ARGS,
		)
	SessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
else:
	# In alembic mode, don't create the async engine
	engine = None
	SessionLocal = None

# On the Pool CLASS, not one engine: the bug is in the driver, so it applies to every
# engine this process creates — the app's, a script's, a test's own.
@event.listens_for(Pool, "invalidate")
def _terminate_driver_connection_on_invalidate(dbapi_connection, connection_record, exception):
	"""Hard-close an invalidated asyncpg connection before SQLAlchemy tries to be polite.

	SQLAlchemy invalidates a connection when a statement dies with a BaseException
	(an asyncio.CancelledError, when the client disconnects mid-statement), then
	closes it via the asyncpg adapter's terminate(), which first attempts a graceful
	`close(timeout=2)`. Under an active cancel scope that close is interrupted at its
	first await, and asyncpg 0.30's recovery path is a no-op: Protocol.close() has
	already set `closing`, so the Protocol.abort() it falls back to returns without
	ever aborting the transport, and its cleanup cancels the in-flight cancel request
	too. The socket stays open, referenced by nothing, and the server keeps the
	transaction — "idle in transaction", locks held — until something kills it.
	Reproduced in test_get_db_cancellation; this is what wedged clear-database.

	asyncpg's own Connection.terminate() is synchronous and aborts the transport
	outright as long as `closing` is not yet set — which, at invalidate time, it is
	not. Nothing graceful is lost: an invalidated connection is unusable by
	definition, and the server rolls the transaction back when the backend exits.
	"""
	driver = getattr(dbapi_connection, "driver_connection", None)
	terminate = getattr(driver, "terminate", None)
	if terminate is not None:
		try:
			terminate()
		except Exception as e:
			log.warning(f"Hard-terminating an invalidated connection failed: {e!r}")


Base = declarative_base()

# Bound on the shielded teardown in release_session. This is not a guess at how
# long a close "usually" takes: whether close() finishes or the bound expires and
# the connection is invalidated instead, the outcome for the data is identical —
# an uncommitted transaction is rolled back either way (close() rolls back;
# terminating the socket makes the server roll back). The bound only guarantees
# that a teardown running inside a cancelled scope cannot wait forever on a dead
# peer. Its only cost when it fires is one discarded connection.
RELEASE_TIMEOUT_S = 10


async def release_session(db: AsyncSession) -> None:
	"""Return a session's connection to the pool clean — or not at all.

	This runs under a cancellation shield because the caller is very often inside
	a cancelled anyio scope: that is what Starlette does to a handler when the
	client disconnects mid-request, and inside such a scope every plain await
	raises at once. A bare `await db.close()` there never reaches the server, so
	the connection stays checked out "idle in transaction", holding every row
	lock the request took, until something kills it. One such connection from a
	Mapillary cache write wedged every `DELETE FROM cached_regions` for a day in
	September 2026 — see test_get_db_cancellation for the shape that triggers it.

	`close()` rolls back whatever is uncommitted on its way out. If it does not
	finish within RELEASE_TIMEOUT_S, or fails, the connection is invalidated —
	dropped from the pool rather than handed to the next request dirty. Both
	exits end the transaction; neither depends on the close being quick.
	"""
	with anyio.CancelScope(shield=True):
		closed = False
		with anyio.move_on_after(RELEASE_TIMEOUT_S) as scope:
			try:
				await db.close()
				closed = True
			except Exception as e:
				log.warning(f"Session close failed ({e!r}); invalidating its connection")
		if closed:
			return
		if scope.cancelled_caught:
			log.warning(f"Session close did not finish within {RELEASE_TIMEOUT_S}s; invalidating its connection")
		with anyio.move_on_after(RELEASE_TIMEOUT_S) as scope:
			try:
				await db.invalidate()
			except Exception as e:
				log.error(f"Session invalidate failed as well: {e!r}")
		if scope.cancelled_caught:
			log.error(f"Session invalidate did not finish within {RELEASE_TIMEOUT_S}s; connection may be leaked")


# Dependency to get DB session
async def get_db():
	"""One session per request.

	A transaction should span exactly the work that must be all-or-nothing, and
	that work should be entirely inside the database. SQLAlchemy opens one
	implicitly on the first statement and keeps it until commit or close, so a
	session handed down to a helper is an open transaction handed down with it.
	Helpers that need the database open their own short session
	(`async with SessionLocal() as db`) or take a factory; they never accept a
	live session from a caller that will hold it across a network call, a stream,
	or a file sweep. Commit or close as soon as the reads are done.
	"""
	if SessionLocal is None:
		raise RuntimeError("Database not initialized (ALEMBIC_SYNC_MODE is set)")
	db = SessionLocal()
	try:
		yield db
		# Note: Commit is handled by the endpoint if needed
	finally:
		# Not `except Exception: rollback` — asyncio.CancelledError is not an
		# Exception, and it is the case that matters. close() rolls back too.
		await release_session(db)
