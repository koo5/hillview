"""Startup validation: a misconfigured container must die at boot with a
message naming the knob, not limp along 500ing (bad scope) or retrying a
mislabelled connection failure forever (empty DB password)."""
import pytest

import settings
from db import _require_password


class TestScopeValidation:
	def test_default_scope_is_valid(self, monkeypatch):
		monkeypatch.delenv('PANORAMAX_SCOPE', raising=False)
		assert settings.active_scope().id == 'cc'

	def test_explicit_valid_scope(self, monkeypatch):
		monkeypatch.setenv('PANORAMAX_SCOPE', 'cc')
		assert settings.active_scope().id == 'cc'

	def test_unknown_scope_exits_naming_value_and_allowed(self, monkeypatch):
		monkeypatch.setenv('PANORAMAX_SCOPE', 'arr')
		with pytest.raises(SystemExit) as e:
			settings.active_scope()
		assert "'arr'" in str(e.value)
		assert 'cc' in str(e.value)


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
