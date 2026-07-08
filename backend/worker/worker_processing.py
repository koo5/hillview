"""Out-of-process photo processing on a pool of persistent worker subprocesses.

Rather than the asyncio threadpool (all processing shares the web process → one
OOM/segfault takes the whole in-memory upload backlog with it), photo processing
runs on a fixed pool of long-running ``spawn`` subprocesses. Each worker loops:
pull the next job off a shared queue, process it, push the result back, repeat.

Why a hand-rolled pool and not ``ProcessPoolExecutor``: when one PPE child dies
abruptly the *entire* executor goes ``BrokenProcessPool`` and every in-flight
future fails. Here a worker death is isolated — a supervisor respawns just that
worker, and only the single photo it was chewing on is failed (the client / API
retries it); the other workers and the whole queued backlog keep going.

``spawn`` (not ``fork``) is mandatory: the parent is multithreaded (uvicorn, the
ping loop, these drainer threads) and forking a multithreaded process risks
deadlock. Heavy imports (cv2, torch, ultralytics via ``photo_processor``) happen
lazily inside the child entrypoint, so importing this module — in the parent or
a freshly spawned worker — stays cheap; each worker pays the ~10 s import once,
on its first photo.

Per-photo phase updates (``read_exif``, ``yolo_scale_*`` …) normally land in
``processing_state._active`` in-process. Since processing now runs in a child,
each worker's ``processing_state.set_phase`` / ``clear_phase`` are monkeypatched
to ship ``(op, photo_id, phase)`` tuples back over ``_phase_queue``; a parent
drainer thread replays them into the parent's ``processing_state`` so /status and
/metrics keep full per-photo phase visibility.

Threading model (parent): the asyncio loop only ``await``s a per-job
``Future``; three daemon threads do the cross-process work — a result drainer
(resolves futures), a phase drainer, and a supervisor (liveness + respawn).
"""
import logging
import multiprocessing
import threading
import time
import traceback
import asyncio

import processing_state
from logging_context import current_photo_id
from exceptions import PhotoDeletedException

logger = logging.getLogger(__name__)


class WorkerDied(RuntimeError):
	"""A processing worker died (e.g. OOM-killed) while holding a job. Distinct
	from TimeoutError so submit()'s wait_for handler doesn't swallow/relabel it —
	in Python 3.11+ asyncio.TimeoutError *is* the builtin TimeoutError. Retriable;
	process()'s catch-all maps it to a retry."""


class ProcessingTimeout(TimeoutError):
	"""The processing job itself exceeded PROCESSING_TIMEOUT_SECONDS of wall-clock
	work (and its worker was killed). A *subclass* of TimeoutError so any handler
	that treats a bare TimeoutError as a retriable resource wait still catches it —
	but a distinct type so process() can tell it apart from the queue/RAM admission
	waits: those are transient ("we're momentarily busy"), whereas a job that blew
	past a multi-hour budget is too large/complex to ever finish within the limit,
	so retrying the *same* photo just times out again. Not a resource shortage."""

# Parent-side state (guarded by _lock).
_lock = threading.Lock()
_started = False
_stop = False
_ctx = None
_job_queue = None       # parent -> workers: {"job_id", "args"} or None sentinel
_result_queue = None    # workers -> parent: (job_id, status, payload)
_phase_queue = None     # workers -> parent: (op, photo_id, phase)
_workers = []           # index -> multiprocessing.Process (None while (re)spawning)
_pending = {}           # job_id -> asyncio.Future
_inflight = {}          # worker_idx -> job_id currently being processed
_loop = None            # the asyncio event loop that owns the futures
_pool_size = 0
_job_counter = 0

# Reconstruct the worker-side exception type so process()'s except-chain still
# routes correctly (e.g. ValueError = permanent, no retry) across the boundary.
_EXC_TYPES = {
	"ValueError": ValueError,
	"PhotoDeletedException": PhotoDeletedException,
	"IOError": OSError,
	"OSError": OSError,
	"PermissionError": PermissionError,
	"FileNotFoundError": FileNotFoundError,
	"TimeoutError": TimeoutError,
}


# ==========================================================================
# Child side (runs inside each spawned worker subprocess)
# ==========================================================================

def _install_phase_pipe(phase_queue):
	"""Redirect this worker's processing_state phase updates back to the parent.

	All child-side callers use ``processing_state.set_phase(...)`` as a module
	attribute, so replacing the attribute intercepts every one."""
	def _send(phase, photo_id=None):
		pid = photo_id or current_photo_id.get()
		if pid:
			try:
				phase_queue.put(("set", pid, phase))
			except Exception:
				pass

	def _clear(photo_id=None):
		pid = photo_id or current_photo_id.get()
		if pid:
			try:
				phase_queue.put(("clear", pid, None))
			except Exception:
				pass

	processing_state.set_phase = _send
	processing_state.clear_phase = _clear


def _worker_main(worker_idx, job_queue, result_queue, phase_queue):
	"""Persistent worker loop: pull a job, process it, report, repeat."""
	_install_phase_pipe(phase_queue)
	logger.info(f"[worker {worker_idx}] started (pid={multiprocessing.current_process().pid})")
	while True:
		job = job_queue.get()
		if job is None:  # shutdown sentinel
			logger.info(f"[worker {worker_idx}] stopping")
			return
		job_id = job["job_id"]
		# Announce pickup so the parent can attribute a death to this job.
		result_queue.put((job_id, "picked", worker_idx))
		try:
			result = _run_photo_processing(**job["args"])
			result_queue.put((job_id, "ok", result))
		except Exception as e:  # noqa: BLE001 — ship type+msg back for routing
			result_queue.put((job_id, "error", {
				"type": type(e).__name__,
				"msg": str(e),
				"tb": traceback.format_exc(),
			}))
			logger.error(f"[worker {worker_idx}] job {job_id} failed: {e}")


def _run_photo_processing(file_path, filename, user_id, photo_id, client_signature,
                          ctx_photo_id=None, ctx_task_id=None, anonymization_override=None,
                          metadata=None, quality=None, fast=False, output_base=None):
	"""Run async photo processing to completion in a dedicated event loop.

	``output_base`` is this job's work dir: we repoint the processor's output
	root at it so every size variant + DZI tile lands under it, and the parent
	reclaims the whole job with a single rmtree (no per-file cleanup list).
	Safe to set on the shared singleton because each worker processes one job at
	a time. Heavy imports (blur, photo_processor) happen here, lazily.
	"""
	from logging_context import task_context
	try:
		with task_context(photo_id=ctx_photo_id, task_id=ctx_task_id):
			from blur import collect_warnings
			# Bracket the run with a TLS warning collector so _dev_only calls
			# downstream (incl. the nested loop) accumulate into one list,
			# attached to the result for the caller to surface.
			with collect_warnings() as warnings:
				loop = asyncio.new_event_loop()
				try:
					from photo_processor import photo_processor
					if output_base:
						photo_processor.upload_dir = output_base
					result = loop.run_until_complete(
						photo_processor.process_uploaded_photo(
							file_path=file_path,
							filename=filename,
							user_id=user_id,
							photo_id=photo_id,
							client_signature=client_signature,
							anonymization_override=anonymization_override,
							metadata=metadata,
							quality=quality,
							fast=fast,
						)
					)
				finally:
					loop.close()
				if isinstance(result, dict) and warnings:
					result['warnings'] = list(warnings)
				return result
	finally:
		# Final clear (FIFO after this photo's set messages) so a late phase
		# update can't leave a stale entry in the parent's _active.
		processing_state.clear_phase(photo_id=ctx_photo_id or photo_id)


# ==========================================================================
# Parent side (pool lifecycle, submission, drainers, supervisor)
# ==========================================================================

def start(pool_size, loop):
	"""Spawn the worker pool and start the drainer/supervisor threads. Idempotent."""
	global _started, _stop, _ctx, _job_queue, _result_queue, _phase_queue, _workers, _loop, _pool_size
	with _lock:
		if _started:
			return
		_started = True
		_stop = False
		_pool_size = max(1, int(pool_size))
		_loop = loop
		_ctx = multiprocessing.get_context("spawn")
		_job_queue = _ctx.Queue()
		_result_queue = _ctx.Queue()
		_phase_queue = _ctx.Queue()
		_workers = [None] * _pool_size
	for idx in range(_pool_size):
		_spawn_worker(idx)
	threading.Thread(target=_result_drain_loop, name="result-drainer", daemon=True).start()
	threading.Thread(target=_phase_drain_loop, name="phase-drainer", daemon=True).start()
	threading.Thread(target=_supervisor_loop, name="worker-supervisor", daemon=True).start()
	logger.info(f"[worker_processing] started {_pool_size} persistent workers")


def _spawn_worker(idx):
	proc = _ctx.Process(
		target=_worker_main,
		args=(idx, _job_queue, _result_queue, _phase_queue),
		name=f"photo-worker-{idx}",
		daemon=False,
	)
	proc.start()
	with _lock:
		_workers[idx] = proc
	logger.info(f"[worker_processing] spawned worker {idx} (pid={proc.pid})")


def _next_job_id():
	global _job_counter
	with _lock:
		_job_counter += 1
		return _job_counter


async def submit(args, timeout=None):
	"""Queue a photo for processing and await the result dict.

	Raises the reconstructed processing exception (so process() routes it),
	``ProcessingTimeout`` if the job exceeded ``timeout``, or ``WorkerDied`` if
	its worker died (e.g. OOM). On timeout the stuck worker is terminated and
	respawned so a single hung photo can't permanently shrink the pool."""
	if not _started:
		raise RuntimeError("worker pool not started")
	job_id = _next_job_id()
	fut = _loop.create_future()
	with _lock:
		_pending[job_id] = fut
	_job_queue.put({"job_id": job_id, "args": args})
	try:
		if timeout is not None:
			try:
				# shield so wait_for's timeout cancels only the wait, not the
				# underlying job future — we still want to read its real outcome.
				await asyncio.wait_for(asyncio.shield(fut), timeout=timeout)
			except asyncio.TimeoutError:
				# Only a genuine budget overrun (job still running) is a
				# ProcessingTimeout. If fut IS done, the job finished right at the
				# deadline — possibly with its own reconstructed TimeoutError — so
				# fall through and surface its real outcome instead of mislabelling.
				if not fut.done():
					_kill_job_worker(job_id)
					raise ProcessingTimeout(f"photo processing exceeded {timeout}s")
			return fut.result()
		return await fut
	finally:
		with _lock:
			_pending.pop(job_id, None)


def _resolve(fut, result=None, exc=None):
	"""Resolve a job future from a drainer/supervisor thread onto the loop."""
	def _set():
		if fut.done():
			return
		if exc is not None:
			fut.set_exception(exc)
		else:
			fut.set_result(result)
	try:
		_loop.call_soon_threadsafe(_set)
	except RuntimeError:
		pass  # loop already closed


def _fail_job(job_id, exc):
	with _lock:
		fut = _pending.get(job_id)
	if fut is not None:
		_resolve(fut, exc=exc)


def _reconstruct_exc(payload):
	cls = _EXC_TYPES.get(payload.get("type"), RuntimeError)
	msg = payload.get("msg") or payload.get("type") or "processing failed"
	try:
		return cls(msg)
	except Exception:
		return RuntimeError(msg)


def _result_drain_loop():
	import queue as _q
	while not _stop:
		try:
			job_id, status, payload = _result_queue.get(timeout=1.0)
		except _q.Empty:
			continue
		except (OSError, EOFError, ValueError):
			time.sleep(0.1)
			continue
		if status == "picked":
			with _lock:
				_inflight[payload] = job_id  # payload = worker_idx
			continue
		# terminal — release the worker's in-flight slot and resolve the future.
		with _lock:
			for widx, jid in list(_inflight.items()):
				if jid == job_id:
					_inflight.pop(widx, None)
					break
			fut = _pending.get(job_id)
		if fut is None:
			continue
		if status == "ok":
			_resolve(fut, result=payload)
		else:
			_resolve(fut, exc=_reconstruct_exc(payload))


def _phase_drain_loop():
	import queue as _q
	while not _stop:
		try:
			op, pid, phase = _phase_queue.get(timeout=1.0)
		except _q.Empty:
			continue
		except (OSError, EOFError, ValueError):
			time.sleep(0.1)
			continue
		try:
			if op == "set":
				processing_state.set_phase(phase, photo_id=pid)
			elif op == "clear":
				processing_state.clear_phase(photo_id=pid)
		except Exception:
			pass


def _supervisor_loop():
	"""Respawn dead workers; fail whatever job the dead worker had picked so the
	client retries fast instead of waiting out the per-job timeout."""
	while not _stop:
		time.sleep(1.0)
		with _lock:
			snapshot = list(enumerate(_workers))
		for idx, proc in snapshot:
			if _stop:
				return
			if proc is None or proc.is_alive():
				continue
			exitcode = proc.exitcode
			with _lock:
				dead_job = _inflight.pop(idx, None)
			logger.warning(f"[worker_processing] worker {idx} died (exitcode={exitcode}); respawning")
			if dead_job is not None:
				_fail_job(dead_job, WorkerDied(f"processing worker died (exitcode={exitcode}, likely OOM); retry later"))
			_spawn_worker(idx)


def _kill_job_worker(job_id):
	"""Terminate the worker processing ``job_id`` (a hung/timed-out job); the
	supervisor then respawns it."""
	with _lock:
		widx = next((w for w, jid in _inflight.items() if jid == job_id), None)
		proc = _workers[widx] if widx is not None else None
		if widx is not None:
			_inflight.pop(widx, None)
	if proc is not None and proc.is_alive():
		logger.warning(f"[worker_processing] terminating worker {widx} for timed-out job {job_id}")
		try:
			proc.terminate()
		except Exception:
			pass


def shutdown():
	"""Best-effort stop: sentinel the workers, stop threads, terminate stragglers."""
	global _stop, _started
	if not _started:
		return
	_stop = True
	try:
		for _ in range(_pool_size):
			_job_queue.put(None)
	except Exception:
		pass
	deadline = time.time() + 5
	for proc in list(_workers):
		if proc is None:
			continue
		remaining = max(0.0, deadline - time.time())
		proc.join(timeout=remaining)
		if proc.is_alive():
			try:
				proc.terminate()
			except Exception:
				pass
	_started = False
	logger.info("[worker_processing] shut down")
