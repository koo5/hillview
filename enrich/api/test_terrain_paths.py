"""Pure-function tests for terrain artifact path containment (no app, no DB).

Run:  python -m pytest enrich/api/test_terrain_paths.py -q
"""
import os
import sys

import pytest
from fastapi import HTTPException

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import config
from app.routers.terrain import _artifact_abspath


def test_normal_artifact_path_resolves_inside_artifacts_dir():
    p = _artifact_abspath(os.path.join("terrain", "abc.depth.bin"))
    root = os.path.realpath(config.ARTIFACTS_DIR)
    assert p == os.path.join(root, "terrain", "abc.depth.bin")


@pytest.mark.parametrize("rel", [
    "../outside.bin",
    "terrain/../../outside.bin",
    "/etc/hostname",                 # absolute path overrides os.path.join
    "terrain/../..",
])
def test_escaping_paths_are_refused(rel):
    with pytest.raises(HTTPException) as e:
        _artifact_abspath(rel)
    assert e.value.status_code == 400
