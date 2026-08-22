"""Filing a graduated overlay's depth buffer into a storage pool.

The blob name IS its identity (content-addressed sha256), which buys sharing
between photos fitted against the same render — and makes hash verification
load-bearing: writing bytes under a name that doesn't hash to them would
poison every overlay pointing there.
"""
import base64
import gzip
import hashlib
import json

import pytest

import graduation


@pytest.fixture
def pool(tmp_path, monkeypatch):
    p = {"type": "files", "url": "https://pics.example/", "path": str(tmp_path)}
    monkeypatch.setattr("common.config.get_write_pool", lambda: p)
    return p


def make_pkg(data: bytes):
    h = hashlib.sha256(data).hexdigest()
    return h, {
        "package": "hillview-enrichment",
        "blobs": {h: {"encoding": "gzip+base64", "bytes": len(data),
                      "data": base64.b64encode(data).decode()}},
    }


DEPTH = gzip.compress(b"\x01\x00" * 4096)


def overlay_with_blob(h):
    return {"version": 1, "fit": {"fov_deg": 90.0},
            "skyline": {"elev_deg": [1.0]},
            "depth": {"blob": h, "width": 64, "height": 64,
                      "az_start": 0.0, "az_end": 63.0,
                      "elev_max_deg": 6.0, "elev_min_deg": -6.0,
                      "lat": 50.0, "lon": 14.5, "depth_scale_m": 4.0,
                      "bytes": len(DEPTH)}}


def test_stores_the_blob_and_returns_its_url(pool, tmp_path):
    h, pkg = make_pkg(DEPTH)
    url = graduation.store_depth_blob(pkg, h)
    assert url == f"https://pics.example/terrain/{h}.depth.bin.gz"
    written = tmp_path / "terrain" / f"{h}.depth.bin.gz"
    assert written.read_bytes() == DEPTH


def test_storing_twice_is_a_no_op(pool, tmp_path):
    """Re-applying a package, or two photos sharing one render, must resolve
    to the same file rather than duplicating megabytes."""
    h, pkg = make_pkg(DEPTH)
    first = graduation.store_depth_blob(pkg, h)
    written = tmp_path / "terrain" / f"{h}.depth.bin.gz"
    mtime = written.stat().st_mtime_ns
    assert graduation.store_depth_blob(pkg, h) == first
    assert written.stat().st_mtime_ns == mtime
    assert len(list((tmp_path / "terrain").iterdir())) == 1


def test_rejects_a_hash_mismatch(pool, tmp_path):
    """The name is the identity — bytes that don't hash to it must never land."""
    h, pkg = make_pkg(DEPTH)
    pkg["blobs"][h]["data"] = base64.b64encode(b"not the depth buffer").decode()
    with pytest.raises(ValueError, match="hash mismatch"):
        graduation.store_depth_blob(pkg, h)
    assert not (tmp_path / "terrain").exists() or not list((tmp_path / "terrain").iterdir())


def test_missing_blob_is_an_error(pool):
    with pytest.raises(KeyError):
        graduation.store_depth_blob({"blobs": {}}, "deadbeef")


def test_resolve_rewrites_the_reference_to_a_url(pool):
    h, pkg = make_pkg(DEPTH)
    resolved = graduation.resolve_overlay_blobs(pkg, overlay_with_blob(h))
    assert resolved["depth"]["url"] == f"https://pics.example/terrain/{h}.depth.bin.gz"
    # the package-local handle must not survive into stored state
    assert "blob" not in resolved["depth"]
    # the grid description is what makes the buffer usable — keep all of it
    assert resolved["depth"]["width"] == 64
    assert resolved["depth"]["depth_scale_m"] == 4.0


def test_resolve_leaves_a_depthless_overlay_alone(pool):
    ov = {"version": 1, "fit": {}, "skyline": {"elev_deg": []}}
    assert graduation.resolve_overlay_blobs({}, ov) is ov


def test_resolved_overlay_is_json_storable(pool):
    h, pkg = make_pkg(DEPTH)
    resolved = graduation.resolve_overlay_blobs(pkg, overlay_with_blob(h))
    # goes into a JSONB column: no bytes, no NaN, no surprises
    assert json.loads(json.dumps(resolved, allow_nan=False))["depth"]["url"]
