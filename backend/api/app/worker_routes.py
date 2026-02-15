"""
Worker management routes for handling worker keepalive pings.
"""
import logging
import os
from typing import Optional

import httpx
from fastapi import APIRouter
from pydantic import BaseModel

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["worker"])

WORKER_URL = os.environ["WORKER_URL"]


class WorkerPingRequest(BaseModel):
	worker_identity: str
	fly_machine_id: Optional[str] = None
	pending_tasks: int
	task0_id: int


@router.post("/worker_pending_background_tasks_ping")
async def worker_pending_background_tasks_ping(request: WorkerPingRequest):
	"""
	Receive ping from worker with pending background tasks.
	If fly_machine_id is provided, ping back the worker to prevent Fly.io auto-shutdown.
	"""
	log.info(f"Worker ping: identity={request.worker_identity}, fly_machine_id={request.fly_machine_id}, pending_tasks={request.pending_tasks}")

	if request.fly_machine_id and request.pending_tasks > 0:
		# Ping back the worker to keep it alive
		# fixme: verify worker signature
		try:
			async with httpx.AsyncClient() as client:
				response = await client.post(
					f"{WORKER_URL}/await",
					headers={"fly-force-instance-id": request.fly_machine_id},
					params={'task_id': request.task0_id},
					timeout=60000.0# might need to set low timeout and reconnect in a loop, if fly.io keeps killing the connection.
				)
				log.info(f"Ping back to worker {request.fly_machine_id}: status={response.status_code}")
		except Exception as e:
			err_text = getattr(e, "message", None) or str(e) or repr(e) or e.__class__.__name__
			log.error(f"Failed to ping back worker {request.fly_machine_id}: {err_text}")
	return {"status": "ok"}
