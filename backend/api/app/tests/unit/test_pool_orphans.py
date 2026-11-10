"""pool_orphans: which files in the local pools no live photo owns.

The load-bearing rule: a file is live only when a completed, undeleted row
POINTS at it (sizes, the DZI pyramid, imu_samples_url) — a path with the right
shape under the right owner is not enough, and a stale copy of a live photo is
an orphan too.
"""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

import pool_orphans
from pool_orphans import Artifact, Index, Scanner, parse_artifact

NOW = datetime(2026, 11, 10, 12, 0, tzinfo=timezone.utc)
OWNER = "u1"


@pytest.fixture
def pools(tmp_path, monkeypatch):
	a = {"type": "files", "url": "https://pics2.example/", "path": str(tmp_path / "pics2")}
	b = {"type": "files", "url": "https://pics.example/", "path": str(tmp_path / "pics")}
	cdn = {"type": "cdn", "url": "https://cdn.example/", "bucket": "x"}
	(tmp_path / "pics2").mkdir()
	(tmp_path / "pics").mkdir()
	monkeypatch.setattr("common.config.get_file_pools", lambda: [a, b, cdn])
	monkeypatch.setattr("pool_orphans.get_file_pools", lambda: [a, b, cdn])
	return a, b


def put(pool, rel, data=b"x"):
	path = pool_path(pool, rel)
	path.parent.mkdir(parents=True, exist_ok=True)
	path.write_bytes(data)
	return path


def pool_path(pool, rel):
	from pathlib import Path
	return Path(pool["path"]) / rel


def row(pid, pool=None, owner=OWNER, status="completed", deleted=False, authorized_at=None, sizes: dict | None = None, imu=None, dzi=False):
	if sizes is None and pool is not None:
		base = pool["url"]
		sizes = {
			"full": {"url": f"{base}opt/full/{owner}/{pid}.webp"},
			"320": {"url": f"{base}opt/320/{owner}/{pid}.webp"},
		}
		if dzi:
			sizes["full"]["pyramid"] = {
				"type": "dzi",
				"dzi_url": f"{base}opt/dzi/{owner}/{pid}.dzi",
				"tiles_url": f"{base}opt/dzi/{owner}/{pid}_files",
			}
	return SimpleNamespace(id=pid, owner_id=owner, deleted=deleted, processing_status=status,
		upload_authorized_at=authorized_at, sizes=sizes, imu_samples_url=imu)


def put_photo(pool, pid, owner=OWNER, dzi=False):
	put(pool, f"opt/full/{owner}/{pid}.webp", b"full")
	put(pool, f"opt/320/{owner}/{pid}.webp", b"320")
	if dzi:
		put(pool, f"opt/dzi/{owner}/{pid}.dzi", b"<dzi/>")
		put(pool, f"opt/dzi/{owner}/{pid}_files/0/0_0.webp", b"t")
		put(pool, f"opt/dzi/{owner}/{pid}_files/1/0_0.webp", b"tt")


def scan(pool_list, rows, recheck_rows=None):
	index = Index()
	for r in rows:
		index.add(r)
	s = Scanner(index, NOW, timedelta(hours=24))
	roots = [p["path"] for p in pool_list]
	for p in pool_list:
		s.walk(p, roots)
	fresh = {r.id: r for r in (rows if recheck_rows is None else recheck_rows)}
	s.recheck({pid: fresh[pid] for pid, _ in s.groups if pid in fresh})
	return s


def reasons(s):
	return {(g.photo_id, g.owner_dir): g.reason for g in s.groups.values()}


def test_parse_layouts():
	assert parse_artifact("opt/320/u1/p1.webp") == Artifact("p1", "u1", None)
	assert parse_artifact("opt/imu/u1/p1.json.gz") == Artifact("p1", "u1", None)
	assert parse_artifact("opt/dzi/u1/p1.dzi") == Artifact("p1", "u1", None)
	assert parse_artifact("opt/dzi/u1/p1_files/12/3_4.webp") == Artifact("p1", "u1", "opt/dzi/u1/p1_files")
	assert parse_artifact("opt/1200/u1/p1.jpg") == Artifact("p1", "u1", None)  # pre-WebP
	assert parse_artifact("opt/320/p1.jpg") == Artifact("p1", None, None)       # pre owner dirs
	assert parse_artifact("opt/a/b/c/d/e/f.webp") is None
	assert parse_artifact("opt/dzi/u1/_files/1/0_0.webp") is None


def test_live_photo_with_pyramid_and_imu_is_clean(pools):
	a, _ = pools
	put_photo(a, "p1", dzi=True)
	put(a, f"opt/imu/{OWNER}/p1.json.gz")
	r = row("p1", a, dzi=True, imu=f"{a['url']}opt/imu/{OWNER}/p1.json.gz")
	s = scan([a], [r])
	assert s.groups == {}
	stats = s.pools[0]
	assert (stats.files, stats.live_files) == (6, 6)
	assert s.dangling() == []


def test_reasons(pools):
	a, _ = pools
	put_photo(a, "gone")                              # no row
	put_photo(a, "del")
	put_photo(a, "err")
	put_photo(a, "fresh")
	put_photo(a, "stale")
	put_photo(a, "mine", owner="u2")                  # row says owner u1
	rows = [
		row("del", a, deleted=True),
		row("err", a, status="error"),
		row("fresh", a, status="authorized", authorized_at=NOW - timedelta(hours=1)),
		row("stale", a, status="authorized", authorized_at=NOW - timedelta(days=3)),
		row("mine", a),
	]
	s = scan([a], rows)
	assert reasons(s) == {
		("gone", OWNER): "missing",
		("del", OWNER): "deleted",
		("err", OWNER): "not_completed",
		("fresh", OWNER): "in_flight",
		("stale", OWNER): "not_completed",
		("mine", "u2"): "owner_mismatch",
	}
	assert {g.photo_id for g in s.orphans()} == {"gone", "del", "err", "stale", "mine"}
	# The row of "mine" is live and points at u1's files, which are absent.
	assert len(s.dangling()) == 2


def test_live_photo_but_file_not_referenced_is_orphaned(pools):
	"""A stale copy on another pool, and a pre-WebP .jpg a reprocess left."""
	a, b = pools
	put_photo(a, "p1")
	put(b, f"opt/320/{OWNER}/p1.webp")
	put(a, f"opt/320/{OWNER}/p1.jpg")
	s = scan([a, b], [row("p1", a)])
	g = s.groups[("p1", OWNER)]
	assert g.reason == "unreferenced"
	assert sorted(key for _, key in g.entries) == [f"opt/320/{OWNER}/p1.jpg", f"opt/320/{OWNER}/p1.webp"]
	assert {root for root, _ in g.entries} == {a["path"], b["path"]}


def test_dzi_tiles_are_one_entry(pools):
	a, _ = pools
	put_photo(a, "p1", dzi=True)
	s = scan([a], [])
	g = s.groups[("p1", OWNER)]
	assert g.reason == "missing"
	assert g.entries[(a["path"], f"opt/dzi/{OWNER}/p1_files/")] == [2, 3]
	assert g.files == 5


def test_outside_opt_and_unrecognized_are_not_judged(pools):
	a, _ = pools
	put(a, "terrain/abc.depth.bin.gz")
	put(a, "work/p9-1234/raw.jpg")
	put(a, "stray.txt")
	put(a, "opt/a/b/c/d/e/f.webp")
	s = scan([a], [])
	assert s.groups == {}
	stats = s.pools[0]
	assert dict(stats.outside_opt) == {"terrain": [1, 1], "work": [1, 1], "(files at the pool root)": [1, 1]}
	assert stats.unrecognized == ["opt/a/b/c/d/e/f.webp"]


def test_recheck_uses_rows_written_during_the_walk(pools):
	"""Read before the walk: no row, status authorized long ago. Read after:
	completed. The files are live, not orphaned."""
	a, _ = pools
	put_photo(a, "new")
	put_photo(a, "slow")
	before = [row("slow", a, status="authorized", authorized_at=NOW - timedelta(days=2))]
	after = [row("new", a), row("slow", a)]
	s = scan([a], before, recheck_rows=after)
	assert s.groups == {}
	assert s.pools[0].live_files == 4


def test_recheck_drops_files_that_vanished(pools):
	a, _ = pools
	put_photo(a, "del")
	index = Index()
	s = Scanner(index, NOW, timedelta(hours=24))
	s.walk(a, [a["path"]])
	for p in ("full", "320"):
		pool_path(a, f"opt/{p}/{OWNER}/del.webp").unlink()
	s.recheck({})
	assert s.groups == {}
	assert s.pools[0].vanished == 2


def test_unresolved_and_cdn_refs_are_counted(pools):
	a, _ = pools
	r = row("p1", sizes={
		"full": {"url": "http://10.0.0.24:9999/pics2/opt/full/u1/p1.webp"},
		"320": {"url": "https://cdn.example/opt/320/u1/p1.webp"},
	})
	index = Index()
	index.add(r)
	assert (index.unresolved_refs, index.cdn_refs, index.live_files) == (1, 1, {})


def test_missing_pool_root_is_reported_not_empty(pools, tmp_path):
	gone = {"type": "files", "url": "https://gone.example/", "path": str(tmp_path / "nope")}
	s = Scanner(Index(), NOW, timedelta(hours=24))
	stats = s.walk(gone, [gone["path"]])
	assert stats.missing_root and not stats.walked


def test_nested_pool_root_is_walked_once(pools, tmp_path):
	"""A pool whose directory sits inside another's is not counted twice."""
	a, _ = pools
	inner = {"type": "files", "url": "https://inner.example/", "path": str(tmp_path / "pics2" / "inner")}
	put(inner, "opt/320/u1/p1.webp")
	s = Scanner(Index(), NOW, timedelta(hours=24))
	roots = [a["path"], inner["path"]]
	s.walk(a, roots)
	s.walk(inner, roots)
	assert [p.files for p in s.pools] == [0, 1]


def test_report_renders(pools, capsys):
	a, _ = pools
	put_photo(a, "gone", dzi=True)
	s = scan([a], [])
	pool_orphans.print_report(s, [], {}, verbose=2)
	out = capsys.readouterr().out
	assert "missing" in out and "gone" in out and "(2 tiles" in out
	doc = pool_orphans.report_json(s, [], {})
	assert doc["orphans"][0]["reason"] == "missing"
	assert doc["orphans"][0]["files"] == 5
