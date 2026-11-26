"""Small, reproducible provenance snapshot from the finished aaa checkout."""
import hashlib
import json
import re
import subprocess
from pathlib import Path

PROVENANCE_VERSION = 2

PROCEDURE_PATHS = ('golden/HANDOFF.md', 'golden/BATCHING.md', 'golden/RUBRIC.md',
                   'golden/AGENT_PROMPT.md', 'tools/review.py', 'tools/rare.py',
                   'tools/missing.py', 'tools/fullsize.py', 'tools/add.py')
PROMPT_PATHS = ('.claude/agents/golden-labeler.md', 'golden/RUBRIC.md', 'golden/AGENT_PROMPT.md', 'tools/make_prompts.py',
                'prompts/1v2.json', 'prompts/2v2.json')


def git(root, *args):
    try:
        result = subprocess.run(['git', '-C', str(root), *args], capture_output=True, text=True)
    except FileNotFoundError:
        return None
    return result.stdout if result.returncode == 0 else None


def recover(root: Path, output: Path):
    """Versioned procedure evidence; rubric matches are candidates, not invented prompts."""
    paths = set(PROCEDURE_PATHS + PROMPT_PATHS + ('photos/.order',))
    paths.update(str(p.relative_to(root)) for p in (root / 'golden/labels').glob('*.jsonl'))
    digest = hashlib.sha256()
    for path in sorted(paths):
        file = root / path
        if file.is_file():
            digest.update(path.encode())
            digest.update(hashlib.sha256(file.read_bytes()).digest())
    fingerprint = digest.hexdigest()
    cache = output / 'provenance/manifest.json'
    if cache.exists():
        previous = json.loads(cache.read_text())
        if previous.get('snapshot_fingerprint') == fingerprint and previous.get('provenance_version') == PROVENANCE_VERSION:
            return previous
    head = git(root, 'rev-parse', 'HEAD')
    manifest = {'provenance_version': PROVENANCE_VERSION, 'snapshot_fingerprint': fingerprint, 'head': head.strip() if head else None, 'procedures': {}, 'rubric_candidates': {},
                'label_commits': {}, 'historical_generation_prompts': 'rubric-matched candidates; not exact per-row proof'}
    snapshot_dir = output / 'provenance'
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    for path in PROCEDURE_PATHS:
        file = root / path
        if file.is_file():
            content = file.read_text()
            manifest['procedures'][path] = {'sha256': hashlib.sha256(content.encode()).hexdigest(), 'commit': manifest['head']}
    commits = (git(root, 'log', '--format=%H', '--', *PROMPT_PATHS) or '').splitlines()
    for commit in commits:
        rubric = git(root, 'show', f'{commit}:golden/RUBRIC.md')
        if not rubric:
            continue
        version = re.search(r'\(v([\d.]+)\)', rubric.splitlines()[0])
        if not version:
            continue
        files = {}
        for path in PROMPT_PATHS:
            content = git(root, 'show', f'{commit}:{path}')
            if content is not None:
                files[path] = {'sha256': hashlib.sha256(content.encode()).hexdigest(), 'content': content}
        (snapshot_dir / f'{commit}.json').write_text(json.dumps({'commit': commit, 'files': files}, indent=2))
        manifest['rubric_candidates'].setdefault(version[1], []).append(commit)
    # File-level last change is explicit; it does not imply every line changed then.
    history = git(root, 'log', '--format=COMMIT:%H', '--name-only', '--', 'golden/labels') or ''
    commit = None
    for line in history.splitlines():
        if line.startswith('COMMIT:'):
            commit = line[len('COMMIT:'):]
        elif line.startswith('golden/labels/') and line.endswith('.jsonl'):
            manifest['label_commits'].setdefault(line, commit)
    (snapshot_dir / 'manifest.json').write_text(json.dumps(manifest, indent=2))
    return manifest


def row_provenance(row, path, manifest):
    by = row.get('by', {})
    corrected = by.get('run') == 'review'
    marker = row.get('x', {}).get('reviewed')
    return {
        'checkout_commit': manifest.get('head'),
        'label_file_last_commit': manifest.get('label_commits', {}).get(path),
        'final_attribution': by,
        'generating_attribution': None if corrected else by,
        'prompt_candidate_commits': manifest.get('rubric_candidates', {}).get(str(by.get('rubric')), []),
        'supervision': {
            'model': 'opus', 'scope': 'documented master-session spot-checking and correction process',
            'procedure_manifest': 'provenance/manifest.json',
            'photo_review_status': 'corrected' if corrected else 'review_marker' if marker else 'not_individually_documented',
            'review_marker': marker,
        },
    }
