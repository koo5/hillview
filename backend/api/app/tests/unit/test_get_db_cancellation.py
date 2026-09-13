"""A request cancelled mid-transaction must not leave that transaction open.

Why this test exists: a Mapillary SSE cache write, cancelled when the client
disconnected, left its connection "idle in transaction" holding row locks on
cached_regions. Every later `DELETE FROM cached_regions` (clear-database) queued
behind it — 20 Playwright tests at 9 minutes each in the 2026-09-05 run, and it
recurred within an hour of the manual cleanup. The teardown in `get_db` ran inside
the cancelled scope, where every await raises at once, so neither the rollback
nor the close ever reached the server.

The cancellation here is an anyio cancel scope, not a bare `task.cancel()`: that
is how Starlette cancels a handler when the client goes away, and it is the
behaviour that matters — asyncio's one-shot cancel would let the teardown awaits
succeed and hide the bug. The generator is driven through `asynccontextmanager`,
which is how FastAPI drives dependency generators (it throws the exception into
the generator at its yield).

Needs a live postgres: DATABASE_URL, defaulting to the dev compose port. Skips
otherwise. Uses its own one-connection QueuePool so the connection really is
returned to (or withheld from) a pool — the unit conftest forces NullPool on the
module engine, which would mask the failure mode.
"""
import os
from contextlib import asynccontextmanager

import anyio
import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

import common.database as database

DEV_URL = "postgresql+asyncpg://hillview:hillview@localhost:25432/hillview"


@pytest_asyncio.fixture
async def db_setup(monkeypatch):
	url = os.getenv("DATABASE_URL", DEV_URL)
	pooled = create_async_engine(url, pool_size=1, max_overflow=0, pool_timeout=5)
	# The probe has its own connections: if the bug withholds the pooled one, a
	# probe drawn from the same pool would just time out instead of observing it.
	probe = create_async_engine(url, poolclass=NullPool)
	try:
		async with probe.connect() as conn:
			await conn.execute(text("select 1"))
	except Exception as e:
		await pooled.dispose()
		await probe.dispose()
		pytest.skip(f"no postgres reachable at {url}: {e}")

	monkeypatch.setattr(
		database, "SessionLocal", sessionmaker(pooled, class_=AsyncSession, expire_on_commit=False)
	)
	yield probe
	await pooled.dispose()
	await probe.dispose()


async def backend_state(probe, pid: int):
	"""pg_stat_activity.state of one backend, from a separate connection. None: gone."""
	async with probe.connect() as conn:
		row = await conn.execute(text("select state from pg_stat_activity where pid = :pid"), {"pid": pid})
		return row.scalar_one_or_none()


async def wait_for_backend(probe, pid: int, predicate, what: str, timeout_s: float = 30):
	"""Poll pg_stat_activity until `predicate(state)` holds. Correct by observation
	rather than by assumed durations: nothing here guesses how long a statement takes
	to reach the server or to finish."""
	with anyio.fail_after(timeout_s):
		while True:
			state = await backend_state(probe, pid)
			if predicate(state):
				return state
			await anyio.sleep(0.05)


@pytest.mark.asyncio
async def test_cancelled_request_does_not_leave_idle_in_transaction(db_setup):
	probe = db_setup
	pid_ready = anyio.Event()
	seen = {}

	async def request():
		async with asynccontextmanager(database.get_db)() as db:
			seen["pid"] = (await db.execute(text("select pg_backend_pid()"))).scalar_one()
			await db.execute(text("select 1"))  # autobegin — the transaction is open from here
			pid_ready.set()
			# The production shape: a statement is IN FLIGHT when the client goes away.
			# The wedged sessions all showed an INSERT/UPDATE as their last statement.
			await db.execute(text("select pg_sleep(3)"))

	async with anyio.create_task_group() as tg:
		tg.start_soon(request)
		await pid_ready.wait()
		# Pull the plug only once the server is provably executing the statement.
		await wait_for_backend(probe, seen["pid"], lambda st: st == "active", "statement running")
		tg.cancel_scope.cancel()

	# Wait until the statement is over — the backend is gone, or no longer 'active' —
	# so the state we assert on is the settled one, however long the server took.
	state = await wait_for_backend(probe, seen["pid"], lambda st: st != "active", "statement finished")
	# 'idle': back in the pool, transaction ended. None: invalidated and closed.
	# Both are fine. Anything 'idle in transaction…' is the wedge — including the
	# '(aborted)' flavour, which still holds every lock the transaction took.
	assert not (state or "").startswith("idle in transaction"), (
		f"backend {seen['pid']} is still inside a transaction ({state!r}) after its request was cancelled"
	)
