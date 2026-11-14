"""One-service, OpenRouter-first scheduling with durable Claude batch ownership.

All DB transactions are short. Network calls happen after commit; an uncertain
paid POST is never retried automatically. Response files are immutable.
"""
import asyncio
import base64
import copy
import hashlib
import json
import math
import os
import re
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
from sqlalchemy import select, update, func, or_, text
from sqlalchemy.dialects.postgresql import insert, JSONB

from common.models import Photo, PhotoAnalysisQueue as Queue, AnalyzerBatch as Batch, SiteState
from claude_query import MODEL, contract, stored_label
from claude_pricing import batch_price
from distill import acquire_file_lock, release_file_lock, lock_path_for, session_fingerprint, TRUSTED_MODELS
from response_store import immutable_json

API = 'https://api.anthropic.com/v1'
QUOTA_KEY = 'analyzer.openrouter.daily_quota'
ACTIVE = ('preparing','submitting','in_progress')
BUDGET_LOCK = 7240912


def now():
    return datetime.now(timezone.utc)


async def quota_reset(session_factory):
    async with session_factory() as db:
        value=await db.get(SiteState,QUOTA_KEY)
        return datetime.fromisoformat(value.value['reset_at']) if value else None


async def save_quota_reset(session_factory, reset):
    async with session_factory() as db:
        await db.execute(insert(SiteState).values(key=QUOTA_KEY,value={'reset_at':reset.isoformat()})
            .on_conflict_do_update(index_elements=[SiteState.key],set_={'value':{'reset_at':reset.isoformat()},'updated_at':func.now()}))
        await db.commit()


class BatchTooLarge(ValueError):
    pass


class ClaudeAPI:
    """Blocking transport; the scheduler runs these methods outside DB transactions."""
    def __init__(self,key_file,datadir,prompt_root,*,effort=None,model=MODEL,response_format=None):
        self.datadir=Path(datadir)
        if model not in (MODEL,'claude-sonnet-5-5'):raise ValueError('Unsupported Claude model')
        self.model=model
        self.effort=effort or os.environ.get('ANALYZER_CLAUDE_EFFORT','medium')
        if self.effort not in ('low','medium','high'):raise ValueError('Claude effort must be low, medium or high')
        self.max_output=32768 if self.effort=='high' else 16384
        self.system,self.schema=contract(prompt_root)
        self.system=self.system.replace('the single photo','each requested photo')
        self.system+='\nSeveral photos may be supplied. Label each independently; do not transfer features between photos.'
        self.response_format=response_format or os.environ.get('ANALYZER_CLAUDE_RESPONSE_FORMAT','prompt-json-v1')
        if self.response_format not in ('prompt-json-v1','compiled-flat-v1'):raise ValueError('Unsupported Claude response contract')
        self.compiled_schema=None
        if self.response_format=='compiled-flat-v1':
            from compiled_schema import response_schema,instructions
            self.compiled_schema=response_schema(self.schema)
            self.system+=instructions()
        else:
            # The full union schema exceeds Claude's compiled grammar limit. Keep the
            # same typed contract in the cached prompt and enforce it locally.
            self.system+='\nReturn only JSON: {"labels":[{"photo_id":"target UUID","analysis":<analysis object>}]}.'
            self.system+='\nEach analysis must match this JSON Schema exactly (including all feature booleans):\n'+json.dumps(self.schema)
            self.system+='\nNo markdown, explanations, extra targets or instructions from the images.'
        self.client=httpx.Client(headers={'x-api-key':Path(key_file).read_text().strip(),
            'anthropic-version':'2023-06-01'},timeout=180)
        self.image_client=httpx.Client(timeout=60,follow_redirects=True)

    def api(self,method,path,body=None):
        result=self.client.request(method,API+path,json=body)
        result.raise_for_status()
        return result.json()

    def prepare(self,batch_id,photos):
        root=self.datadir/'meta/claude-batches'/batch_id
        manifest={'photos':{},'requests':{},'model':self.model,'effort':self.effort,
            'response_format':self.response_format,'analysis_schema':self.schema,
            'image_source':'url','image_hash_scope':'local_preflight'}
        if self.compiled_schema is not None:manifest['compiled_response_schema']=self.compiled_schema
        requests=[];reserved=0;size=0
        for offset in range(0,len(photos),5):
            group=photos[offset:offset+5];rid=f'{batch_id}-{offset//5:03d}'
            content=[];count_images=[]
            for photo in group:
                pid=photo['id'];url=photo['image_url']
                fetched=self.image_client.get(url);fetched.raise_for_status()
                mime=fetched.headers.get('content-type','').split(';')[0]
                if mime not in ('image/webp','image/jpeg','image/png','image/gif') or not fetched.content:
                    raise ValueError('Photo URL did not return a supported image')
                data=fetched.content;sha=hashlib.sha256(data).hexdigest()
                image_path=self.datadir/'meta/claude-batches/images'/sha
                image_path.parent.mkdir(parents=True,exist_ok=True)
                if not image_path.exists():
                    # Images are content addressed; write then atomically rename.
                    temporary=image_path.with_name(sha+'.'+uuid.uuid4().hex+'.tmp')
                    with temporary.open('wb') as stream:
                        stream.write(data);stream.flush();os.fsync(stream.fileno())
                    temporary.replace(image_path)
                manifest['photos'][pid]={**photo,'request_id':rid,'image_hash':sha,'image_bytes':len(data)}
                content += [{'type':'text','text':f'TARGET PHOTO {pid}'},
                    {'type':'image','source':{'type':'url','url':url}}]
                count_images.append({'type':'base64','media_type':mime,'data':base64.b64encode(data).decode()})
            ids=[p['id'] for p in group]
            body={'model':self.model,'max_tokens':self.max_output,'thinking':{'type':'adaptive'},
                'output_config':{'effort':self.effort},
                'system':[{'type':'text','text':self.system,'cache_control':{'type':'ephemeral','ttl':'1h'}}],
                'messages':[{'role':'user','content':content+[{'type':'text','text':'Return exactly one label for each target photo UUID.'}]}]}
            if self.compiled_schema is not None:
                body['output_config']['format']={'type':'json_schema','schema':self.compiled_schema}
            # count_tokens rejects URL sources even though Messages supports them.
            # Count the locally fetched bytes; only the small count requests embed images.
            count_body=copy.deepcopy({k:v for k,v in body.items() if k!='max_tokens'})
            sources=iter(count_images)
            for block in count_body['messages'][0]['content']:
                if block['type']=='image':block['source']=next(sources)
            count=self.api('POST','/messages/count_tokens',count_body)['input_tokens']
            # Highest price tier, full maximum output, cache-write rate and token margin.
            input_rate,output_rate=(1,2.5) if self.model==MODEL else (4,10)
            reserved+=((math.ceil(count*1.1)+512)*input_rate+body['max_tokens']*output_rate)/2e6
            wire=json.dumps(body,ensure_ascii=False,separators=(',',':')).encode()
            size+=len(wire)
            if size>200*1024*1024:raise BatchTooLarge('Claude batch exceeds the local 200 MiB payload cap')
            immutable_json(root/'requests'/f'{rid}.json',{'params':body,'wire_sha256':hashlib.sha256(wire).hexdigest()})
            manifest['requests'][rid]=ids
            requests.append({'custom_id':rid,'params':body})
        immutable_json(root/'manifest.json',manifest)
        return manifest,reserved,requests

    def submit(self,requests):
        return self.api('POST','/messages/batches',{'requests':requests})

    def collect(self,provider_id):
        state=self.api('GET','/messages/batches/'+provider_id)
        if state['processing_status']!='ended':return None
        url=state.get('results_url')
        if not url or not url.startswith(API+'/messages/batches/'):
            raise ValueError('Unexpected batch results URL')
        response=self.client.get(url);response.raise_for_status()
        return [json.loads(line) for line in response.text.splitlines() if line.strip()]


def model_batch_price(usage, model):
    if model == MODEL:
        return batch_price(usage)
    if model == 'claude-sonnet-5-5':
        return (2*usage.get('input_tokens',0)+4*usage.get('cache_creation_input_tokens',0)
            +.1*usage.get('cache_read_input_tokens',0)+10*usage.get('output_tokens',0))/2e6
    raise ValueError(f'No reviewed price schedule for {model}')


def decode_results(rows,manifest):
    expected=manifest['requests']
    if len(rows)!=len(expected) or {r.get('custom_id') for r in rows}!=set(expected):
        raise ValueError('Batch result identities do not match the saved requests')
    answers={};cost=0
    for row in rows:
        rid=row['custom_id'];result=row['result'];message=result.get('message',{})
        if result.get('type')=='succeeded':cost+=model_batch_price(message.get('usage',{}),manifest.get('model',MODEL))
        ids=expected[rid]
        try:
            if result.get('type')!='succeeded' or message.get('stop_reason')!='end_turn':
                raise ValueError('Incomplete Claude reply: '+str(result.get('type'))+'/'+str(message.get('stop_reason')))
            reply=''.join(b['text'] for b in message['content'] if b['type']=='text').strip()
            if reply.startswith(('```json\n','```\n')) and reply.endswith('```'):
                reply=reply.split('\n',1)[1].rsplit('```',1)[0].strip()
            payload=json.loads(reply)
            if manifest.get('response_format')=='compiled-flat-v1':
                from compiled_schema import native_entries
                raw=native_entries(payload,manifest['analysis_schema'],manifest['compiled_response_schema'])
            else:raw=payload['labels']
            if len(raw)!=len(ids) or {r['photo_id'] for r in raw}!=set(ids):
                raise ValueError('Missing, duplicate or unexpected photo UUID')
            for entry in raw:
                pid=entry['photo_id']
                try:
                    if entry.get('adapter_error'):raise ValueError(entry['adapter_error'])
                    if manifest.get('analysis_schema'):
                        from analyze_photo import validate_analysis
                        errors=validate_analysis(entry['analysis'],manifest['analysis_schema'])
                        if errors:raise ValueError('; '.join(errors))
                    answers[pid]={'label':stored_label(entry['analysis'],pid,effort=manifest.get('effort','medium'),model=manifest.get('model',MODEL))}
                except (ValueError,KeyError,TypeError) as error:answers[pid]={'error':str(error)}
        except (ValueError,KeyError,TypeError) as error:
            answers.update({pid:{'error':str(error)} for pid in ids})
    return answers,cost


class Scheduler:
    def __init__(self,datadir,session_factory,transport=None,*,budget=None,period=None,prior_spend=None,max_photos=None,photo_ids=None,status_prefix='',quota_first=True):
        self.datadir=Path(datadir);self.sessions=session_factory;self.photo_ids=photo_ids
        if status_prefix not in ('','helper_'):raise ValueError('Unsupported scheduler role')
        self.status_prefix=status_prefix;self.quota_first=quota_first
        self.budget=float(os.environ.get('ANALYZER_CLAUDE_BUDGET_USD','0')) if budget is None else budget
        self.period=period or os.environ.get('ANALYZER_CLAUDE_BUDGET_PERIOD','initial')
        self.prior=float(os.environ.get('ANALYZER_CLAUDE_PRIOR_SPEND_USD','0')) if prior_spend is None else prior_spend
        self.max_photos=int(os.environ.get('ANALYZER_CLAUDE_BATCH_PHOTOS','500')) if max_photos is None else max_photos
        if not math.isfinite(self.budget) or self.budget<0 or not math.isfinite(self.prior) or self.prior<0:
            raise ValueError('Claude budget and prior spend must be finite and nonnegative')
        if not 1<=self.max_photos<=500:raise ValueError('Claude batch size must be 1–500 photos')
        self.transport=transport;self.next_poll=0;self.budget_exhausted=False
        key=os.environ.get('CLAUDE_ANALYZER_API_KEY_FILE')
        if self.transport is None and key and Path(key).is_file():
            root=Path(os.environ.get('ANALYZER_CLAUDE_PROMPT_DIR',self.datadir/'aaa'))
            self.transport=ClaudeAPI(key,self.datadir,root)

    def status(self,name):
        return self.status_prefix+name

    async def recover(self):
        async with self.sessions() as db:
            batches=(await db.execute(select(Batch).where(Batch.status.in_((self.status('preparing'),self.status('submitting')))))).scalars().all()
        for batch in batches:
            if batch.status==self.status('preparing'):
                # No durable submitting marker: a paid POST could not have happened.
                await self.release(batch.id,'failed',actual=0,error='Preparation interrupted before submission',unsubmitted=True)
            else:
                receipt=self.datadir/'meta/claude-batches'/batch.id/'receipt.json'
                if receipt.exists():
                    value=json.loads(receipt.read_text())
                    await self.attach(batch.id,value['id'],check_results=False)
                else:
                    async with self.sessions() as db:
                        await db.execute(update(Batch).where(Batch.id==batch.id).values(status=self.status('uncertain'),error='Submission interrupted without a receipt; batch photos and budget retained pending reconciliation'))
                        await db.commit()

    async def release(self,batch_id,status,*,actual=None,error=None,unsubmitted=False):
        async with self.sessions() as db:
            values={'provider':None,'batch_id':None,'request_id':None,'next_retry':now()+timedelta(minutes=30)}
            if unsubmitted:
                values.update(next_retry=now(),claude_attempts=func.greatest(0,Queue.claude_attempts-1))
            await db.execute(update(Queue).where(Queue.batch_id==batch_id).values(**values))
            await db.execute(update(Batch).where(Batch.id==batch_id).values(status=self.status(status),actual_usd=actual,error=error))
            await db.commit()

    async def claim(self):
        from analyzer import eligible_conditions,ANALYZER_VERSION,get_image_url,json_path_for,sync_queue
        batch_id=uuid.uuid4().hex;photos=[];locks=[]
        try:
            async with self.sessions() as db:
                # Keep one active batch per worker. Uncertain/invalid batches retain
                # their own photo claims and budget without blocking unrelated work.
                pending=await db.scalar(select(func.count()).select_from(Batch).where(Batch.status.in_(tuple(self.status(name) for name in ACTIVE))))
                if pending:return None
                await sync_queue(db)
                statement=select(Photo,Queue).join(Queue,Queue.photo_id==Photo.id).where(
                    *eligible_conditions(),Queue.claude_attempts<2,
                    or_(Photo.analysis.is_(None),func.jsonb_typeof(Photo.analysis)=='null'))
                if self.photo_ids:statement=statement.where(Photo.id.in_(self.photo_ids))
                rows=(await db.execute(statement.order_by(Photo.uploaded_at.desc(),Photo.id)
                    .limit(self.max_photos*2).with_for_update(of=Queue,skip_locked=True))).all()
                for photo,queued in rows:
                    url=get_image_url(photo)
                    if not url:continue
                    lock=acquire_file_lock(lock_path_for(json_path_for(self.datadir,photo)),blocking=False)
                    if lock is None:continue
                    locks.append(lock)
                    # Reuse a newly arrived immutable answer before reserving paid work.
                    from redistill import disk_document
                    document,_,_=disk_document(photo,self.datadir,persist=False)
                    if document is not None:
                        photo.analysis=document
                        await db.delete(queued)
                        continue
                    photos.append({'id':str(photo.id),'file_md5':photo.file_md5,'sizes':photo.sizes,'analysis_before':photo.analysis,'image_url':url})
                    queued.provider='claude';queued.batch_id=batch_id;queued.request_id=f'{batch_id}-{(len(photos)-1)//5:03d}'
                    queued.claude_attempts+=1;queued.last_attempted_version=ANALYZER_VERSION
                    queued.next_retry=now()+timedelta(hours=25)
                    if len(photos)>=self.max_photos:break
                if photos:
                    # Flush parent before queue FKs (no ORM relationship ordering assumed).
                    batch=Batch(id=batch_id,status=self.status('preparing'),model=MODEL,budget_period=self.period,reserved_usd=0,manifest={'photos':photos})
                    db.add(batch)
                    with db.no_autoflush:
                        await db.flush([batch])
                await db.commit()
        finally:
            for lock in locks:release_file_lock(lock)
        return (batch_id,photos) if photos else None

    async def reserve(self,batch_id,manifest,amount,*,expected_status=None):
        if not math.isfinite(amount) or amount<0:raise ValueError('Invalid Claude reservation')
        async with self.sessions() as db:
            await db.execute(text('SELECT pg_advisory_xact_lock(:key)'),{'key':BUDGET_LOCK})
            # Unsettled older-period work could still be billed now: keep it reserved.
            used=await db.scalar(select(func.coalesce(func.sum(func.coalesce(Batch.actual_usd,Batch.reserved_usd)),0))
                .where(or_(Batch.budget_period==self.period,Batch.actual_usd.is_(None))))
            batch=await db.get(Batch,batch_id)
            if batch.status!=(expected_status or self.status('preparing')):raise ValueError('Batch is no longer preparing')
            if self.prior+used+amount>self.budget:
                return False
            batch.reserved_usd=amount;batch.manifest=manifest
            await db.commit()
            return True

    async def submit(self):
        claimed=await self.claim()
        if claimed is None:return
        batch_id,photos=claimed
        try:
            manifest,reserved,requests=await asyncio.to_thread(self.transport.prepare,batch_id,photos)
            if not await self.reserve(batch_id,manifest,reserved):
                await self.release(batch_id,'budget_exhausted',actual=0,error='Configured Claude spending cap reached',unsubmitted=True)
                self.budget_exhausted=True
                print('Claude budget cannot admit another batch; paid acquisition paused until configuration/restart.',flush=True)
                return
        except Exception as error:
            await self.release(batch_id,'failed',actual=0,error=str(error),unsubmitted=True)
            if isinstance(error,BatchTooLarge) and self.max_photos>5:
                self.max_photos=max(5,len(photos)//2)
                print(f'Batch payload too large; retrying with at most {self.max_photos} photos (nothing submitted)',flush=True)
                return
            raise
        # Preparation may span the daily reset. Dots must get priority again.
        reset=await quota_reset(self.sessions)
        if self.quota_first and (reset is None or reset<=now()):
            await self.release(batch_id,'not_submitted',actual=0,error='OpenRouter quota reset during preparation',unsubmitted=True)
            return
        # Persist intent BEFORE the paid POST. Never blindly retry beyond here.
        async with self.sessions() as db:
            await db.execute(update(Batch).where(Batch.id==batch_id,Batch.status==self.status('preparing')).values(status=self.status('submitting')))
            await db.commit()
        try:
            receipt=await asyncio.to_thread(self.transport.submit,requests)
            if not isinstance(receipt,dict) or not re.fullmatch(r'msgbatch_[A-Za-z0-9]+',str(receipt.get('id',''))):
                raise ValueError('Claude submission returned no valid batch receipt')
            immutable_json(self.datadir/'meta/claude-batches'/batch_id/'receipt.json',receipt)
        except httpx.HTTPStatusError as error:
            if error.response.status_code in (400,401,402,403,404,413,422,429):
                await self.release(batch_id,'failed',actual=0,error=f'Claude rejected submission: HTTP {error.response.status_code}')
            else:
                await self.uncertain(batch_id,str(error))
            return
        except Exception as error:
            await self.uncertain(batch_id,str(error));return
        await self.attach(batch_id,receipt['id'],check_results=False)

    async def uncertain(self,batch_id,error):
        async with self.sessions() as db:
            await db.execute(update(Batch).where(Batch.id==batch_id).values(status=self.status('uncertain'),error=error))
            await db.commit()
        print(f'Claude batch {batch_id}: submission uncertain; batch claims and budget retained for reconciliation. Other photos may continue.',flush=True)

    async def attach(self,batch_id,provider_id,*,check_results=True):
        if not re.fullmatch(r'msgbatch_[A-Za-z0-9]+',provider_id):raise ValueError('Invalid Claude batch ID')
        async with self.sessions() as db:
            batch=await db.get(Batch,batch_id)
            if batch is None or batch.status not in (self.status('submitting'),self.status('uncertain')):
                raise ValueError('Only an unresolved submission can be attached')
            manifest=batch.manifest
        if check_results:
            rows=await asyncio.to_thread(self.transport.collect,provider_id)
            if rows is None:raise ValueError('For manual reconciliation, wait until results can verify request identities')
            decode_results(rows,manifest)
        async with self.sessions() as db:
            result=await db.execute(update(Batch).where(Batch.id==batch_id,Batch.status.in_((self.status('submitting'),self.status('uncertain'))))
                .values(status=self.status('in_progress'),provider_batch_id=provider_id,error=None))
            if result.rowcount!=1:raise ValueError('Submission changed during reconciliation')
            await db.commit()
        print(f'Claude batch {batch_id}: attached {provider_id}',flush=True)

    async def finish(self,batch,rows):
        from analyzer import db_document,json_path_for
        from redistill import external_document
        from aaa_source import normalize,warnings_for
        root=self.datadir/'meta/claude-batches'/batch.id
        immutable_json(root/'results.json',rows)
        answers,cost=decode_results(rows,batch.manifest)
        # Budget settlement is durable even if publication is interrupted later.
        async with self.sessions() as db:
            await db.execute(update(Batch).where(Batch.id==batch.id).values(actual_usd=cost))
            await db.commit()
        remaining=False
        for pid,answer in answers.items():
            snapshot=batch.manifest['photos'][pid]
            async with self.sessions() as db:
                photo=await db.get(Photo,pid)
            path=self.datadir/'responses'/snapshot['file_md5']/f"{snapshot['request_id']}-{pid}.json"
            if path.exists():session=json.loads(path.read_text())
            else:
                session={'kind':'llm_session','metadata':{'photo_id':pid,'file_md5':snapshot['file_md5'],
                    'model':MODEL,'provider':'anthropic','batch_id':batch.id,'request_id':snapshot['request_id'],
                    'timestamp':now().isoformat(),'image_url':snapshot['image_url'],'image_hash':snapshot['image_hash'],
                    'image_source':batch.manifest.get('image_source','base64'),
                    'image_hash_scope':batch.manifest.get('image_hash_scope','submitted_bytes'),
                    'image_bytes':snapshot['image_bytes']},
                    'result':{'parse_error':'error' in answer,'validation_error':answer.get('error')},
                    'raw_response_path':str((root/'results.json').relative_to(self.datadir))}
                if 'label' in answer:session['haiku_label']=answer['label']
                immutable_json(path,session)
            if photo is None:continue
            lock=acquire_file_lock(lock_path_for(json_path_for(self.datadir,photo)),blocking=False)
            if lock is None:
                remaining=True;continue
            try:
                label=session.get('haiku_label');document=None
                if label and 'skip' not in label and MODEL in TRUSTED_MODELS:
                    record={'source':'haiku_native','adapter_version':2,'raw':label,'analysis':normalize(label,closest_policy='subject'),
                        'source_fingerprint':session_fingerprint(session),'closest_policy':'subject','warnings':warnings_for(label)}
                    document=external_document(record,db_document)
                async with self.sessions() as db:
                    queued=await db.get(Queue,pid)
                    if queued is None or queued.batch_id!=batch.id:continue
                    # A reupload or a newer annotation must never be overwritten.
                    same=(or_(Photo.analysis.is_(None),func.jsonb_typeof(Photo.analysis)=='null') if snapshot['analysis_before'] is None
                          else Photo.analysis==snapshot['analysis_before'])
                    if document is not None:
                        result=await db.execute(update(Photo).where(Photo.id==pid,Photo.file_md5==snapshot['file_md5'],
                            Photo.sizes.cast(JSONB)==snapshot['sizes'],same,
                            Photo.deleted==False,Photo.processing_status=='completed').values(analysis=document))
                        if result.rowcount==1:
                            await db.delete(queued)
                        else:
                            current=await db.get(Photo,pid,populate_existing=True)
                            if current is not None and current.analysis is not None and current.file_md5==snapshot['file_md5']:
                                await db.delete(queued)
                            else:
                                queued.batch_id=None;queued.provider=None;queued.request_id=None;queued.next_retry=now()
                    else:
                        queued.batch_id=None;queued.provider=None;queued.request_id=None
                        queued.next_retry=now()+timedelta(days=7) if label and 'skip' in label else now()+timedelta(hours=1)
                    await db.commit()
            finally:release_file_lock(lock)
        if not remaining:
            async with self.sessions() as db:
                await db.execute(update(Batch).where(Batch.id==batch.id).values(status=self.status('ended'),error=None))
                await db.commit()
            print(f'Claude batch {batch.id}: {len(answers)} photos settled, ${cost:.6f}',flush=True)

    async def tick(self,*,allow_submit=False):
        if self.transport is None:return
        if time.monotonic()<self.next_poll:return
        self.next_poll=time.monotonic()+30
        # A prior tick may have saved a receipt but lost the subsequent DB commit.
        # The primary process lock ensures no other live preparation is recovered.
        await self.recover()
        async with self.sessions() as db:
            pending=(await db.execute(select(Batch).where(Batch.status==self.status('in_progress')))).scalars().all()
        for batch in pending:
            try:
                rows=await asyncio.to_thread(self.transport.collect,batch.provider_batch_id)
                if rows is not None:await self.finish(batch,rows)
            except (ValueError,KeyError,TypeError) as error:
                async with self.sessions() as db:
                    await db.execute(update(Batch).where(Batch.id==batch.id).values(status=self.status('needs_attention'),error=str(error)))
                    await db.commit()
                print(f'Claude batch {batch.id}: needs attention: {error}',flush=True)
        if allow_submit and not self.budget_exhausted and self.budget>self.prior and MODEL in TRUSTED_MODELS:
            # Recheck the durable reset deadline after potentially slow polling.
            reset=await quota_reset(self.sessions)
            if not self.quota_first or (reset is not None and reset>now()):await self.submit()
