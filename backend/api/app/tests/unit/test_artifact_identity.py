from types import SimpleNamespace

import pytest

from common.artifact_identity import (artifact_stem, file_sha256, pyramid_sha256,
                                     split_artifact_stem, session_matches_image)
from common.security_utils import is_photo_artifact_relative_path
from pool_orphans import parse_artifact


@pytest.mark.parametrize('version', [None, 3])
def test_hashed_paths_remain_bound_to_owner_photo_and_optional_version(version):
    digest = 'a'*64
    stem = artifact_stem('photo', digest, version)
    assert split_artifact_stem(stem) == ('photo', version, digest)
    for path in (f'opt/640_llm/owner/{stem}.webp', f'opt/dzi/owner/{stem}.dzi',
                 f'opt/dzi/owner/{stem}_files/0/0_0.webp'):
        assert is_photo_artifact_relative_path(path, 'owner', 'photo', 3)
        assert not is_photo_artifact_relative_path(path, 'other', 'photo', 3)
        assert not is_photo_artifact_relative_path(path, 'owner', 'other', 3)
        assert parse_artifact(path).photo_id == 'photo'
        if version is not None:
            assert not is_photo_artifact_relative_path(path, 'owner', 'photo', 4)


def test_pyramid_identity_changes_when_pixels_change_but_descriptor_does_not(tmp_path):
    dzi = tmp_path/'photo.dzi'; dzi.write_bytes(b'<same descriptor/>')
    tiles = tmp_path/'photo_files'; tiles.mkdir()
    tile = tiles/'0_0.webp'; tile.write_bytes(b'old pixels')
    old = pyramid_sha256(dzi, tiles)
    tile.write_bytes(b'new pixels')
    assert pyramid_sha256(dzi, tiles) != old


def test_analyzer_does_not_reuse_same_md5_and_url_after_render_change():
    photo = SimpleNamespace(sizes={'640_llm': {'url': 'same-url', 'sha256': 'a'*64}})
    old = {'metadata': {'image_url': 'same-url', 'image_content_sha256': 'b'*64}}
    assert not session_matches_image(old, photo)
    assert not session_matches_image({'metadata': {}}, photo)
    old['metadata']['image_content_sha256'] = 'a'*64
    assert session_matches_image(old, photo)
    photo.sizes['640_llm']['artifact_version'] = 3
    assert not session_matches_image(old, photo)
    old['metadata']['artifact_version'] = 3
    assert session_matches_image(old, photo)
    assert session_matches_image({'metadata': {}}, SimpleNamespace(sizes={}))
