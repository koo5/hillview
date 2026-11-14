"""Resumable, budget-limited continuing-context acquisition through batch rounds.

No database writes and no model tools. Candidates never enter golden/labels.
"""
import argparse
import base64
import copy
import hashlib
import json
import shutil
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import httpx

from aaa_source import normalize, warnings_for
from claude_pilot import Runner, MODEL, API, params, prefix, user_content, price, write
from distill import file_lock


def load(path, default=None):
    return json.loads(path.read_text()) if path.exists() else default


def chunks(seqs, size=20):
    groups = []
    for seq in seqs:
        if not groups or len(groups[-1]) >= size or seq != groups[-1][-1] + 1:
            groups.append([])
        groups[-1].append(seq)
    return groups


def strengthen_prompt(root):
    # Drop the stored-output example, which caused format drift in the pilot.
    rubric = (root/'golden/RUBRIC.md').read_text()
    if '## Format' in rubric and '### Clarification fields' in rubric:
        semantic = rubric.split('## Format', 1)[0] + '### Clarification fields' + rubric.split('### Clarification fields', 1)[1]
    else:
        semantic = rubric
    original = prefix(root)
    original = original.replace(rubric, semantic)
    return original + ('\n\nOUTPUT CONTRACT: Only the compact input format is accepted. '
        'Never output id, by, visibility_distance, tallest_building, farthest_object or closest_object; '
        'the program derives those. Cross-check building/storeys/high_rise_building and '
        'landscape/open_view against your honest numeric estimates before replying. '
        'Return all requested labels, no commentary or markdown. Do not add features from '
        'earlier photos unless they are visible in the current one.')


class Acquisition(Runner):
    def __init__(self, args):
        self.root = args.aaa_dir.resolve()
        self.out = self.root/'distiller/acquisition'/getattr(args, 'run_name', 'context-bulk-v1')
        self.out.mkdir(parents=True, exist_ok=True)
        self.order = (self.root/'photos/.order').read_text().split()
        self.client = httpx.Client(headers={'x-api-key': args.key_file.read_text().strip(),
            'anthropic-version': '2023-06-01'}, timeout=180)
        cp = self.out/'config.json'
        self.config = load(cp)
        if self.config is None:
            done = set()
            for path in (self.root/'golden/labels').glob('*.jsonl'):
                for line in path.read_text().splitlines():
                    row = json.loads(line)
                    if self.order[row['seq']] != row['id']:
                        raise ValueError('Source identity mismatch')
                    done.add(row['seq'])
            targets = [s for s in range(len(self.order)) if s not in done][:10000]
            pilot = load(self.root/'distiller/acquisition/context-pilot-v1/ledger.json', {})
            prior = sum(e.get('actual_usd', e['reserved_usd']) for e in pilot.values())
            self.config = {'model': MODEL, 'system': strengthen_prompt(self.root), 'targets': targets,
                'order_sha256': hashlib.sha256((self.root/'photos/.order').read_bytes()).hexdigest(),
                'prior_pilot_usd': prior, 'bulk_budget_usd': 90-prior, 'session_ceiling_usd': 100,
                'review_reserve_usd': 10, 'canary_photos': 100, 'canary_min_coverage': .95, 'canary_max_skip_share': .05,
                'max_active_chunks': 20, 'max_batch_bytes': 64*1024*1024,
                'chunk_size': 20, 'turn_size': 5, 'max_repairs': 1,
                'candidate_trust': False, 'thinking_budget': 1024}
            validator = self.out/'validator'
            for name in ('tools/add.py', 'tools/emit.py', 'prompts/1.json', 'photos/.order'):
                dest = validator/name; dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(self.root/name, dest)
            self.config['validator_sha256']={str(p.relative_to(validator)):hashlib.sha256(p.read_bytes()).hexdigest() for p in validator.rglob('*') if p.is_file()}
            write(cp, self.config)
        if hashlib.sha256((self.root/'photos/.order').read_bytes()).hexdigest() != self.config['order_sha256']:
            raise ValueError('Source ordering changed; cannot resume against different photos')
        self.system = self.config['system']
        self.budget_usd = self.config['bulk_budget_usd']
        self.state = load(self.out/'state.json')
        if self.state is None:
            # End a chunk at the canary boundary so no later photo is charged
            # before the first hundred outcomes have been checked.
            target = self.config['targets']; n = self.config['canary_photos']
            groups = chunks(target[:n]) + chunks(target[n:])
            self.state = {'chunks': [{'id': i, 'seqs': g, 'history': [], 'pending': None,
                                      'repair': None, 'failed': [], 'calls': 0} for i,g in enumerate(groups)],
                          'canary_passed': False, 'status': 'running'}
            self.seed_pilot()
            self.save_state()
        self.validate_resume()
        if self.state['status']=='needs_attention':
            self.state['status']='running';self.state.pop('error',None);self.save_state()

    def save_state(self):
        write(self.out/'state.json', self.state)

    def seed_pilot(self):
        pilot = self.root/'distiller/acquisition/context-pilot-v1'
        targets = set(self.config['targets'])
        for path in (pilot/'candidates').glob('context20-*.jsonl'):
            status = load(pilot/'validation'/f'{path.stem}.json', {})
            if not status.get('valid'):
                continue
            for line in path.read_text().splitlines():
                row = json.loads(line)
                if row['seq'] in targets:
                    write(self.out/'accepted'/f"{row['seq']}.json", {
                        'row': row, 'request_id': 'pilot/'+path.stem, 'trusted': False,
                        'source': 'anthropic-api', 'opus_reviewed': False})

    def validate_resume(self):
        jobs = [load(p) for p in (self.out/'jobs').glob('*.json')]
        assigned = {e['rid'] for j in jobs for e in j['entries']}
        ledger = load(self.out/'ledger.json', {})
        orphan = set(ledger)-assigned
        if orphan:
            raise ValueError(f'Reserved requests without a job need reconciliation: {sorted(orphan)}')
        for job in jobs:
            if job['status'] == 'preparing':
                # The durable intent marker proves POST was never attempted.
                # Retain an audit entry, release its unused budget, and move to
                # fresh request IDs rather than accidentally resending anything.
                for entry in job['entries']:
                    if entry['rid'] in ledger:
                        ledger[entry['rid']].update(actual_usd=0, status='not_submitted')
                    c=self.state['chunks'][entry['chunk']]
                    c['pending']=None
                    c['calls']=max(c['calls'],entry['call_index']+1)
                job.update(status='done',reason='preparation_interrupted_before_post')
                write(self.out/'jobs'/f"{job['id']}.json",job)
                write(self.out/'ledger.json',ledger)
                self.save_state()
            if job['status'] == 'submitting':
                receipt = load(self.out/'receipts'/f"{job['id']}.json")
                if receipt:
                    job.update(status='in_progress', provider_id=receipt['id'])
                    write(self.out/'jobs'/f"{job['id']}.json", job)
                else:
                    raise ValueError(f"Submission uncertain for {job['id']}; do not blindly resubmit")

    def content(self, seqs):
        content = user_content(self.root, self.order, seqs, cache_dir=self.out/'images')
        image_seqs=iter(seqs)
        for block in content:
            if block['type'] == 'image':
                data = base64.b64decode(block['source']['data'])
                sha = hashlib.sha256(data).hexdigest()
                seq = next(image_seqs)
                block['source'] = {'type': 'local_blob', 'media_type': 'image/webp',
                    'path': f'images/{self.order[seq]}.webp', 'sha256': sha}
        return content

    def materialize(self, value):
        if isinstance(value, dict):
            if value.get('type') == 'local_blob':
                data = (self.out/value['path']).read_bytes()
                if hashlib.sha256(data).hexdigest() != value['sha256']:
                    raise ValueError('Image blob checksum mismatch')
                return {'type': 'base64', 'media_type': value['media_type'], 'data': base64.b64encode(data).decode()}
            return {k:self.materialize(v) for k,v in value.items()}
        if isinstance(value,list):
            return [self.materialize(v) for v in value]
        return value

    def archive_request(self, rid, payload):
        # Image bytes are stored once. The complete wire body is reproducible
        # from its references and checksum instead of duplicating gigabytes.
        compact = self._compact_body
        wire = json.dumps(payload, ensure_ascii=False, separators=(',',':')).encode()
        write(self.out/'requests'/f'{rid}.json', {'params': compact, 'wire_sha256': hashlib.sha256(wire).hexdigest()})

    def body_for(self, chunk, seqs, repair):
        if chunk['history']:
            last = chunk['history'][-1]
            messages = load(self.out/'requests'/f'{last}.json')['params']['messages']
            response = load(self.out/'responses'/f'{last}.json')
            blocks = response.get('content', [])
            # Signed thinking is retained when complete. A truncated thought
            # cannot be replayed as a valid signed block.
            blocks = [b for b in blocks if b.get('type') != 'thinking' or b.get('signature')]
            if blocks:
                messages = messages + [{'role':'assistant','content':blocks}]
        else:
            messages = []
        if repair:
            content = [{'type':'text','text':
                'The local validator rejected these labels. Reinspect their earlier images and '
                'return ONLY corrected compact labels for these seqs: '+str(seqs)+'. '
                'Correct the actually wrong field, never stretch distances just to pass. '
                'Omit derived fields such as visibility_distance/id/by. Errors: '+json.dumps(chunk['repair']['errors']),
                'cache_control':{'type':'ephemeral','ttl':'1h'}}]
        else:
            content = self.content(seqs)
        body = params(self.system, messages+[{'role':'user','content':content}], len(seqs))
        body['max_tokens'] = 8192
        return body

    def todo(self, chunk):
        return [s for s in chunk['seqs'] if s not in chunk['failed'] and not (self.out/'accepted'/f'{s}.json').exists()]

    def ready(self):
        canary = set(self.config['targets'][:self.config['canary_photos']])
        unfinished = [c for c in self.state['chunks'] if self.todo(c) or c['pending']]
        if not self.state['canary_passed']:
            unfinished = [c for c in unfinished if c['seqs'][0] in canary]
            if not unfinished:
                good = sum((self.out/'accepted'/f'{s}.json').exists() for s in canary)
                skipped=sum('skip' in load(self.out/'accepted'/f'{s}.json',{}).get('row',{}) for s in canary)
                known_skips=set(self.config.get('known_skip_seqs',[])) & canary
                unexpected_skips=sum('skip' in load(self.out/'accepted'/f'{s}.json',{}).get('row',{}) for s in canary-known_skips)
                if good/max(1,len(canary)) < self.config['canary_min_coverage'] or unexpected_skips/max(1,len(canary-known_skips)) > self.config.get('canary_max_skip_share',.05):
                    self.state.update(status='canary_failed', canary_accepted=good, canary_skipped=skipped)
                    self.save_state()
                    return []
                self.state.update(canary_passed=True, canary_accepted=good, canary_skipped=skipped)
                self.save_state()
                unfinished = [c for c in self.state['chunks'] if self.todo(c) or c['pending']]
        # Keep old chunks moving before opening more conversations.
        active = [c for c in unfinished if c['history'] or c['pending']]
        new = [c for c in unfinished if not c['history'] and not c['pending']]
        selected = active + new[:max(0,self.config['max_active_chunks']-len(active))]
        return [c for c in selected if not c['pending']]

    def prepare(self):
        entries = []; byte_count = 0
        job = {'id':uuid.uuid4().hex,'status':'preparing','entries':entries}
        for chunk in self.ready():
            repair = chunk['repair'] is not None
            seqs = chunk['repair']['seqs'] if repair else self.todo(chunk)[:5]
            if not seqs:
                continue
            compact = self.body_for(chunk,seqs,repair)
            payload = self.materialize(compact)
            size = len(json.dumps(payload).encode())
            if entries and byte_count+size > self.config['max_batch_bytes']:
                break
            rid = f"c{chunk['id']:04d}-t{chunk['calls']:03d}"
            self._compact_body = compact
            entry={'rid':rid,'chunk':chunk['id'],'seqs':seqs,'repair':repair,'call_index':chunk['calls']}
            entries.append(entry)
            write(self.out/'jobs'/f"{job['id']}.json",job)
            try:
                self.reserve(rid,payload,True)
            except ValueError as error:
                if 'budget cap' in str(error):
                    entries.pop()
                    write(self.out/'jobs'/f"{job['id']}.json",job)
                    break
                raise
            chunk['pending']=rid;chunk['calls']+=1
            self.save_state()
            byte_count += size
        if not entries:
            if (self.out/'jobs'/f"{job['id']}.json").exists():
                job['status']='done';write(self.out/'jobs'/f"{job['id']}.json",job)
            return None
        job['status']='ready'
        write(self.out/'jobs'/f"{job['id']}.json",job)
        self.save_state()
        return job

    def submit_job(self, job):
        requests=[]
        for entry in job['entries']:
            stored=load(self.out/'requests'/f"{entry['rid']}.json")
            payload=self.materialize(stored['params'])
            wire=json.dumps(payload,ensure_ascii=False,separators=(',',':')).encode()
            if hashlib.sha256(wire).hexdigest()!=stored['wire_sha256']:
                raise ValueError('Archived request cannot be reconstructed exactly')
            requests.append({'custom_id':entry['rid'],'params':payload})
        job['status']='submitting';write(self.out/'jobs'/f"{job['id']}.json",job)
        receipt=self.api('POST','/messages/batches',{'requests':requests})
        write(self.out/'receipts'/f"{job['id']}.json",receipt)
        job.update(status='in_progress',provider_id=receipt['id'])
        write(self.out/'jobs'/f"{job['id']}.json",job)
        print('Submitted',receipt['id'],len(requests),'requests',flush=True)

    def validate_rows(self, rid, response, seqs):
        vp=self.out/'validation'/f'{rid}.json'
        if vp.exists():return load(vp)
        result={'accepted':[],'errors':{}}
        try:
            if response.get('stop_reason')!='end_turn':raise ValueError('Unfinished response: '+str(response.get('stop_reason')))
            raw=''.join(b.get('text','') for b in response['content'] if b['type']=='text').strip()
            if raw.startswith('```'):raw=raw.split('\n',1)[1].rsplit('```',1)[0].strip()
            rows=json.loads(raw)['labels']
            if len(rows)!=len(seqs) or any(type(r.get('seq')) is not int for r in rows) or {r['seq'] for r in rows}!=set(seqs):
                raise ValueError('Missing/duplicate/unexpected target identity')
        except (ValueError,KeyError,TypeError) as error:
            result['errors']={str(s):str(error) for s in seqs};write(vp,result);return result
        for row in rows:
            seq=row['seq']
            try:
                if 'skip' not in row and row.get('img')!=self.order[seq][:8]:raise ValueError('Image identity mismatch')
                target=self.out/'normalized'/rid/f'{seq}.jsonl'
                by=f"run={self.out.name},agent=fixed-runner,model={self.config['model']},effort={self.config.get('effort', 'thinking-1024')},rubric=2.20"
                proc=subprocess.run([sys.executable,str(self.out/'validator/tools/add.py'),str(target),'--by',by],
                    input=json.dumps(row),text=True,capture_output=True,cwd=self.out/'validator')
                if proc.returncode:raise ValueError(proc.stdout+proc.stderr)
                saved=json.loads(target.read_text())
                if 'skip' not in saved:normalize(saved,closest_policy='subject')
                result['accepted'].append({'row':saved,'request_id':rid,'trusted':self.config.get('candidate_trust',False),
                    'source':'anthropic-api','opus_reviewed':False,
                    'warnings':warnings_for(saved) if 'skip' not in saved else []})
            except (ValueError,KeyError,TypeError) as error:
                result['errors'][str(seq)]=str(error)
        write(vp,result);return result

    def usage_price(self, usage, rid):
        return price(usage, True)

    def consume(self, entry, response):
        rid=entry['rid'];chunk=self.state['chunks'][entry['chunk']]
        if chunk['pending']!=rid:return
        write(self.out/'responses'/f'{rid}.json',response)
        ledger=load(self.out/'ledger.json')
        ledger[rid].update(actual_usd=self.usage_price(response.get('usage',{}),entry['rid']),usage=response.get('usage',{}))
        write(self.out/'ledger.json',ledger)
        result=self.validate_rows(rid,response,entry['seqs'])
        for record in result['accepted']:
            path=self.out/'accepted'/f"{record['row']['seq']}.json"
            if path.exists() and load(path)!=record:raise ValueError('Conflicting accepted answer')
            write(path,record)
        errors=result['errors']
        chunk['history'].append(rid);chunk['pending']=None
        if entry['repair']:
            chunk['failed']+=list(map(int,errors));chunk['repair']=None
        elif errors:
            chunk['repair']={'seqs':list(map(int,errors)),'errors':errors}
        else:
            chunk['repair']=None
        self.save_state()

    def collect_job(self, job):
        state=self.api('GET','/messages/batches/'+job['provider_id'])
        job['provider_state']=state;write(self.out/'jobs'/f"{job['id']}.json",job)
        if state['processing_status']!='ended':return False
        if not state['results_url'].startswith(API+'/messages/batches/'):raise ValueError('Unexpected results origin')
        fetched=self.client.get(state['results_url']);fetched.raise_for_status()
        text=fetched.text;rows=[json.loads(l) for l in text.splitlines() if l.strip()]
        mapping={e['rid']:e for e in job['entries']}
        if len(rows)!=len(mapping) or {r['custom_id'] for r in rows}!=set(mapping):raise ValueError('Incomplete batch results')
        (self.out/'results').mkdir(exist_ok=True)
        (self.out/'results'/f"{job['id']}.jsonl").write_text(text)
        for row in rows:
            rid=row['custom_id'];result=row['result']
            if result['type']=='succeeded':response=result['message']
            else:response={'stop_reason':result['type'],'content':[],'usage':{},'provider_result':result}
            self.consume(mapping[rid],response)
        job['status']='done';write(self.out/'jobs'/f"{job['id']}.json",job)
        return True

    def summary(self):
        ledger=load(self.out/'ledger.json',{});accepted=list((self.out/'accepted').glob('*.json'))
        failed=sum(len(c['failed']) for c in self.state['chunks'])
        jobs=[load(p) for p in (self.out/'jobs').glob('*.json')]
        summary={'status':self.state['status'],'target_photos':len(self.config['targets']),
            'accepted':len(accepted),'failed_after_repair':failed,'canary_passed':self.state['canary_passed'],
            'prior_pilot_usd':self.config['prior_pilot_usd'],
            'bulk_spent_usd':sum(e.get('actual_usd',0) for e in ledger.values()),
            'bulk_spent_or_reserved_usd':sum(e.get('actual_usd',e['reserved_usd']) for e in ledger.values()),
            'total_session_spent_usd':self.config['prior_pilot_usd']+sum(e.get('actual_usd',0) for e in ledger.values()),
            'max_active_chunks':self.config['max_active_chunks'],
            'bulk_budget_usd':self.budget_usd,'active_batches':sum(j['status']!='done' for j in jobs),
            'updated_at':datetime.now(timezone.utc).isoformat()}
        write(self.out/'summary.json',summary);print(json.dumps(summary),flush=True);return summary

    def run(self, once=False):
        while True:
            jobs=[load(p) for p in sorted((self.out/'jobs').glob('*.json'))]
            for job in jobs:
                if job['status']=='ready':self.submit_job(job)
                elif job['status']=='in_progress':self.collect_job(job)
                elif job['status'] not in ('done',):raise ValueError('Uncertain job; reconcile before continuing')
            job=self.prepare()
            if job:self.submit_job(job)
            summary=self.summary()
            if not summary['active_batches'] and not job:
                if self.state['status']=='running':
                    self.state['status']='complete' if summary['accepted']+summary['failed_after_repair']==len(self.config['targets']) else 'budget_exhausted'
                    self.save_state();self.summary()
                return
            if once:return
            time.sleep(45)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--aaa-dir',type=Path,default=Path(__file__).parent.parent/'data/analyzer/aaa')
    parser.add_argument('--key-file',type=Path,default=Path(__file__).resolve().parents[2]/'secrets/CLAUDE_ANALYZER')
    parser.add_argument('--once',action='store_true',help='One reconcile/submit tick, for inspection')
    args=parser.parse_args()
    # Lock before initialization, including pilot seeding and resume checks.
    out=args.aaa_dir.resolve()/'distiller/acquisition/context-bulk-v1'
    with file_lock(out/'controller.lock',blocking=False) as acquired:
        if not acquired:raise SystemExit('Acquisition controller already running')
        worker=Acquisition(args)
        try:worker.run(args.once)
        except Exception as error:
            worker.state.update(status='needs_attention',error=str(error));worker.save_state();worker.summary()
            raise


if __name__=='__main__':main()
