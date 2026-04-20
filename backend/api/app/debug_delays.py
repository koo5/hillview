"""Process-wide artificial-latency knobs for debugging.

Lets an operator inject a sleep into specific hot paths without
restarting the API or editing code. Useful both in dev (tests that want
a wider observation window for in-flight requests — e.g. the photo-
upload foreground notification on Android) and in prod for reproducing
race conditions or slow-network-like behavior on demand.

Set via the `POST /api/internal/debug/delays` endpoint in debug_routes.
Read by the code paths that opt in via `sleep_for("name")`.

State is in-memory and per-process: resets on restart, and with multiple
API workers behind a load balancer only the one receiving the write
observes it. Good enough for its purpose — nothing persistent required.
"""

from __future__ import annotations

import asyncio
import logging

log = logging.getLogger(__name__)

_delays: dict[str, float] = {}


def set_delay(name: str, seconds: float) -> None:
	"""Set an artificial delay (in seconds) for the named code path."""
	if seconds < 0:
		raise ValueError("seconds must be non-negative")
	if seconds == 0:
		_delays.pop(name, None)
		log.info(f"debug_delays: cleared '{name}'")
	else:
		_delays[name] = seconds
		log.info(f"debug_delays: set '{name}' = {seconds}s")


def get_delay(name: str) -> float:
	"""Return the currently-configured delay for `name`, or 0."""
	return _delays.get(name, 0.0)


def snapshot() -> dict[str, float]:
	"""Return a copy of the current delay map. For the listing endpoint."""
	return dict(_delays)


async def sleep_for(name: str) -> None:
	"""Await the configured delay for `name` (no-op if unset).

	Call this at the point in a handler where you want the delay to
	apply. Usually right before returning the response.
	"""
	seconds = get_delay(name)
	if seconds > 0:
		await asyncio.sleep(seconds)
