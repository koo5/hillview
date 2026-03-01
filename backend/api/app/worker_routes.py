"""
Worker management routes for handling worker keepalive pings.
"""
import logging
import os
import threading
import time
from typing import Optional

import httpx
from fastapi import APIRouter
from pydantic import BaseModel

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["worker"])

WORKER_URL = os.environ["WORKER_URL"]

# Track active pingback connections per worker to avoid duplicates.
# Key: fly_machine_id, Value: number of active pingback threads.
_active_pingbacks: dict[str, int] = {}
_active_pingbacks_lock = threading.Lock()
_PINGBACKS_PER_WORKER = 2


class WorkerPingRequest(BaseModel):
	worker_identity: str
	fly_machine_id: Optional[str] = None
	pending_tasks: int
	task0_id: str


@router.post("/worker_pending_background_tasks_ping")
async def worker_pending_background_tasks_ping(request: WorkerPingRequest):
	"""
	Receive ping from worker with pending background tasks.
	If fly_machine_id is provided, ping back the worker to prevent Fly.io auto-shutdown.
	Returns immediately — pingback threads run in the background.
	"""
	log.info(f"Worker ping: identity={request.worker_identity}, fly_machine_id={request.fly_machine_id}, pending_tasks={request.pending_tasks}")

	if request.fly_machine_id and request.pending_tasks > 0:
		with _active_pingbacks_lock:
			active = _active_pingbacks.get(request.fly_machine_id, 0)
			needed = _PINGBACKS_PER_WORKER - active
		if needed > 0:
			log.info(f"Launching {needed} pingback thread(s) for worker {request.fly_machine_id} (already active: {active})")
			for _ in range(needed):
				t = threading.Thread(target=_worker_pingback_thread, args=(request,), daemon=True)
				t.start()
		else:
			log.debug(f"Pingback already active for worker {request.fly_machine_id} ({active} threads), skipping")

	return {"status": "ok"}


def _worker_pingback_thread(request: WorkerPingRequest):
	machine_id = request.fly_machine_id
	with _active_pingbacks_lock:
		_active_pingbacks[machine_id] = _active_pingbacks.get(machine_id, 0) + 1
	try:
		while True:
			try:
				response = httpx.post(
					f"{WORKER_URL}/await",
					headers={
						"fly-force-instance-id": machine_id,
						"Connection": "close",
					},
					params={'task_id': request.task0_id},
					timeout=30.0,
				)
				body = response.text
				log.info(f"Pingback to worker {machine_id}: status={response.status_code}, body={body!r}")
				if '"completed"' in body:
					break
			except Exception as e:
				err_text = getattr(e, "message", None) or str(e) or repr(e) or e.__class__.__name__
				log.warning(f"Pingback to worker {machine_id} failed: {err_text}")
				time.sleep(5)
	finally:
		with _active_pingbacks_lock:
			_active_pingbacks[machine_id] = _active_pingbacks.get(machine_id, 1) - 1
			if _active_pingbacks[machine_id] <= 0:
				del _active_pingbacks[machine_id]
