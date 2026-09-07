#!/usr/bin/env python3
"""Minimal reproduction: a statement cancelled mid-flight strands its connection.

No Hillview code involved — a SQLAlchemy 2.0 async engine over asyncpg, and an
anyio cancel scope, which is how Starlette cancels a handler when the client
disconnects. Run it against any Postgres:

	DATABASE_URL=postgresql+asyncpg://user:pass@host:port/db python repro_asyncpg_cancel_strand.py

Expected output on asyncpg 0.30.0 / SQLAlchemy 2.0.36:

	without workaround: backend state='idle in transaction'  client socket=ESTAB
	with workaround:    backend state=None (gone)            client socket=gone

What happens without the workaround: SQLAlchemy invalidates the connection on the
CancelledError and closes it through the asyncpg adapter's terminate(), which first
awaits asyncpg's graceful close(timeout=2). Protocol.close() sets `closing = True`,
sends a cancel request for the running statement, and awaits it; the cancelled
scope interrupts that await; asyncpg falls back to _abort() -> Protocol.abort(),
which starts with `if self.closing: return`. The transport is never aborted and the
pending cancel request is cancelled by _cleanup(). The server finishes the statement
and then waits for a client that will never speak again, holding every lock the
transaction took.

The workaround terminates the driver connection synchronously at invalidate time,
before the polite path can be interrupted. In Hillview it lives on the Pool class in
common/database.py; here it is on the one engine so the two runs can be compared.
"""
import asyncio
import os
import subprocess

import anyio
from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

URL = os.environ.get("DATABASE_URL", "postgresql+asyncpg://hillview:hillview@localhost:25432/hillview")


def client_socket_state(client_port: int) -> str:
	out = subprocess.run(["ss", "-tan"], capture_output=True, text=True).stdout
	for line in out.splitlines():
		parts = line.split()
		if len(parts) >= 4 and parts[3].endswith(f":{client_port}"):
			return parts[0]
	return "gone"


async def scenario(workaround: bool) -> None:
	engine = create_async_engine(URL, pool_size=1, max_overflow=0, pool_timeout=5)
	probe = create_async_engine(URL, poolclass=NullPool)  # own connections, so it can't be starved
	if workaround:
		@event.listens_for(engine.sync_engine, "invalidate")
		def _terminate(dbapi_connection, connection_record, exception):
			dbapi_connection.driver_connection.terminate()

	seen = {}
	ready = anyio.Event()

	async def request():
		async with engine.connect() as conn:
			seen["pid"] = (await conn.execute(text("select pg_backend_pid()"))).scalar_one()
			ready.set()
			await conn.execute(text("select pg_sleep(3)"))  # in flight when the client goes away

	async def backend():
		async with probe.connect() as c:
			return (await c.execute(
				text("select state, client_port from pg_stat_activity where pid = :pid"), {"pid": seen["pid"]}
			)).first()

	async def wait_until(pred, timeout_s=30):
		with anyio.fail_after(timeout_s):
			while True:
				row = await backend()
				if pred(row):
					return row
				await anyio.sleep(0.05)

	async with anyio.create_task_group() as tg:
		tg.start_soon(request)
		await ready.wait()
		# Cancel only once the server is provably executing the statement.
		await wait_until(lambda row: row is not None and row[0] == "active")
		tg.cancel_scope.cancel()

	# Settled state: the backend is gone, or its statement is no longer running.
	row = await wait_until(lambda row: row is None or row[0] != "active")
	state = row[0] if row else None
	sock = client_socket_state(row[1]) if row else "gone"
	label = "with workaround:   " if workaround else "without workaround:"
	print(f"{label} backend state={state!r:24} client socket={sock}")
	await engine.dispose()
	await probe.dispose()


async def main() -> None:
	await scenario(workaround=False)
	await scenario(workaround=True)


if __name__ == "__main__":
	asyncio.run(main())
