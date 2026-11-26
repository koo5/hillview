"""Content identities shared by image publication, path validation and analysis."""
import hashlib
from pathlib import Path
import re

# Full SHA-256 initially. Filename policy can change independently of the full
# digest recorded in sizes metadata. Readers accept byte-aligned 64–256-bit tags.
HASH_HEX_LENGTH = 64
_TAG = re.compile(r'^(?P<photo>.+?)(?:-v(?P<version>[1-9][0-9]{0,9}))?-(?P<hash>[0-9a-f]{16,64})$')


def file_sha256(path):
    value = hashlib.sha256()
    with open(path, 'rb') as source:
        for block in iter(lambda: source.read(1024*1024), b''):
            value.update(block)
    return value.hexdigest()


def artifact_stem(photo_id, sha256, version=None):
    if not re.fullmatch(r'[0-9a-f]{64}', sha256):
        raise ValueError('Expected full SHA-256 digest')
    if version is not None and (type(version) is not int or not 1 <= version <= 2147483647):
        raise ValueError('Artifact version must be a positive 32-bit integer')
    return f'{photo_id}' + (f'-v{version}' if version is not None else '') + '-' + sha256[:HASH_HEX_LENGTH]


def split_artifact_stem(stem):
    match = _TAG.fullmatch(stem)
    if match and len(match['hash']) % 2 == 0:
        return match['photo'], int(match['version']) if match['version'] else None, match['hash']
    return stem, None, None


def pyramid_sha256(descriptor, tiles):
    """A descriptor alone doesn't identify its pixels; include every tile."""
    value = hashlib.sha256(b'hillview-dzi-v1\0' + bytes.fromhex(file_sha256(descriptor)))
    root = Path(tiles)
    for path in sorted(root.rglob('*')):
        if path.is_file():
            name = path.relative_to(root).as_posix().encode()
            value.update(len(name).to_bytes(8, 'big') + name + bytes.fromhex(file_sha256(path)))
    return value.hexdigest()


def selected_image(photo):
    sizes = (photo.get('sizes') if isinstance(photo, dict) else photo.sizes) or {}
    return next((sizes[key] for key in ('640_llm', '640', '1024', 'full') if key in sizes), {})


def session_matches_image(session, photo):
    """Legacy rows retain compatibility; hashed renders require matching evidence."""
    image = selected_image(photo)
    current = image.get('sha256')
    if not current:
        return True
    metadata = session.get('metadata', {})
    if image.get('artifact_version') != metadata.get('artifact_version'):
        return False
    return current == (metadata.get('image_content_sha256') or metadata.get('image_hash'))
