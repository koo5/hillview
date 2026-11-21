import asyncio
from pathlib import Path

from common.artifact_identity import file_sha256
from photo_processor import PhotoProcessor


def test_publication_hashes_final_bytes_and_accepts_optional_client_version(tmp_path):
    processor = PhotoProcessor.__new__(PhotoProcessor)
    published = []
    async def ship(path, relative, *args, **kwargs):
        published.append((Path(path).read_bytes(), relative))
        return 'https://pics.test/'+relative
    processor._get_size_url = ship
    source = tmp_path/'photo.webp'
    source.write_bytes(b'final encoded bytes including exif')
    digest = file_sha256(source)
    row = asyncio.run(processor._publish_webp(str(source), 'opt/640_llm/owner/photo.webp',
                                            'photo', 'photo', 'signature', False, 7))
    assert row['sha256'] == digest and row['artifact_version'] == 7
    assert row['url'].endswith(f'photo-v7-{digest}.webp')
    assert published == [(b'final encoded bytes including exif', row['path'])]
    source.write_bytes(b'final encoded bytes including exif')
    row = asyncio.run(processor._publish_webp(str(source), 'opt/640_llm/owner/photo.webp',
                                            'photo', 'photo', 'signature', False, None))
    assert row['url'].endswith(f'photo-{digest}.webp')
    assert 'artifact_version' not in row
