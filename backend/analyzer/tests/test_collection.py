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


def test_invalid_answer_limit_is_enforced_before_another_request(tmp_path, monkeypatch):
    fake = _fake_run_analysis(fail_features=True)
    monkeypatch.setattr(analyzer, 'run_analysis', fake)
    for _ in range(analyzer.MAX_JUNK_ATTEMPTS):
        asyncio.run(analyzer.process_photo(_photo(), tmp_path, MODEL, False))
    attempts = len(fake.calls)
    result = asyncio.run(analyzer.process_photo(_photo(), tmp_path, MODEL, False))
    assert result.kind == 'junk' and result.junk_attempts == analyzer.MAX_JUNK_ATTEMPTS
    assert not result.queried and len(fake.calls) == attempts


def test_photo_log_identifies_timestamps_owner_and_session_paths(tmp_path, monkeypatch, capsys):
    from datetime import datetime, timezone
    photo = _photo()
    photo.owner_id = 'owner-uuid'
    photo.record_created_ts = datetime(2026, 1, 2, tzinfo=timezone.utc)
    photo.captured_at = datetime(2026, 1, 1)
    photo.uploaded_at = datetime(2026, 1, 3, tzinfo=timezone.utc)
    monkeypatch.setattr(analyzer, 'run_analysis', _fake_run_analysis(fail_features=False))
    asyncio.run(analyzer.process_photo(photo, tmp_path, MODEL, False))
    output = capsys.readouterr().out
    assert '2026-01-02' in output and '2026-01-01' in output and '2026-01-03' in output
    assert 'MD5: md5x; user: owner-uuid' in output
    assert str(tmp_path/'md5x.json') in output
    assert str(tmp_path/'responses/md5x') in output


def test_explicit_image_fetch_cannot_attest_to_different_render(tmp_path, monkeypatch):
    photo = _photo()
    photo.sizes['640_llm']['sha256'] = 'a'*64
    monkeypatch.setattr(analyzer, 'prepare_image_url', lambda *args: ('data:image/webp;base64,bytes', 'b'*64))
    monkeypatch.setattr(analyzer, 'run_analysis', lambda **kwargs: pytest.fail('Mismatched bytes reached model'))
    with pytest.raises(analyzer.ImageAccessError, match='differs from its database checksum'):
        asyncio.run(analyzer.process_photo(photo, tmp_path, MODEL, False))


def test_changed_render_requeries_both_passes_and_preserves_old_history(tmp_path, monkeypatch):
    fake = _fake_run_analysis(fail_features=False)
    monkeypatch.setattr(analyzer, 'run_analysis', fake)
    photo = _photo()
    photo.sizes['640_llm']['sha256'] = 'a'*64
    asyncio.run(analyzer.process_photo(photo, tmp_path, MODEL, False))
    assert len(fake.calls) == 2
    asyncio.run(analyzer.process_photo(photo, tmp_path, MODEL, False))
    assert len(fake.calls) == 2
    photo.sizes['640_llm']['sha256'] = 'b'*64  # same MD5, UUID and URL
    asyncio.run(analyzer.process_photo(photo, tmp_path, MODEL, False))
    history = distill.load_sessions(tmp_path/'md5x.json')
    assert len(fake.calls) == 4 and len(history) == 4
    assert [s['metadata']['image_content_sha256'] for s in history] == ['a'*64]*2 + ['b'*64]*2


def test_model_coverage_skips_old_prompts_but_not_other_models_or_partial_answers(tmp_path, monkeypatch):
    def example(schema):
        if 'enum' in schema:return schema['enum'][0]
        kind=schema['type']
        if kind=='object':return {k:example(v) for k,v in schema['properties'].items()}
        if kind=='array':return []
        if kind=='boolean':return False
        if kind in ('number','integer'):return 1
        return 'visible subject'
    history=[{'metadata':{'model':MODEL},'result':{'parse_error':False},'analysis':example(analyzer.build_schema(distances=d,features=not d))}
             for d in (False,True)]
    distill.save_sessions(tmp_path / 'md5x.json', history)
    assert analyzer.model_has_complete_answer(history, MODEL)
    assert not analyzer.model_has_complete_answer(history, CANDIDATE)
    assert not analyzer.model_has_complete_answer(history[:1], MODEL)
    monkeypatch.setattr(analyzer, "run_analysis", lambda **kwargs: pytest.fail("Already-covered model was queried"))
    outcome = asyncio.run(analyzer.process_photo(_photo(), tmp_path, MODEL, False, skip_model_covered=True))
    assert outcome.kind == 'cached' and not outcome.queried


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
    asyncio.run(analyzer.main_loop(tmp_path, CANDIDATE, False, True, 30, prefer="update", collect_only=True))
    assert select_photo.await_count == 2
    assert select_photo.call_args_list[0].args[2] == "update"
    publish.assert_not_awaited()
    sync.assert_not_awaited()
    assert photo.analysis == {"closest_object_distance": 30}


def test_primary_backfills_before_counting_gaps(tmp_path, monkeypatch, capsys):
    from unittest.mock import AsyncMock, MagicMock
    import redistill
    events = []
    async def backfill(args):
        assert args.missing_only and not args.dry_run
        events.append('backfill')
        return 0
    async def execute(stmt):
        events.append('count')
        result = MagicMock()
        result.one.return_value = (100, 20, 19) if len(events) == 1 else (100, 12, 11)
        return result
    db = MagicMock()
    db.execute = AsyncMock(side_effect=execute)
    context = MagicMock()
    context.__aenter__ = AsyncMock(return_value=db)
    context.__aexit__ = AsyncMock(return_value=False)
    monkeypatch.setattr(redistill, 'run', backfill)
    monkeypatch.setattr(analyzer, 'SessionLocal', lambda: context)
    assert asyncio.run(analyzer.startup_backfill(tmp_path)) == (100, 12)
    assert events == ['count', 'backfill', 'count']
    output = capsys.readouterr().out
    assert 'missing analyses: 20; rows to check against disk: 19; missing upload hash: 1' in output
    assert 'missing analyses: 12' in output
