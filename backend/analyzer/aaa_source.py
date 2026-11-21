"""Read an explicitly trusted aaa checkout without modifying its labels or prompt history."""
import hashlib
import json
import math
import os
import tempfile
from pathlib import Path
from uuid import UUID
from urllib.parse import urlsplit
from common.artifact_identity import split_artifact_stem

from analyze_photo import build_schema, validate_analysis
from distill import session_fingerprint, file_lock, TRUSTED_MODELS

ADAPTER_VERSION = 2

# Reader-facing additions, kept out of free-text identifying fields.
EXTRA_DB_KEYS = ("closest_visible_object_distance", "tallest_building_storeys",
                 "has_horizon", "buildings_on_horizon", "open_view", "through_glass",
                 "blur", "sky_only", "obstructed", "house_number")


def meters(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
        raise ValueError(f"Invalid distance in meters: {value!r}")
    return value


def normalize(row, *, closest_policy):
    """A complete source row wins as a unit; never fill its nulls from older models."""
    features = row.get('features')
    schema = build_schema(distances=False)
    allowed = schema['properties']['features']['properties']
    if not isinstance(features, list) or any(not isinstance(f, str) or f not in allowed for f in features):
        raise ValueError('Unknown or malformed features')
    answer = {k: row[k] for k in schema['required']}
    answer['features'] = {f: f in features for f in allowed}
    errors = validate_analysis(answer, schema)
    if errors:
        raise ValueError('; '.join(errors))
    x = row.get('x', {})
    sky = x.get('sky_only') is True
    distances = {}
    for key in ('closest_object', 'farthest_object'):
        obj = row.get(key)
        if not isinstance(obj, dict) or not isinstance(obj.get('description'), str):
            raise ValueError(f'Malformed {key}')
        value = obj.get('meters')
        if sky:
            if value is not None:
                raise ValueError('Sky-only distances must be null')
        else:
            value = meters(value)
            category = ('meters' if value < 10 else 'tens_of_meters' if value < 100
                        else 'hundreds_of_meters' if value < 1000 else 'kilometers')
            if obj.get('distance_category') != category:
                raise ValueError(f'{key}: meters/category disagree')
        distances[key] = value
    near, far = distances['closest_object'], distances['farthest_object']
    if not sky and near > far:
        raise ValueError('Closest object is farther than farthest object')
    if not sky:
        expected = 'near' if far < 10 else 'medium' if far < 100 else 'far' if far < 1000 else 'panoramic'
        if answer['visibility_distance'] != expected:
            raise ValueError('Visibility and farthest distance disagree')
    if closest_policy == 'subject':
        subject = x.get('closest_subject')
        # No silent substitution of a curb for a consequential subject.
        if not isinstance(subject, dict) or not isinstance(subject.get('description'), str):
            raise ValueError('Missing closest_subject; choose an explicit mapping or repair the source')
        near = subject.get('meters')
        if sky:
            if near is not None:
                raise ValueError('Sky-only subject distance must be null')
        else:
            near = meters(near)
            # Separate rough estimates can disagree. Preserve values and expose
            # the discrepancy in the index instead of silently changing them.
    elif closest_policy != 'object':
        raise ValueError('Unknown closest policy')
    answer['closest_object_distance'] = near
    answer['farthest_object_distance'] = far
    answer['features'] = list(features)
    answer['closest_visible_object_distance'] = distances['closest_object']
    answer['tallest_building_storeys'] = x.get('storeys')
    if answer['tallest_building_storeys'] is not None and (type(answer['tallest_building_storeys']) is not int or answer['tallest_building_storeys'] < 0):
        raise ValueError('Invalid building storeys')
    for key in ('has_horizon', 'buildings_on_horizon'):
        answer[key] = row[key]
    for key in ('open_view', 'through_glass', 'sky_only', 'obstructed', 'house_number'):
        if key in x:
            if type(x[key]) is not bool:
                raise ValueError(f'Invalid boolean: {key}')
            answer[key] = x[key]
    if 'blur' in x:
        if x['blur'] not in ('none', 'slight', 'heavy'):
            raise ValueError('Invalid blur')
        answer['blur'] = x['blur']
    for key in ('animals', 'animal_depictions'):
        if key in x:
            if not isinstance(x[key], list) or any(not isinstance(a, str) or not a.strip() for a in x[key]):
                raise ValueError(f'Invalid {key}')
            # Keep other animal names and real/depicted distinctions in raw source.
    for animal in ('cat', 'dog'):
        if any(animal in x.get(key, []) for key in ('animals', 'animal_depictions')) and animal not in answer['features']:
            answer['features'].append(animal)
    return answer


def warnings_for(row):
    x = row.get('x', {})
    if x.get('sky_only'):
        return []
    near = row['closest_object']['meters']
    subject = x.get('closest_subject', {}).get('meters')
    far = row['farthest_object']['meters']
    if subject is not None and not near <= subject <= far:
        return [{'code': 'subject_outside_distance_bounds', 'closest_m': near,
                 'subject_m': subject, 'farthest_m': far}]
    return []


def atomic_jsonl(path, records):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode='w', dir=path.parent, delete=False) as out:
        try:
            for record in records:
                out.write(json.dumps(record, ensure_ascii=False) + '\n')
            out.flush()
            os.fsync(out.fileno())
            os.replace(out.name, path)
        finally:
            if os.path.exists(out.name):
                os.unlink(out.name)


class AaaSource:
    """Snapshot and index JSONL rows once. Reject ambiguity before any DB writes."""
    def __init__(self, root: Path, *, closest_policy: str):
        self.root = Path(root)
        self.closest_policy = closest_policy
        self.output_dir = self.root / 'distiller'
        self.rows = {}
        self.skipped = 0
        order = (self.root / 'photos/.order').read_text().split()
        paths = sorted((self.root / 'golden/labels').glob('*.jsonl'))
        if not paths:
            raise ValueError('No aaa label files found')
        for path in paths:
            for number, line in enumerate(path.read_text().splitlines(), 1):
                if not line.strip():
                    continue
                row = json.loads(line)
                pid = str(UUID(row['id']))
                seq = row.get('seq')
                if type(seq) is not int or not 0 <= seq < len(order) or order[seq] != pid:
                    raise ValueError(f'{path}:{number}: seq/UUID mismatch')
                if pid in self.rows:
                    raise ValueError(f'Duplicate aaa photo {pid}')
                self.rows[pid] = {'row': row, 'path': str(path.relative_to(self.root)), 'line': number}
                if 'skip' in row:
                    self.skipped += 1
        self._include_haiku(order)
        self.errors = {}
        for pid, item in self.rows.items():
            if 'skip' in item['row']:
                continue
            try:
                item['answer'] = normalize(item['row'], closest_policy=closest_policy)
                url = item.get('image_metadata', {}).get('url') or (self.root / 'photos' / pid).read_text().strip()
                filename = Path(urlsplit(url).path).name
                if not url.startswith('https://') or not filename.endswith('.webp') or split_artifact_stem(filename[:-5])[0] != pid:
                    raise ValueError('Unexpected source image URL')
                item['image_url'] = url
                item['fingerprint'] = session_fingerprint(item['row'])
                item['warnings'] = warnings_for(item['row'])
            except (ValueError, KeyError, TypeError) as error:
                self.errors[pid] = f"{item['path']}:{item['line']}: {error}"

    def _include_haiku(self, order):
        """User-approved Haiku sources; curated originals retain precedence."""
        self.api_variants = 0
        base = self.output_dir / 'acquisition'
        for run in sorted(base.iterdir()) if base.exists() else []:
            if not run.is_dir():
                continue
            files = [(p, 5) for p in sorted((run/'accepted').glob('*.json'))]
            files += [(p, 2) for p in sorted((run/'normalized').glob('*/*.jsonl'))]
            files += [(p, 2) for p in sorted((run/'per-photo-validation').glob('*/*.jsonl'))]
            files += [(p, 3 if p.stem.startswith('context20-') else 2 if p.stem.startswith('group5-') else 1)
                      for p in sorted((run/'candidates').glob('*.jsonl'))]
            for path, priority in files:
                wrapped = None
                if path.suffix == '.json':
                    wrapped = json.loads(path.read_text())
                    rows = [wrapped['row']]
                else:
                    rows = [json.loads(l) for l in path.read_text().splitlines() if l.strip()]
                for row in rows:
                    model = (row.get('by') or {}).get('model')
                    if model not in TRUSTED_MODELS or not (model == 'haiku' or model.startswith('claude-haiku-')):
                        continue
                    seq = row.get('seq'); pid = str(UUID(row['id']))
                    if type(seq) is not int or not 0 <= seq < len(order) or order[seq] != pid:
                        raise ValueError(f'{path}: Haiku seq/UUID mismatch')
                    self.api_variants += 1
                    if pid in self.rows and self.rows[pid].get('priority', 10) >= priority:
                        # A trusted usable answer may fill a previously skipped frame.
                        # Curated usable answers still retain precedence.
                        if 'skip' not in self.rows[pid]['row'] or 'skip' in row:
                            continue
                    # Don't let a failed normalization hide a usable prior answer.
                    if 'skip' not in row:
                        try:
                            normalize(row, closest_policy=self.closest_policy)
                        except (ValueError, KeyError, TypeError):
                            continue
                    image_run = run
                    if wrapped and str(wrapped.get('request_id','')).startswith('pilot/'):
                        image_run = base/'context-pilot-v1'
                    metadata = image_run/'images'/f'{pid}.json'
                    self.rows[pid] = {'row':row, 'path':str(path.relative_to(self.root)),
                        'line':None, 'priority':priority, 'source':'haiku_api',
                        'collection':wrapped, 'image_metadata':json.loads(metadata.read_text()) if metadata.exists() else {}}

    def write_index(self):
        from aaa_provenance import recover, row_provenance
        with file_lock(self.output_dir / '.index.lock'):
            self.provenance = recover(self.root, self.output_dir)
            def records():
                for pid, item in self.rows.items():
                    item['provenance'] = (row_provenance(item['row'], item['path'], self.provenance)
                        if item.get('source') != 'haiku_api' else {
                            'generating_attribution':item['row'].get('by'),
                            'collection':item.get('collection'),
                            'supervision':{'photo_review_status':'user_trusted', 'model':None,
                                'note':'User approved existing Haiku results on 2026-11-04; no Opus review implied'}})
                    yield {'photo_id': pid, 'adapter_version': ADAPTER_VERSION,
                           'closest_policy': self.closest_policy,
                           'status': 'skip' if 'skip' in item['row'] else 'error' if pid in self.errors else 'ready',
                           'error': self.errors.get(pid), **item}
            atomic_jsonl(self.output_dir / 'index.jsonl', records())
            atomic_jsonl(self.output_dir / 'validation.jsonl', (
                {'photo_id': pid, 'error': self.errors.get(pid), 'warnings': item.get('warnings', [])}
                for pid, item in self.rows.items() if pid in self.errors or item.get('warnings')))

    def resolve(self, pid, *, file_md5, image_url, image_sha256=None, artifact_version=None):
        item = self.rows.get(str(pid))
        if item is None or 'skip' in item['row']:
            return None
        if str(pid) in self.errors:
            raise ValueError(self.errors[str(pid)])
        if image_sha256 and item.get('image_metadata',{}).get('sha256') != image_sha256:
            return None  # Preserve the old answer, but don't apply it to a new render.
        if artifact_version is not None and item.get('image_metadata',{}).get('artifact_version') != artifact_version:
            return None
        if not image_sha256 and item['image_url'] != image_url:
            raise ValueError(f'{pid}: source and DB LLM image URLs differ')
        if not isinstance(file_md5, str) or len(file_md5) != 32 or any(c not in '0123456789abcdef' for c in file_md5):
            raise ValueError(f'{pid}: invalid database file_md5')
        return {
            'kind': 'external_analysis', 'source': item.get('source','aaa'), 'adapter_version': ADAPTER_VERSION,
            'photo_id': str(pid), 'file_md5': file_md5, 'image_url': image_url,
            'image_content_sha256': image_sha256,
            'source_fingerprint': item['fingerprint'], 'source_path': item['path'],
            'source_line': item['line'], 'closest_policy': self.closest_policy,
            'raw': item['row'], 'analysis': item['answer'],
            'warnings': item.get('warnings', []), 'provenance': item.get('provenance', {}),
            **({'image_hash':item['image_metadata']['sha256'],'image_bytes':item['image_metadata']['bytes']}
               if item.get('image_metadata',{}).get('sha256') else {}),
        }


def backfill_image_hash(record, previous, fetch):
    """Use the collector's SHA-256 of exact fetched LLM bytes; file_md5 is a separate DB key."""
    if previous and previous.get('image_url') == record['image_url'] and previous.get('image_hash'):
        record['image_hash'] = previous['image_hash']
        record['image_bytes'] = previous['image_bytes']
        return
    content = fetch(record['image_url'])
    record['image_hash'] = hashlib.sha256(content).hexdigest()
    record['image_bytes'] = len(content)
