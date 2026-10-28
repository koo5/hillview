"""Audit coverage and failure reporting must not silently skip images."""

import importlib.util
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

spec = importlib.util.spec_from_file_location('deps', Path(__file__).resolve().parents[1] / 'deps.py')
deps = importlib.util.module_from_spec(spec)
spec.loader.exec_module(deps)


def test_analyzer_lockfile_is_covered():
	assert 'backend/analyzer/uv.lock' in deps.LOCKFILES


def test_running_images_use_immutable_ids_and_write_reports(tmp_path, monkeypatch):
	image_id = 'sha256:abc123'
	subprocess_run = Mock(side_effect=[SimpleNamespace(stdout='container123\n'),
	                                  SimpleNamespace(stdout=image_id + '\n')])
	monkeypatch.setattr(deps.subprocess, 'run', subprocess_run)
	work = tmp_path / 'archives'
	work.mkdir()
	monkeypatch.setattr(deps.tempfile, 'mkdtemp', lambda **kwargs: str(work))
	run = Mock(side_effect=[0, 1])
	monkeypatch.setattr(deps, 'run', run)
	args = SimpleNamespace(images=[], dry_run=False, output_dir=str(tmp_path / 'reports'))
	with pytest.raises(SystemExit) as result:
		deps.cmd_images(args)
	assert result.value.code == 1
	assert subprocess_run.call_args_list[1].args[0] == [
		'docker', 'inspect', '--format', '{{.Image}}', 'container123',
	]
	assert run.call_args_list[0].args[0][:3] == ['docker', 'save', image_id]
	scan = run.call_args_list[1].args[0]
	assert scan[-4:] == ['--format', 'json', '--output-file',
	                    str(tmp_path / 'reports' / 'sha256_abc123.json')]
	assert not work.exists()


def test_image_export_failure_is_not_a_clean_audit(tmp_path, monkeypatch):
	monkeypatch.setattr(deps.tempfile, 'mkdtemp', lambda **kwargs: str(tmp_path))
	run = Mock(return_value=1)
	monkeypatch.setattr(deps, 'run', run)
	with pytest.raises(SystemExit) as result:
		deps.cmd_images(SimpleNamespace(images=['missing:tag'], dry_run=False, output_dir=None))
	assert result.value.code == 2
	assert run.call_count == 1


def test_no_running_containers_does_not_invoke_scanner(monkeypatch):
	monkeypatch.setattr(deps.subprocess, 'run', Mock(return_value=SimpleNamespace(stdout='')))
	run = Mock()
	monkeypatch.setattr(deps, 'run', run)
	deps.cmd_images(SimpleNamespace(images=[], dry_run=False, output_dir=None))
	run.assert_not_called()
