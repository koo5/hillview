"""Out-of-process photo processing on a pool of persistent worker subprocesses.

Rather than the asyncio threadpool (all processing shares the web process → one
OOM/segfault takes the whole in-memory upload backlog with it), photo processing
runs on long-running ``spawn`` subprocesses. The default shape is ONE worker
process running ``threads`` puller threads: each thread loops pull-job /
process / report. One process means one copy of the heavy imports (torch, cv2,
the YOLO model — ~700 MB RSS); the 3-process variant tripled that overhead and
pushed available RAM down to the admission gate's threshold (the 2026-07-13
livelock). Threading *within* the child is the old pre-split concurrency model,
just moved out of the web process — GIL contention stays contained in the child,
so the parent's event loop (and /status, /metrics, health checks) stays
responsive no matter what processing does.

Why a hand-rolled pool and not ``ProcessPoolExecutor``: when one PPE child dies
abruptly the *entire* executor goes ``BrokenProcessPool`` and every in-flight
future fails. Here a worker death is isolated — a supervisor respawns just that
worker, and only the single photo it was chewing on is failed (the client / API
retries it); the other workers and the whole queued backlog keep going.

``spawn`` (not ``fork``) is mandatory: the parent is multithreaded (uvicorn, the
ping loop, these drainer threads) and forking a multithreaded process risks
deadlock. Heavy imports (cv2, torch, ultralytics via ``photo_processor``) never
run in the parent; the worker child warms them at spawn, BEFORE pulling its
first job — so the RSS they cost (~700 MB) is already on the books when the
parent's admission RAM gate measures the machine, instead of landing mid-photo
right after the first admission. (The YOLO weights themselves still load
lazily on first detection.)

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
import os
import signal
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
_pending = {}           # job_id -> (asyncio.Future, args) — args kept for requeue-on-rebuild
_inflight = {}          # worker_idx -> set of job_ids currently being processed
_loop = None            # the asyncio event loop that owns the futures
_pool_size = 0
_threads = 1            # puller threads per worker process
_job_counter = 0

# After an UNPLANNED worker death (OOM-kill, segfault — anything but our own
# deliberate SIGTERM for a timed-out job), process this many jobs serially
# before allowing parallelism again: if the machine just OOMed under N
# concurrent jobs, immediately running N more concurrently invites a repeat.
# app.wait_admission() enforces it (serial_mode() + pending_count()); each
# successful job counts the pool back down toward normal operation.
OOM_SERIAL_RECOVERY_JOBS = int(os.getenv("OOM_SERIAL_RECOVERY_JOBS", "10"))
_serial_remaining = 0   # >0 → admit one job at a time; -1 per success


def serial_mode():
	"""True while the pool is recovering from an unplanned worker death."""
	with _lock:
		return _serial_remaining > 0

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


def _worker_main(worker_idx, job_queue, result_queue, phase_queue, threads=1):
	"""Persistent worker process: run ``threads`` puller threads, each looping
	pull-a-job / process / report. Threads share this process's single copy of
	the heavy imports (torch/cv2/YOLO) — that sharing is the point of
	threads-in-one-child over one-child-per-slot."""
	_install_phase_pipe(phase_queue)
	logger.info(f"[worker {worker_idx}] started (pid={multiprocessing.current_process().pid}, threads={threads})")

	# Warm the heavy imports BEFORE any job is pulled: this pre-pays the
	# ~700 MB / ~10 s of cv2+torch+ultralytics at spawn, so the parent's RAM
	# gate always measures the settled post-import baseline (otherwise the
	# first admission's RAM check runs before the growth it triggers). Failures
	# are non-fatal — the per-job import would surface the same error as a
	# normal, retriable job failure.
	t0 = time.monotonic()
	for mod in ("photo_processor", "anonymize"):
		try:
			__import__(mod)
		except Exception as e:  # noqa: BLE001
			logger.error(f"[worker {worker_idx}] warm-up import of {mod} failed: {e}")
	logger.info(f"[worker {worker_idx}] warm-up imports done in {time.monotonic() - t0:.1f}s")

	def _pull_loop():
		while True:
			job = job_queue.get()
			if job is None:  # shutdown sentinel (one per thread)
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

	pullers = [threading.Thread(target=_pull_loop, name=f"puller-{i}", daemon=False)
			   for i in range(max(1, threads))]
	for t in pullers:
		t.start()
	for t in pullers:
		t.join()
	logger.info(f"[worker {worker_idx}] stopping")


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

def start(pool_size, loop, threads=1):
	"""Spawn the worker pool and start the drainer/supervisor threads. Idempotent.

	``pool_size`` worker processes × ``threads`` puller threads each. Production
	shape is 1 × PARALLEL_PROCESSING_CONCURRENCY: one copy of the heavy imports,
	concurrency via threads inside that child."""
	global _started, _stop, _ctx, _job_queue, _result_queue, _phase_queue, _workers, _loop, _pool_size, _threads
	with _lock:
		if _started:
			return
		_started = True
		_stop = False
		_pool_size = max(1, int(pool_size))
		_threads = max(1, int(threads))
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
		args=(idx, _job_queue, _result_queue, _phase_queue, _threads),
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


def pending_count():
	"""Jobs submitted and not yet finished — the parent's authoritative
	'running' count, used by app.wait_admission()'s force-progress rule."""
	with _lock:
		return len(_pending)


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
		_pending[job_id] = (fut, args)
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
		entry = _pending.get(job_id)
	if entry is not None:
		_resolve(entry[0], exc=exc)


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
				_inflight.setdefault(payload, set()).add(job_id)  # payload = worker_idx
			continue
		# terminal — release the job's in-flight entry and resolve the future.
		with _lock:
			for jobs in _inflight.values():
				jobs.discard(job_id)
			entry = _pending.get(job_id)
		if entry is None:
			continue
		fut = entry[0]
		if status == "ok":
			global _serial_remaining
			with _lock:
				if _serial_remaining > 0:
					_serial_remaining -= 1
					if _serial_remaining == 0:
						logger.info("[worker_processing] serial mode lifted — resuming parallel processing")
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


def _rebuild_queues(exclude_job_ids):
	"""Replace all three IPC queues after a child died — a killed child can die
	with a puller thread blocked inside ``job_queue.get()``, still holding the
	queue's shared reader lock, which poisons the queue: every later ``get()``
	(including the respawned child's) blocks forever. Caught by
	test_worker_pool: the respawned worker never picked another job.

	Submitted-but-unfinished jobs (minus ``exclude_job_ids`` — the dead child's
	in-flight jobs, whose futures the supervisor is failing right now; their
	done() state may lag behind call_soon_threadsafe) are re-enqueued on the
	fresh queue, so nothing queued is lost. The drainer threads re-read the
	module globals every iteration and migrate on their next tick.

	Only valid with a single worker process: with siblings, the old queues are
	still held by live children and can't be swapped out from under them.
	"""
	global _job_queue, _result_queue, _phase_queue
	_job_queue = _ctx.Queue()
	_result_queue = _ctx.Queue()
	_phase_queue = _ctx.Queue()
	with _lock:
		requeue = [(jid, args) for jid, (fut, args) in _pending.items()
				   if jid not in exclude_job_ids and not fut.done()]
	for jid, args in requeue:
		_job_queue.put({"job_id": jid, "args": args})
	if requeue:
		logger.info(f"[worker_processing] re-enqueued {len(requeue)} queued job(s) on fresh queues")


def _supervisor_loop():
	"""Respawn dead workers; fail every job the dead worker was holding so the
	clients retry fast instead of waiting out the per-job timeout. With the
	1×N-threads shape a child death takes all in-flight jobs — acceptable
	collateral: they are all retriable, and the parent's backlog survives."""
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
				dead_jobs = _inflight.pop(idx, set())
			logger.warning(f"[worker_processing] worker {idx} died (exitcode={exitcode}); "
						   f"respawning, failing {len(dead_jobs)} in-flight job(s)")
			# Unplanned death (not our own SIGTERM for a timed-out job) → recover
			# serially for a while. Set BEFORE failing the futures so a caller that
			# just saw WorkerDied already observes serial_mode() as true.
			if exitcode != -signal.SIGTERM:
				global _serial_remaining
				with _lock:
					_serial_remaining = OOM_SERIAL_RECOVERY_JOBS
				logger.warning(f"[worker_processing] unplanned worker death — serial mode for "
							   f"the next {OOM_SERIAL_RECOVERY_JOBS} jobs")
			for job_id in dead_jobs:
				_fail_job(job_id, WorkerDied(f"processing worker died (exitcode={exitcode}, likely OOM); retry later"))
			if _pool_size == 1:
				_rebuild_queues(dead_jobs)  # the dead child may have poisoned the queue locks
			_spawn_worker(idx)


def _kill_job_worker(job_id):
	"""Terminate the worker processing ``job_id`` (a hung/timed-out job); the
	supervisor then respawns it and fails the worker's OTHER in-flight jobs as
	WorkerDied (retriable collateral — deliberate, see _supervisor_loop). Only
	the timed-out job is discarded here so the supervisor doesn't also try to
	fail the future submit() has already abandoned."""
	with _lock:
		widx = next((w for w, jobs in _inflight.items() if job_id in jobs), None)
		proc = _workers[widx] if widx is not None else None
		if widx is not None:
			_inflight[widx].discard(job_id)
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
		for _ in range(_pool_size * _threads):  # one sentinel per puller thread
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
