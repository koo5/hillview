import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from batch_scheduler import ClaudeAPI, Scheduler, is_credit_exhaustion


@pytest.mark.parametrize('message,unavailable', [
    ('model is no longer available on OpenRouter: no provider serves this model anymore', True),
    ('No endpoints found that support image URLs', True),
    ('Image could not be downloaded: 404 Not Found', False),
])
def test_model_removal_is_distinct_from_an_image_404(monkeypatch,message,unavailable):
    import analyze_photo
    import analyzer
    response=httpx.Response(404,json={'error':{'message':message}},request=httpx.Request('POST','https://openrouter.ai/api/v1/chat/completions'))
    def fail(*args,**kwargs):raise httpx.HTTPStatusError('404',request=response.request,response=response)
    monkeypatch.setattr(analyze_photo,'call_openrouter_api',fail)
    session=analyze_photo.run_analysis('test/model','url','url',None,'prompt',False)
    assert (analyzer.request_error_outcome(session).kind=='model_unavailable') == unavailable


def test_removed_model_stops_acquisition_before_visiting_another_photo(tmp_path,monkeypatch,capsys):
    import analyzer
    from distill import acquire_file_lock,lock_path_for
    from test_retry import _photo,MODEL
    photo=_photo();lock=acquire_file_lock(lock_path_for(tmp_path/'md5x.json'))
    claim=AsyncMock(side_effect=[(photo,lock),None])
    monkeypatch.setattr(analyzer,'claim_refresh',claim)
    run=AsyncMock(return_value=analyzer.Outcome('model_unavailable',queried=True))
    monkeypatch.setattr(analyzer,'process_photo',run)
    asyncio.run(analyzer.main_loop(tmp_path,MODEL,False,True,30,collect_only=True))
    assert claim.await_count==1 and run.await_count==1
    assert 'acquisition paused' in capsys.readouterr().out

WORKSPACE_LIMIT = ('You have reached your specified workspace API usage limits. '
                   'You will regain access on 2026-12-01 at 00:00 UTC.')
LIMIT_RESET = datetime(2026, 12, 1, tzinfo=timezone.utc)


def scheduler_db(pending=()):
    db = MagicMock()
    db.__aenter__ = AsyncMock(return_value=db)
    db.__aexit__ = AsyncMock(return_value=False)
    result = MagicMock()
    result.scalars.return_value.all.return_value = list(pending)
    db.execute = AsyncMock(return_value=result)
    db.commit = AsyncMock()
    return MagicMock(return_value=db)


def test_repeated_400s_cool_down_one_exact_request_but_do_not_count_as_invalid_answers():
    from datetime import datetime, timedelta, timezone
    import analyzer
    from distill import count_failed_attempts
    from test_retry import _session, MODEL

    first=analyzer.request_error_outcome({'result':{'http_status':400,'error':'bad request'}})
    assert first.kind=='provider_rejected' and first.retry_at is not None
    stamp=datetime.now(timezone.utc)
    sessions=[]
    for _ in range(3):
        session=_session(model=MODEL,prompt='prompt',temperature=analyzer.TEMPERATURE,
                         max_tokens=analyzer.MAX_TOKENS,timestamp=stamp.isoformat(),parse_error=True)
        session['result'].update(error='Provider rejected request',http_status=400)
        sessions.append(session)
    outcome=analyzer.rejection_backoff(sessions,MODEL,'prompt',{'type':'json_object'})
    assert outcome.kind=='provider_rejected' and not outcome.queried
    assert analyzer.next_retry_for(outcome,stamp)==stamp+timedelta(days=1)
    assert count_failed_attempts(sessions,MODEL,'prompt',analyzer.TEMPERATURE,analyzer.MAX_TOKENS)==0
    assert analyzer.rejection_backoff(sessions,MODEL,'changed prompt',{'type':'json_object'}) is None
    for session in sessions:session['metadata']['timestamp']=(stamp-timedelta(days=2)).isoformat()
    assert analyzer.rejection_backoff(sessions,MODEL,'prompt',{'type':'json_object'}) is None


def test_openrouter_logs_upstream_rejection_without_calling_it_a_model_answer(monkeypatch,capsys):
    import json
    import analyze_photo
    body={'error':{'message':'Provider returned error','metadata':{'provider_name':'AtlasCloud',
          'raw':json.dumps({'code':400,'msg':'bad request','request_id':'test'})}}}
    response=httpx.Response(400,json=body,request=httpx.Request('POST','https://openrouter.ai/api/v1/chat/completions'))
    def fail(*args,**kwargs):raise httpx.HTTPStatusError('400',request=response.request,response=response)
    monkeypatch.setattr(analyze_photo,'call_openrouter_api',fail)
    session=analyze_photo.run_analysis('test/model','url','url',None,'prompt',False)
    message=capsys.readouterr().out
    assert 'no model answer' in message and 'AtlasCloud' in message and 'bad request' in message
    assert session['result']['provider_error']==body


def test_batch_summary_names_whole_batch_estimate_and_token_categories():
    from batch_scheduler import batch_completion_message
    answers={'a':{'label':{}},'b':{'label':{'skip':'blocked'}},'c':{'error':'invalid JSON'}}
    rows=[{'result':{'type':'succeeded','message':{'usage':{'input_tokens':1000,
        'cache_creation_input_tokens':2000,'cache_read_input_tokens':3000,'output_tokens':4000}}}}]
    message=batch_completion_message('batch',answers,rows,.163047,{'published':1,'retry deferred':2})
    assert '3 photo outcomes' in message and '1 valid, 1 skipped, 1 failed' in message
    assert 'input=1,000, cache_write=2,000, cache_read=3,000, output=4,000' in message
    assert 'DB this pass:' in message and '1 published' in message
    assert 'estimated cost for entire batch: $0.163047' in message
    assert '$0.054349/photo' in message


def rejected(message):
    response = httpx.Response(400, json={'error': {'type': 'invalid_request_error', 'message': message}},
                              headers={'request-id': 'test-request'},
                              request=httpx.Request('POST', 'https://api.anthropic.com/v1/messages/count_tokens'))
    return httpx.HTTPStatusError(message, request=response.request, response=response)


@pytest.mark.parametrize('message,credit', [
    ('Your credit balance is too low to access the Anthropic API.', True),
    ('output_config: invalid schema', False),
])
def test_provider_message_is_preserved_and_only_credit_errors_are_classified(message, credit):
    error = rejected(message)
    api = ClaudeAPI.__new__(ClaudeAPI)
    api.client = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(
        400, json=error.response.json(), headers={'request-id': 'test-request'})))
    try:
        with pytest.raises(httpx.HTTPStatusError) as caught:
            api.api('POST', '/messages/count_tokens', {})
        assert message in str(caught.value) and 'test-request' in str(caught.value)
        assert is_credit_exhaustion(caught.value) == credit
    finally:
        api.client.close()


def test_credit_failure_during_preparation_releases_unsent_claims_and_pauses(tmp_path, capsys):
    transport = MagicMock()
    transport.prepare.side_effect = rejected('Your credit balance is too low to access the Anthropic API.')
    scheduler = Scheduler(tmp_path, MagicMock(), transport, budget=100, prior_spend=0)
    scheduler.claim = AsyncMock(return_value=('batch', []))
    scheduler.release = AsyncMock()
    asyncio.run(scheduler.submit())
    assert scheduler.budget_exhausted
    transport.submit.assert_not_called()
    assert scheduler.release.await_args.kwargs['unsubmitted'] is True
    assert scheduler.release.await_args.kwargs['actual'] == 0
    output = capsys.readouterr()
    assert 'credit balance' in output.out and 'paused' in output.out
    assert 'Traceback' not in output.err


def test_workspace_limit_pauses_preparation_until_reset_but_keeps_collecting(tmp_path, monkeypatch, capsys):
    import batch_scheduler
    current = datetime(2026, 11, 18, tzinfo=timezone.utc)
    monkeypatch.setattr(batch_scheduler, 'now', lambda: current)
    monkeypatch.setattr(batch_scheduler, 'quota_reset', AsyncMock(return_value=None))
    transport = MagicMock()
    transport.prepare.side_effect = rejected(WORKSPACE_LIMIT)
    transport.collect.return_value = []
    pending = SimpleNamespace(provider_batch_id='msgbatch_existing')
    scheduler = Scheduler(tmp_path, scheduler_db([pending]), transport, budget=100, prior_spend=0, quota_first=False)
    scheduler.claim = AsyncMock(side_effect=[('batch', []), None])
    scheduler.release = AsyncMock()
    scheduler.recover = AsyncMock()
    scheduler.finish = AsyncMock()

    async def run():
        nonlocal current
        await scheduler.tick(allow_submit=True)
        assert scheduler.provider_resume_at == LIMIT_RESET
        assert not scheduler.budget_exhausted
        scheduler.next_poll = 0
        current = LIMIT_RESET - timedelta(seconds=1)
        await scheduler.tick(allow_submit=True)
        scheduler.claim.assert_awaited_once()
        assert transport.prepare.call_count == 1
        assert transport.collect.call_count == 2
        assert scheduler.finish.await_count == 2
        current = LIMIT_RESET
        scheduler.next_poll = 0
        await scheduler.tick(allow_submit=True)
        assert scheduler.claim.await_count == 2

    asyncio.run(run())
    transport.submit.assert_not_called()
    assert scheduler.release.await_args.kwargs['unsubmitted'] is True
    assert scheduler.release.await_args.kwargs['actual'] == 0
    output = capsys.readouterr()
    assert 'paused until 2026-12-01T00:00:00+00:00' in output.out
    assert 'Dots and collection of already-submitted batches continue' in output.out
    assert 'Traceback' not in output.err


def test_workspace_limit_at_submission_releases_reservation_and_pauses(tmp_path, monkeypatch):
    import batch_scheduler
    monkeypatch.setattr(batch_scheduler, 'now', lambda: datetime(2026, 11, 18, tzinfo=timezone.utc))
    monkeypatch.setattr(batch_scheduler, 'quota_reset', AsyncMock(return_value=None))
    transport = MagicMock()
    transport.prepare.return_value = ({}, 1.0, [])
    transport.submit.side_effect = rejected(WORKSPACE_LIMIT)
    scheduler = Scheduler(tmp_path, scheduler_db(), transport, budget=100, prior_spend=0, quota_first=False)
    scheduler.claim = AsyncMock(return_value=('batch', []))
    scheduler.reserve = AsyncMock(return_value=True)
    scheduler.release = AsyncMock()
    scheduler.uncertain = AsyncMock()
    scheduler.recover = AsyncMock()

    async def run():
        await scheduler.submit()
        await scheduler.tick(allow_submit=True)

    asyncio.run(run())
    assert scheduler.provider_resume_at == LIMIT_RESET
    scheduler.release.assert_awaited_once_with('batch', 'failed', actual=0,
        error=batch_scheduler.provider_error_message(transport.submit.side_effect.response))
    scheduler.uncertain.assert_not_awaited()
    assert transport.submit.call_count == 1
    scheduler.claim.assert_awaited_once()


@pytest.mark.parametrize('message', [
    'You have reached your specified workspace API usage limits.',
    'You have reached your specified workspace API usage limits. You will regain access on 2026-99-01 at 00:00 UTC.',
    'You have reached your specified workspace API usage limits. You will regain access on 2026-01-01 at 00:00 UTC.',
])
def test_workspace_limit_without_a_future_reset_requires_restart(tmp_path, monkeypatch, message, capsys):
    import batch_scheduler
    monkeypatch.setattr(batch_scheduler, 'now', lambda: datetime(2026, 11, 18, tzinfo=timezone.utc))
    transport = MagicMock()
    transport.prepare.side_effect = rejected(message)
    scheduler = Scheduler(tmp_path, scheduler_db(), transport, budget=100, prior_spend=0, quota_first=False)
    scheduler.claim = AsyncMock(return_value=('batch', []))
    scheduler.release = AsyncMock()
    scheduler.recover = AsyncMock()

    async def run():
        await scheduler.submit()
        await scheduler.tick(allow_submit=True)

    asyncio.run(run())
    assert scheduler.budget_exhausted
    scheduler.claim.assert_awaited_once()
    assert 'restart the analyzer' in capsys.readouterr().out


def test_other_preparation_errors_still_surface(tmp_path):
    transport = MagicMock()
    transport.prepare.side_effect = rejected('output_config: invalid schema')
    scheduler = Scheduler(tmp_path, scheduler_db(), transport, budget=100, prior_spend=0)
    scheduler.claim = AsyncMock(return_value=('batch', []))
    scheduler.release = AsyncMock()
    with pytest.raises(httpx.HTTPStatusError, match='invalid schema'):
        asyncio.run(scheduler.submit())
    assert not scheduler.budget_exhausted
