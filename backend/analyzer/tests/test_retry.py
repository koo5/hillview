"""
Pure-function coverage for the analyzer's retry policy and the sessions-file lock.

Run from backend/analyzer:  uv run --with pytest pytest tests -q
"""
import subprocess
import sys
import textwrap
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

import distill
from distill import (
	acquire_file_lock,
	count_failed_attempts,
	file_lock,
	find_duplicate,
	load_sessions,
	lock_path_for,
	release_file_lock,
	save_sessions,
)
import analyzer
from analyzer import (
	GIVEN_UP,
	MAX_JUNK_ATTEMPTS,
	RETRY_ERROR,
	RETRY_JUNK_STEP,
	RETRY_MISSING_IMAGE,
	Outcome,
	next_retry_for,
)

MODEL = "qwen/qwen3-vl-30b-a3b-thinking"
PROMPT = "Analyze this photo.\n{schema}"
TEMPERATURE = 0
MAX_TOKENS = 6666


def _session(model=MODEL, prompt=PROMPT, temperature=TEMPERATURE, max_tokens=MAX_TOKENS,
			 parse_error=False, timestamp="2026-09-01T00:00:00+00:00"):
	s = {
		"metadata": {"model": model, "timestamp": timestamp, "image_url": "u", "image_hash": None},
		"request": {
			"model": model,
			"messages": [{"role": "user", "content": [{"type": "text", "text": prompt}]}],
			"max_tokens": max_tokens,
			"temperature": temperature,
		},
		"result": {"parse_error": parse_error},
	}
	if not parse_error:
		s["analysis"] = {"time_of_day": "day"}
	return s


# --- count_failed_attempts / find_duplicate -------------------------------

def test_count_failed_attempts_counts_only_matching_parse_errors():
	sessions = [
		_session(parse_error=True),
		_session(parse_error=True),
		_session(parse_error=False),                     # a success is not a failed attempt
		_session(parse_error=True, model="other/model"), # different model
		_session(parse_error=True, prompt="different"),  # different prompt
		_session(parse_error=True, temperature=0.7),     # different temperature
		_session(parse_error=True, max_tokens=1),        # different max_tokens
	]
	assert count_failed_attempts(sessions, MODEL, PROMPT, TEMPERATURE, MAX_TOKENS) == 2
	assert count_failed_attempts([], MODEL, PROMPT, TEMPERATURE, MAX_TOKENS) == 0


def test_find_duplicate_still_skips_parse_errors_and_matches_exactly():
	bad = _session(parse_error=True)
	good = _session(parse_error=False)
	assert find_duplicate([bad], MODEL, PROMPT, TEMPERATURE, MAX_TOKENS) is None
	assert find_duplicate([bad, good], MODEL, PROMPT, TEMPERATURE, MAX_TOKENS) is good
	assert find_duplicate([good], MODEL, "other prompt", TEMPERATURE, MAX_TOKENS) is None


# --- next_retry_for -------------------------------------------------------

NOW = datetime(2026, 9, 13, 12, 0, tzinfo=timezone.utc)


def test_ok_schedules_no_retry():
	# a complete run leaves the queue, there is nothing to schedule
	assert next_retry_for(Outcome('ok', analysis={}), NOW) is None


def test_junk_backs_off_by_attempts_then_gives_up():
	assert next_retry_for(Outcome('junk', junk_attempts=1), NOW) == NOW + RETRY_JUNK_STEP
	assert next_retry_for(Outcome('junk', junk_attempts=2), NOW) == NOW + 2 * RETRY_JUNK_STEP
	assert next_retry_for(Outcome('junk', junk_attempts=MAX_JUNK_ATTEMPTS), NOW) == GIVEN_UP
	assert next_retry_for(Outcome('junk', junk_attempts=MAX_JUNK_ATTEMPTS + 5), NOW) == GIVEN_UP
	# a junk outcome with a zero count (should not happen) still backs off one step
	assert next_retry_for(Outcome('junk', junk_attempts=0), NOW) == NOW + RETRY_JUNK_STEP


def test_missing_image_and_error_backoffs():
	assert next_retry_for(Outcome('no_image'), NOW) == NOW + RETRY_MISSING_IMAGE
	assert next_retry_for(Outcome('image_404'), NOW) == NOW + RETRY_MISSING_IMAGE
	assert next_retry_for(Outcome('error'), NOW) == NOW + RETRY_ERROR


def test_unknown_kind_is_an_error():
	with pytest.raises(ValueError):
		next_retry_for(Outcome('what'), NOW)


def test_given_up_is_the_asyncpg_infinity_sentinel():
	# asyncpg encodes exactly tz-aware datetime.max as Postgres 'infinity' (verified against the dev DB;
	# the read direction yields a naive datetime.max, which is why the loop only compares in SQL)
	assert GIVEN_UP == datetime.max.replace(tzinfo=timezone.utc)
	assert GIVEN_UP > NOW + timedelta(days=365 * 100)


# --- file lock ------------------------------------------------------------

HOLDER = textwrap.dedent("""
	import fcntl, sys, time
	f = open(sys.argv[1], 'w')
	fcntl.flock(f.fileno(), fcntl.LOCK_EX)
	print('locked', flush=True)
	time.sleep(60)
""")


def _hold_lock_in_subprocess(lock_path: Path) -> subprocess.Popen:
	proc = subprocess.Popen([sys.executable, "-c", HOLDER, str(lock_path)], stdout=subprocess.PIPE, text=True)
	assert proc.stdout.readline().strip() == "locked"
	return proc


def test_nonblocking_lock_reports_a_live_holder_and_frees_when_it_dies(tmp_path):
	json_path = tmp_path / "abc.json"
	lock_path = lock_path_for(json_path)
	assert lock_path == tmp_path / "abc.json.lock"

	proc = _hold_lock_in_subprocess(lock_path)
	try:
		assert acquire_file_lock(lock_path, blocking=False) is None
		with file_lock(lock_path, blocking=False) as held:
			assert held is False
	finally:
		proc.kill()
		proc.wait()

	# the kernel dropped the dead holder's flock
	lock_file = acquire_file_lock(lock_path, blocking=False)
	assert lock_file is not None
	try:
		with file_lock(lock_path, blocking=False) as held:
			assert held is False  # we hold it ourselves, on another fd
	finally:
		release_file_lock(lock_file)

	with file_lock(lock_path, blocking=False) as held:
		assert held is True


def test_sessions_io_with_lock_false_does_not_self_deadlock(tmp_path):
	json_path = tmp_path / "abc.json"
	lock_file = acquire_file_lock(lock_path_for(json_path), blocking=False)
	assert lock_file is not None
	try:
		assert load_sessions(json_path, lock=False) == []
		save_sessions(json_path, [_session()], lock=False)
		assert len(load_sessions(json_path, lock=False)) == 1
	finally:
		release_file_lock(lock_file)

	# and the default (locking) path still works once the lock is free
	assert len(load_sessions(json_path)) == 1


# --- the document readers get ---------------------------------------------

import asyncio
import types

from analyzer import ANALYZER_VERSION, DB_ANALYSIS_KEYS, SCHEMA_VERSION, db_document, process_photo


def test_db_document_filters_to_reader_keys_and_stamps_version():
	distilled = {"closest_object_distance": 3.0, "farthest_object_distance": 2000.0, "time_of_day": "day",
				 "location_type": "outdoors", "scenic_score": 4, "visibility_distance": "far",
				 "tallest_building": "low_rise", "features": ["hill"],
				 # analyzer-internal, never written
				 "description": "x", "image_url": "u", "closest_object": {"description": "bench"},
				 "farthest_object": {"description": "hill"}, "focal_length_35mm": None}
	doc = db_document(distilled)
	assert doc["schema_version"] == SCHEMA_VERSION
	assert doc["analyzer_version"] == ANALYZER_VERSION
	assert set(doc) == set(DB_ANALYSIS_KEYS) | {"schema_version", "analyzer_version"}


def _photo():
	return types.SimpleNamespace(id="p", original_filename="p.jpg", file_md5="md5x", analysis=None, exif_data=None,
								 sizes={"640_llm": {"url": "http://example.invalid/p.jpg"}})


def _fake_run_analysis(fail_features: bool):
	"""Stand-in for the OpenRouter call: answers each pass from the prompt text, no network."""
	calls = []

	def run(model, image_url, final_image_url, image_hash, prompt_text, verbose):
		calls.append(prompt_text)
		is_distances = "farthest_object" in prompt_text
		if not is_distances and fail_features:
			return _session(model=model, prompt=prompt_text, parse_error=True)
		analysis = ({"farthest_object": {"description": "hill", "distance_category": "kilometers", "distance_estimate": "2 km"},
					 "closest_object": {"description": "bench", "distance_category": "meters", "distance_estimate": "3 m"}}
					if is_distances else
					{"time_of_day": "day", "location_type": "outdoors", "features": {"hill": True, "street": False},
					 "scenic_score": 4, "visibility_distance": "far", "tallest_building": "low_rise"})
		s = _session(model=model, prompt=prompt_text)
		s["analysis"] = analysis
		return s

	run.calls = calls
	return run


def _run(monkeypatch, datadir, fake):
	monkeypatch.setattr(analyzer, "check_image", lambda url: True)   # no HEAD request
	monkeypatch.setattr(analyzer, "run_analysis", fake)
	assert analyzer.FETCH_IMAGES is False                              # prepare_image_url then does no fetch
	return asyncio.run(process_photo(_photo(), datadir, MODEL, verbose=False))


def test_complete_run_writes_a_stamped_document(tmp_path, monkeypatch):
	fake = _fake_run_analysis(fail_features=False)
	outcome = _run(monkeypatch, tmp_path, fake)
	assert outcome.kind == 'ok'
	assert outcome.analysis["analyzer_version"] == ANALYZER_VERSION
	assert outcome.analysis["schema_version"] == SCHEMA_VERSION
	assert outcome.analysis["closest_object_distance"] == 3.0
	assert outcome.analysis["features"] == ["hill"]
	assert len(fake.calls) == 2
	assert len(load_sessions(tmp_path / "md5x.json")) == 2

	# second run: everything cached, no calls, same document
	again = _run(monkeypatch, tmp_path, fake)
	assert len(fake.calls) == 2
	assert again.analysis == outcome.analysis


def test_incomplete_run_writes_nothing_and_counts_attempts_from_the_file(tmp_path, monkeypatch):
	fake = _fake_run_analysis(fail_features=True)
	first = _run(monkeypatch, tmp_path, fake)
	assert first.kind == 'junk'
	assert first.analysis is None          # readers never see a partial result
	assert first.junk_attempts == 1
	assert len(fake.calls) == 2

	second = _run(monkeypatch, tmp_path, fake)
	assert second.kind == 'junk'
	assert second.junk_attempts == 2       # the file accumulated the failed attempt
	assert len(fake.calls) == 3            # only the failed pass was re-queried; distances were cached
