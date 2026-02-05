import logging

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

import time, psutil
import asyncio
from contextlib import asynccontextmanager
import threading


class Throttle:

	def __init__(s, tag):
		s.tag = tag
		s._lock = threading.Lock()
		s._last_request_time = 0
		s._running_tasks = 0

	@asynccontextmanager
	async def rate_limit(s, interval_seconds: float = 5.0):
		"""
		Async context manager to enforce a rate limit between operation starts.
		- If no task running: starts immediately
		- If task(s) running: waits for interval since last start
		- Allows unlimited concurrent operations
		Thread-safe: works across threads without blocking the event loop.
		"""
		await asyncio.to_thread(s._lock.acquire)
		try:
			delay_start = time.time()
			while True:
				if s._running_tasks == 0:
					break
				current_time = time.time()

				if current_time - delay_start < interval_seconds:
					logger.debug(f"[THROTTLE] {s.tag} Rate limit: waiting up to {interval_seconds:.2f} seconds")
					await asyncio.sleep(0.5)
				else:
					logger.debug(f"[THROTTLE] {s.tag} Rate limit: proceeding after wait of {current_time - delay_start:.2f} seconds")
					break

			logger.debug(f"[THROTTLE] {s.tag} Rate limit: proceeding with request")
			s._last_request_time = time.time()
			s._running_tasks += 1
		finally:
			s._lock.release()

		try:
			yield
		finally:
			await asyncio.to_thread(s._lock.acquire)
			try:
				s._running_tasks -= 1
			finally:
				s._lock.release()

	async def wait_for_free_ram(s, required_mb: int, check_interval: float = 1.0, timeout: float = 600.0):
		"""
		Wait until there is at least `required_bytes` of free RAM available.
		Checks every `check_interval` seconds, up to `timeout` seconds.
		Raises TimeoutError if timeout is reached without enough free RAM.
		"""

		required_bytes = required_mb * 1024 * 1024

		start_time = time.time()
		while True:
			mem = psutil.virtual_memory()
			logger.debug(
				f"[THROTTLE] {s.tag} Available RAM: {mem.available / (1024 * 1024):.2f} MB, Required: {required_mb} MB")
			if mem.available >= required_bytes:
				return
			if time.time() - start_time > timeout:
				logger.error(f"wait_for_free_ram timeout for {s.tag}")
				raise TimeoutError(f"{s.tag} Timeout waiting for {required_bytes} bytes of free RAM")
			logger.debug(f"[THROTTLE] {s.tag} Waiting for free RAM...")
			await asyncio.sleep(check_interval)

