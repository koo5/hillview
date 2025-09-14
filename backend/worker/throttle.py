import logging

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

import time, psutil
import asyncio
from contextlib import asynccontextmanager


class Throttle:

	def __init__(s, tag):
		s.tag = tag
		s._rate_limit_lock = asyncio.Lock()
		s._last_request_time = 0

	@asynccontextmanager
	async def rate_limit(s, interval_seconds: float = 2.0):
		"""
		Async context manager to enforce a rate limit of one operation per `interval_seconds`.
		Usage:
			async with rate_limit():
				# your code here
		"""
		async with s._rate_limit_lock:
			current_time = time.time()
			time_since_last = current_time - s._last_request_time

			if time_since_last < interval_seconds:
				sleep_time = interval_seconds - time_since_last
				logger.debug(f"[THROTTLE] {s.tag} Rate limit: waiting {sleep_time:.2f} seconds")
				await asyncio.sleep(sleep_time)

			logger.debug(f"[THROTTLE] {s.tag} Rate limit: proceeding with request")
			s._last_request_time = time.time()
			yield

	async def wait_for_free_ram(s, required_mb: int, check_interval: float = 1.0, timeout: float = 30.0):
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
				raise TimeoutError(f"{s.tag} Timeout waiting for {required_bytes} bytes of free RAM")
			logger.debug(f"[THROTTLE] {s.tag} Waiting for free RAM...")
			await asyncio.sleep(check_interval)

