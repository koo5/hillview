#!/usr/bin/env python3
"""Unit tests for sharpness_cli.py's local-mirror lookup."""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

import sharpness_cli as cli


@pytest.fixture
def mirror(tmp_path):
	root = tmp_path / "opt"
	(root / "full" / "u1").mkdir(parents=True)
	(root / "full" / "u1" / "p1.webp").write_bytes(b"pixels")
	(tmp_path / "secret").write_bytes(b"outside")
	return cli.parse_local([f"https://pics.example/opt/={root}"])


def test_reads_a_mirrored_file(mirror):
	assert cli.read_local("https://pics.example/opt/full/u1/p1.webp", mirror) == b"pixels"


def test_missing_file_or_other_prefix_falls_through(mirror):
	assert cli.read_local("https://pics.example/opt/full/u1/missing.webp", mirror) is None
	assert cli.read_local("https://pics.example/pics2/opt/full/u1/p1.webp", mirror) is None


def test_never_resolves_outside_the_mirror(mirror):
	assert cli.read_local("https://pics.example/opt/../secret", mirror) is None


def test_longest_prefix_wins(tmp_path):
	a, b = tmp_path / "a", tmp_path / "b"
	a.mkdir(); b.mkdir()
	(b / "x").write_bytes(b"from b")
	(a / "full").mkdir(); (a / "full" / "x").write_bytes(b"from a")
	local = cli.parse_local([f"https://h/={a}", f"https://h/full/={b}"])
	assert cli.read_local("https://h/full/x", local) == b"from b"


def test_bad_spec_exits(tmp_path):
	with pytest.raises(SystemExit):
		cli.parse_local(["no-equals-sign"])
	with pytest.raises(SystemExit):
		cli.parse_local([f"https://h/={tmp_path / 'nope'}"])
