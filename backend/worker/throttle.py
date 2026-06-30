import logging

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

import time
import psutil
import asyncio
from contextlib import asynccontextmanager
import threading
import processing_state


class Throttle:

	def __init__(s, tag):
		s.tag = tag
		s._lock = threading.Lock()
		s._last_request_time = 0
		s._running_tasks = 0
		# Token-bucket pacer: monotonic time of the next allowed start. Each
		# admission reserves max(now, _next_start) and pushes _next_start out
		# by interval_seconds, so starts are spaced without holding the lock
		# across the wait. Shared across the per-task event loops via _lock.
		s._next_start = 0.0

	@asynccontextmanager
	async def rate_limit(s, interval_seconds: float = 10.0, ram_mb: int = None):
		"""Pace operation *starts* without capping or serializing concurrency.

		Successive starts are spaced at least ``interval_seconds`` apart
		(anti-thundering-herd: let one start allocate its working set before
		the next RAM check), but tasks wait CONCURRENTLY for their own reserved
		start time. The lock is held only to reserve a slot — a few arithmetic
		ops with no ``await`` inside — so a backlog no longer serializes behind
		one holder (nor blocks every other task's loop in ``_lock.acquire``) the
		way holding the lock across the sleep did. This matters now that
		``PARALLEL_PROCESSING_START_DELAY`` may be small and concurrency high.

		Concurrency is bounded elsewhere (the caller's ``processing_semaphore``
		+ ``wait_for_free_ram``); this only paces starts. ``_running_tasks``
		(tasks in-flight inside the context) is kept for the ``/ready`` snapshot.

		Called once per task, each from its own event loop in a threadpool
		thread, so ``_lock`` is a cross-thread ``threading.Lock`` and the brief,
		await-free critical sections don't meaningfully block any one loop.
		"""
		# Reserve this task's start slot under a short, await-free lock.
		with s._lock:
			now = time.monotonic()
			start_at = max(now, s._next_start)
			s._next_start = start_at + interval_seconds
		# Wait for the reserved slot WITHOUT holding the lock — other tasks
		# reserve and wait concurrently rather than queueing behind us.
		delay = start_at - time.monotonic()
		if delay > 0:
			processing_state.set_phase(f"wait_stagger_{delay:.0f}s")
			logger.debug(f"[THROTTLE] {s.tag} start-stagger: waiting {delay:.2f}s for reserved slot")
			await asyncio.sleep(delay)
		if ram_mb is not None:
			await s.wait_for_free_ram(ram_mb)
		logger.debug(f"[THROTTLE] {s.tag} Rate limit: proceeding with request")
		with s._lock:
			s._last_request_time = time.time()
			s._running_tasks += 1
		try:
			yield
		finally:
			with s._lock:
				s._running_tasks -= 1

	async def wait_for_free_ram(s, required_mb: int, check_interval: float = 1.0, timeout: float = 600_000_000.0):
		"""
		Wait until there is at least `required_bytes` of free RAM available.
		Checks every `check_interval` seconds, up to `timeout` seconds.
		Raises TimeoutError if timeout is reached without enough free RAM.
		"""

		required_bytes = required_mb * 1024 * 1024

		start_time = time.time()
		phase_set = False
		while True:
			mem = psutil.virtual_memory()
			avail_mb = mem.available / (1024 * 1024)
			logger.debug(f"[THROTTLE] {s.tag} Available RAM: {avail_mb:.2f} MB, Required: {required_mb} MB")
			if mem.available >= required_bytes:
				return
			if not phase_set:
				processing_state.set_phase(f"wait_ram_{required_mb}mb")
				phase_set = True
			if time.time() - start_time > timeout:
				logger.error(f"wait_for_free_ram timeout for {s.tag}")
				raise TimeoutError(f"{s.tag} Timeout waiting for {required_bytes} bytes of free RAM")
			logger.debug(f"[THROTTLE] {s.tag} Waiting for free RAM ({avail_mb:.0f}/{required_mb} MB)...")
			await asyncio.sleep(check_interval)

