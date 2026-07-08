"""Unit tests for the persistent worker pool (``worker_processing``).

Exercises the real ``worker_processing`` machinery end to end with stub
``blur`` / ``photo_processor`` modules, so the spawn / queue / future / phase-pipe
plumbing runs without cv2/torch. Covers:

  * success round-trip (result dict comes back across the process boundary)
  * cross-process exception-type reconstruction — a ``ValueError`` stays a
    ``ValueError`` (so process() can route it as a permanent failure)
  * a ``TimeoutError`` raised *by the job* stays a plain ``TimeoutError`` and is
    NOT mislabelled ``ProcessingTimeout`` (the submit() shield / ``fut.done()``
    guard)
  * per-photo phase updates piped back into the parent's ``processing_state``
  * the per-job budget timeout surfacing as ``ProcessingTimeout``
  * a worker dying mid-job → supervisor attributes it and fails fast as
    ``WorkerDied`` → pool recovers

Runs as one test on a single pool: spawning is slow and each worker pays a
subprocess start, so we start/stop the pool once rather than per case (which
would also churn the module-global drainer/supervisor threads).

The instant-death case (a worker exiting the same instant it picks a job) is
deliberately omitted: whether its ``"picked"`` message flushes before the exit
is a race, so it non-deterministically fails fast (``WorkerDied``) or via the
timeout backstop — fine in reality, too flaky to assert on in CI.
"""
import asyncio
import os
import shutil
import sys
import tempfile
import textwrap

import pytest

import processing_state
import worker_processing

# tests/unit/test_worker_pool.py -> up three dirs -> backend/worker
WORKER_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture(scope="module", autouse=True)
def _stub_heavy_modules():
	"""Put stub ``blur`` / ``photo_processor`` modules ahead of the real ones on
	PYTHONPATH so the spawned workers import them instead of cv2/torch. The stub
	``process_uploaded_photo`` branches on the filename to simulate each outcome."""
	d = tempfile.mkdtemp(prefix="hillview-pool-stubs-")
	with open(os.path.join(d, "blur.py"), "w") as f:
		f.write("from contextlib import contextmanager\n"
				"@contextmanager\n"
				"def collect_warnings():\n"
				"    yield []\n")
	with open(os.path.join(d, "photo_processor.py"), "w") as f:
		f.write(textwrap.dedent('''
			import os, asyncio, processing_state
			class _PP:
			    async def process_uploaded_photo(self, **kw):
			        processing_state.set_phase("read_exif")
			        fn = kw.get("filename")
			        if fn == "DIELATE":              # die mid-processing (realistic OOM)
			            await asyncio.sleep(0.7)
			            os._exit(9)
			        if fn == "HANG":
			            await asyncio.sleep(30)       # wedged photo -> budget timeout
			        processing_state.set_phase("encode_sizes")
			        if fn == "BADIMAGE":
			            raise ValueError("corrupt image")    # permanent failure
			        if fn == "RAMTIMEOUT":
			            raise TimeoutError("no free RAM")     # a TimeoutError raised BY the job
			        return {"ok": True, "photo_id": kw.get("photo_id")}
			photo_processor = _PP()
		'''))
	# spawn copies the parent's sys.path into each child, so the stub dir must be
	# on sys.path (not just PYTHONPATH) to win over the real cv2-importing modules.
	old_env = os.environ.get("PYTHONPATH", "")
	os.environ["PYTHONPATH"] = os.pathsep.join([d, WORKER_DIR, old_env])
	sys.path.insert(0, d)
	yield
	sys.path.remove(d)
	os.environ["PYTHONPATH"] = old_env
	shutil.rmtree(d, ignore_errors=True)


def _job(photo_id, filename):
	return {
		"file_path": "/x", "filename": filename, "user_id": "u", "photo_id": photo_id,
		"client_signature": "s", "ctx_photo_id": photo_id, "ctx_task_id": "t",
		"anonymization_override": None, "metadata": None, "quality": None,
		"fast": False, "output_base": "/tmp/work/" + photo_id,
	}


@pytest.mark.asyncio
async def test_worker_pool_end_to_end():
	worker_processing.start(2, asyncio.get_running_loop())
	try:
		await asyncio.sleep(0.8)  # let the workers spawn

		# success round-trip
		assert await worker_processing.submit(_job("p1", "ok.jpg"), timeout=20) == {"ok": True, "photo_id": "p1"}

		# a ValueError raised in the child comes back as a ValueError (not a
		# generic RuntimeError), so process() can route it as a permanent failure
		with pytest.raises(ValueError, match="corrupt image"):
			await worker_processing.submit(_job("p2", "BADIMAGE"), timeout=20)

		# a TimeoutError raised BY the job must surface as-is, NOT be mislabelled
		# ProcessingTimeout (submit()'s shield + fut.done() guard)
		with pytest.raises(TimeoutError) as ei:
			await worker_processing.submit(_job("p2b", "RAMTIMEOUT"), timeout=20)
		assert not isinstance(ei.value, worker_processing.ProcessingTimeout)

		# phase pipe-back: the child's set_phase reaches the parent's processing_state
		hang = asyncio.ensure_future(worker_processing.submit(_job("p3", "HANG"), timeout=2))
		await asyncio.sleep(1.0)
		phases = {a["photo_id"]: a["phase"] for a in processing_state.get_active_list()}
		assert phases.get("p3") == "read_exif", phases

		# ...and the per-job budget timeout surfaces as ProcessingTimeout
		with pytest.raises(worker_processing.ProcessingTimeout):
			await hang

		# a worker dying mid-job is attributed by the supervisor and fails fast
		with pytest.raises(worker_processing.WorkerDied):
			await worker_processing.submit(_job("p5", "DIELATE"), timeout=20)

		# the pool self-heals: a respawned worker serves the next job
		await asyncio.sleep(2.0)
		assert await worker_processing.submit(_job("p6", "ok.jpg"), timeout=20) == {"ok": True, "photo_id": "p6"}
	finally:
		worker_processing.shutdown()
