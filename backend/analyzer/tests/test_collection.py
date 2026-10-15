"""Acquisition remains independent of trusted production distillation."""
import asyncio
import copy
from unittest.mock import patch

import httpx
import pytest

import analyzer
import analyze_photo
import distill
from test_retry import _fake_run_analysis, _photo, MODEL

CANDIDATE = "google/gemma-4-26b-a4b-it:free"


def test_candidate_is_recorded_and_cached_without_distillation(tmp_path, monkeypatch):
    monkeypatch.setattr(analyzer, "check_image", lambda url: True)
    fake = _fake_run_analysis(fail_features=False)
    monkeypatch.setattr(analyzer, "run_analysis", fake)
    photo = _photo()
    baseline = asyncio.run(analyzer.process_photo(photo, tmp_path, MODEL, False))
    trusted = copy.deepcopy(distill.load_sessions(tmp_path / "md5x.json"))
    assert baseline.kind == "ok"
    with patch.object(analyzer, "distill_sessions", side_effect=AssertionError("candidate must not distill")):
        candidate = asyncio.run(analyzer.process_photo(photo, tmp_path, CANDIDATE, False))
        again = asyncio.run(analyzer.process_photo(photo, tmp_path, CANDIDATE, False))
    assert candidate.kind == "collected" and candidate.analysis is None and candidate.queried
    assert again.kind == "collected" and not again.queried
    history = distill.load_sessions(tmp_path / "md5x.json")
    assert len(history) == 4 and history[:2] == trusted
    assert distill.distill_sessions(history) == distill.distill_sessions(trusted)
    assert distill.distill_sessions(history[2:]) is None
    with patch.object(distill, "TRUSTED_MODELS", (*distill.TRUSTED_MODELS, CANDIDATE)):
        assert distill.distill_sessions(history[2:]) is not None
    assert distill.distill_sessions(history[2:]) is None


def test_first_pass_survives_second_pass_exception(tmp_path, monkeypatch):
    monkeypatch.setattr(analyzer, "check_image", lambda url: True)
    fake = _fake_run_analysis(fail_features=False)
    def run(*args, **kwargs):
        if "farthest_object" in kwargs["prompt_text"]:
            raise RuntimeError("provider unavailable")
        return fake(*args, **kwargs)
    monkeypatch.setattr(analyzer, "run_analysis", run)
    with pytest.raises(RuntimeError):
        asyncio.run(analyzer.process_photo(_photo(), tmp_path, CANDIDATE, False))
    assert len(distill.load_sessions(tmp_path / "md5x.json")) == 1


def test_transport_failure_is_recorded():
    with patch.object(analyze_photo, "call_openrouter_api", side_effect=RuntimeError("provider down")):
        session = analyze_photo.run_analysis(CANDIDATE, "url", "url", None, "prompt", False)
    assert session["metadata"]["model"] == CANDIDATE
    assert session["result"]["parse_error"]
    assert session["result"]["error"] == "provider down"
    assert session["result"]["cost"] is None


def test_502_retries_are_bounded():
    response = httpx.Response(502, request=httpx.Request("POST", "https://example.invalid"))
    with patch.object(analyze_photo, "get_api_key", return_value="test"), patch.object(analyze_photo.httpx, "Client") as client, patch.object(analyze_photo.time, "sleep"):
        client.return_value.__enter__.return_value.post.return_value = response
        with pytest.raises(httpx.HTTPStatusError):
            analyze_photo.call_openrouter_api({})
        assert client.return_value.__enter__.return_value.post.call_count == 3


def test_update_collection_uses_db_selection_without_publication(tmp_path, monkeypatch):
    from unittest.mock import AsyncMock
    photo = _photo()
    photo.analysis = {"closest_object_distance": 30}
    lock = distill.acquire_file_lock(distill.lock_path_for(tmp_path / "md5x.json"))
    select_photo = AsyncMock(side_effect=[(photo, lock), None])
    publish = AsyncMock(side_effect=AssertionError("candidate must not publish"))
    sync = AsyncMock(side_effect=AssertionError("candidate must not sync production queue"))
    monkeypatch.setattr(analyzer, "claim_refresh", select_photo)
    monkeypatch.setattr(analyzer, "record_outcome", publish)
    monkeypatch.setattr(analyzer, "sync_queue", sync)
    monkeypatch.setattr(analyzer, "check_image", lambda url: True)
    monkeypatch.setattr(analyzer, "run_analysis", _fake_run_analysis(fail_features=False))
    monkeypatch.setattr(analyzer.asyncio, "sleep", AsyncMock())
    asyncio.run(analyzer.main_loop(tmp_path, CANDIDATE, False, True, 30, prefer="update"))
    assert select_photo.await_count == 2
    assert select_photo.call_args_list[0].args[2] == "update"
    publish.assert_not_awaited()
    sync.assert_not_awaited()
    assert photo.analysis == {"closest_object_distance": 30}
