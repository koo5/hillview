"""Startup validation: a misconfigured container must die at boot with a
message naming the knob, not limp along 500ing (bad scope) or retrying a
mislabelled connection failure forever (empty DB password)."""
import pytest

import settings
from db import _require_password


class TestScopeValidation:
	def test_default_scope_is_valid(self, monkeypatch):
		monkeypatch.delenv('PANORAMAX_SCOPE', raising=False)
		assert settings.active_scope().id == 'p1'

	def test_explicit_valid_scope(self, monkeypatch):
		monkeypatch.setenv('PANORAMAX_SCOPE', 'p1')
		assert settings.active_scope().id == 'p1'

	def test_unknown_scope_exits_naming_value_and_allowed(self, monkeypatch):
		monkeypatch.setenv('PANORAMAX_SCOPE', 'arr')
		with pytest.raises(SystemExit) as e:
			settings.active_scope()
		assert "'arr'" in str(e.value)
		assert 'p1' in str(e.value)


class TestDbPasswordValidation:
	def test_url_with_password_passes_through(self):
		url = 'postgresql+asyncpg://panoramax_ro:s3cret@localhost:5432/hillview'
		assert _require_password(url) == url

	@pytest.mark.parametrize('url', [
		# what compose builds when PANORAMAX_DB_PASSWORD defaults to ''
		'postgresql+asyncpg://panoramax_ro:@localhost:5432/hillview',
		'postgresql+asyncpg://panoramax_ro@localhost:5432/hillview',
	])
	def test_empty_password_exits_naming_the_env_var(self, url):
		with pytest.raises(SystemExit) as e:
			_require_password(url)
		assert 'PANORAMAX_DB_PASSWORD' in str(e.value)


@pytest.mark.parametrize('value,expected', [('4', 4), ('16', 16), ('360', 360)])
def test_bearing_buckets(monkeypatch, value, expected):
	monkeypatch.setenv('PANORAMAX_BEARING_BUCKETS', value)
	assert settings.bearing_buckets() == expected


@pytest.mark.parametrize('value', ['0', '-1', '361', '8.5', 'NaN', ''])
def test_invalid_bearing_buckets(monkeypatch, value):
	monkeypatch.setenv('PANORAMAX_BEARING_BUCKETS', value)
	with pytest.raises(SystemExit, match='PANORAMAX_BEARING_BUCKETS'):
		settings.bearing_buckets()


@pytest.mark.parametrize('value,expected', [('2', 2.0), ('0.5', 0.5), ('10', 10.0)])
def test_cell_size_m(monkeypatch, value, expected):
	monkeypatch.setenv('PANORAMAX_CELL_SIZE_M', value)
	assert settings.cell_size_m() == expected


@pytest.mark.parametrize('value', ['0', '-1', 'inf', 'NaN', 'five', ''])
def test_invalid_cell_size_m(monkeypatch, value):
	monkeypatch.setenv('PANORAMAX_CELL_SIZE_M', value)
	with pytest.raises(SystemExit, match='PANORAMAX_CELL_SIZE_M'):
		settings.cell_size_m()


class TestSettingsEnv:
	"""settings.env holds the defaults; outside compose settings.py resolves it."""

	def names(self):
		return [line.partition('=')[0] for line in settings.SETTINGS_ENV.read_text().splitlines()
			if line and not line.startswith('#')]

	def test_every_default_is_valid(self, monkeypatch):
		for name in self.names() + ['FRONTEND_URL']:
			monkeypatch.delenv(name, raising=False)
		for getter in (settings.active_scope, settings.base_url, settings.viewer_url, settings.logo_url,
				settings.dev_mode, settings.explorer_url, settings.instance_name, settings.session_gap_hours,
				settings.sequencer_interval_s, settings.sequencer_enabled, settings.bearing_buckets,
				settings.cell_size_m):
			getter()

	def test_environment_wins_over_the_file(self, monkeypatch):
		monkeypatch.setenv('PANORAMAX_INSTANCE_NAME', 'Elsewhere')
		assert settings.instance_name() == 'Elsewhere'

	def test_nested_default_follows_compose(self, monkeypatch):
		monkeypatch.delenv('PANORAMAX_VIEWER_URL', raising=False)
		monkeypatch.setenv('FRONTEND_URL', 'https://hv.example')
		assert settings.viewer_url() == 'https://hv.example'

	@pytest.mark.parametrize('text,env,expected', [
		('${A:-x}', {}, 'x'),
		('${A:-x}', {'A': 'set'}, 'set'),
		('${A:-x}', {'A': ''}, 'x'),  # :- treats empty as unset, as compose does
		('${A:-}', {}, ''),
		('${A:-${B:-https://h}}/p', {}, 'https://h/p'),
		('${A:-${B:-https://h}}/p', {'B': 'b'}, 'b/p'),
	])
	def test_interpolate(self, monkeypatch, text, env, expected):
		for name in 'AB':
			monkeypatch.delenv(name, raising=False)
		for name, value in env.items():
			monkeypatch.setenv(name, value)
		assert settings._interpolate(text)[0] == expected

	def test_unsupported_form_is_rejected(self):
		with pytest.raises(ValueError):
			settings._interpolate('${A}:-x')
