"""
Per-photo processing phase tracker.

set_phase() / clear_phase() are called at key processing milestones in
app.py, photo_processor.py, and anonymize.py.  The background loop in
app.py calls format_active() every ~10 s to log a live snapshot of what
each in-flight photo is currently doing.

photo_id defaults to current_photo_id from logging_context so callers
don't have to pass it explicitly — the contextvars mechanism propagates
it across threads via Starlette's run_in_threadpool.
"""
import threading
import time
from logging_context import current_photo_id

_lock = threading.Lock()
_active: dict = {}  # photo_id -> {"phase": str, "since": float}


def set_phase(phase: str, photo_id: str = None) -> None:
	pid = photo_id or current_photo_id.get()
	if not pid:
		return
	with _lock:
		entry = _active.get(pid)
		if entry is not None:
			entry["phase"] = phase
			entry["since"] = time.monotonic()
		else:
			_active[pid] = {"phase": phase, "since": time.monotonic()}


def clear_phase(photo_id: str = None) -> None:
	pid = photo_id or current_photo_id.get()
	if not pid:
		return
	with _lock:
		_active.pop(pid, None)


def format_active() -> str:
	"""'abc12345:yolo_scale_1.00(12s), def67890:encode_sizes(3s)' — empty string if nothing active."""
	now = time.monotonic()
	with _lock:
		if not _active:
			return ""
		parts = [
			f"{pid[:8]}:{info['phase']}({now - info['since']:.0f}s)"
			for pid, info in _active.items()
		]
	return ", ".join(parts)


def get_active_list() -> list:
	"""Return active phases as a list of dicts suitable for JSON serialisation."""
	now = time.monotonic()
	with _lock:
		return [
			{
				"photo_id": pid,
				"phase": info["phase"],
				"elapsed_s": round(now - info["since"], 1),
			}
			for pid, info in _active.items()
		]
