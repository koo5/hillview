"""Configuration for the p1.geovisio.hillview.cz federation read API.

Only intake grants allowing Hillview to publish under a Panoramax-compatible
licence qualify. Owner consent and moderation further gate participation.
The outflow is CC BY-SA 4.0 + LO derivatives; the SPDX slot carries the first
part and the configuration description states the second.
"""
import math
import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Scope:
	id: str
	# photos.legal_rights values that select this scope's photos
	legal_rights: tuple[str, ...]
	# SPDX id declared instance-wide and on every collection/item
	license: str
	license_url: str


SCOPES = {
	'p1': Scope(
		id='p1',
		legal_rights=('full1', 'panoramax_in'),
		license='CC-BY-SA-4.0',
		license_url='https://creativecommons.org/licenses/by-sa/4.0/',
	),
}


SETTINGS_ENV = Path(__file__).with_name('settings.env')


def _interpolate(text: str, i: int = 0, stop: str = '') -> tuple[str, int]:
	"""Compose's ${NAME:-default}, nesting included: the default applies when
	NAME is unset or empty. Returns the value and where parsing stopped."""
	out = []
	while i < len(text) and text[i] not in stop:
		if text.startswith('${', i):
			name_end = text.index(':-', i)
			name = text[i + 2:name_end]
			if not name.isidentifier():
				raise ValueError(f'{SETTINGS_ENV.name}: expected ${{NAME:-default}}, got {text[i:]!r}')
			default, i = _interpolate(text, name_end + 2, '}')
			out.append(os.environ.get(name) or default)
			i += 1  # the closing brace
		else:
			out.append(text[i])
			i += 1
	return ''.join(out), i


def _env(name: str) -> str:
	# Inside compose the variable is always set, from settings.env; elsewhere
	# resolve the same line, so the defaults live in that file alone.
	value = os.environ.get(name)
	if value is not None:
		return value
	for line in SETTINGS_ENV.read_text().splitlines():
		key, sep, raw = line.partition('=')
		if sep and key == name:
			return _interpolate(raw)[0]
	raise KeyError(f'{name} is not in {SETTINGS_ENV.name}')


def _validated_scope_id(value: str) -> str:
	if value not in SCOPES:
		raise SystemExit(
			f"unknown PANORAMAX_SCOPE {value!r}; allowed: {', '.join(sorted(SCOPES))}")
	return value


def active_scope() -> Scope:
	return SCOPES[_validated_scope_id(_env('PANORAMAX_SCOPE'))]


def base_url() -> str:
	"""Public canonical base URL of this instance (no trailing slash, no /api).

	Registered in the meta-catalog verbatim. Caveat on the registered string:
	the catalog's canonical_url() does a char-class rstrip("/api"), so a URL
	ending in any of '/', 'a', 'p', 'i' loses those characters. `.cz` ends in
	'z', so every *.hillview.cz host is safe (and a trailing slash just gets
	stripped, which is the intent) — but a path-suffixed URL would need care
	(".../cc" is fine, ".../cc-osm-map" would be mangled to ".../cc-osm-m").

	The canonical production host is p1.geovisio.hillview.cz.
	"""
	return _env('PANORAMAX_BASE_URL').rstrip('/')


def viewer_url() -> str:
	"""Where a human landing on this service's root should go.

	The meta-catalog attaches a `rel=via` link to every harvested item whose
	href is the registered instance URL, presented as "Link to the original
	instance" — i.e. it is a viewer link, not an API link. Serving raw STAC
	JSON there would be a dead end, so `/` redirects here.
	"""
	return _env('PANORAMAX_VIEWER_URL').rstrip('/')


def logo_url() -> str:
	"""The logo the meta-catalog shows for this instance. It stores
	/api/configuration's `logo` and /api/instances/<name>/logo redirects to it;
	the web viewer's picture panel asks the public catalog for that URL."""
	return _env('PANORAMAX_LOGO_URL')


def dev_mode() -> bool:
	"""DEV_MODE, the same switch the api reads; it gates the /dev/ pages."""
	return _env('DEV_MODE').lower() in ('true', '1', 'yes')


def explorer_url() -> str:
	"""A Panoramax explorer showing this instance's harvested data (a local
	meta-catalog, say), linked from /dev/suspicious; empty for none."""
	return _env('PANORAMAX_EXPLORER_URL').rstrip('/')


def instance_name() -> str:
	# Unique key in the meta-catalog's `instances` table (the URL is not
	# unique, the name is).
	return _env('PANORAMAX_INSTANCE_NAME')


def session_gap_hours() -> float:
	return float(_env('PANORAMAX_SESSION_GAP_HOURS'))


def sequencer_interval_s() -> int:
	return int(_env('PANORAMAX_SEQUENCER_INTERVAL_S'))


def sequencer_enabled() -> bool:
	return _env('PANORAMAX_SEQUENCER_ENABLED').lower() in ('1', 'true', 'yes')


def bearing_buckets() -> int:
	value = _env('PANORAMAX_BEARING_BUCKETS')
	try:
		count = int(value)
		if 1 <= count <= 360:
			return count
	except ValueError:
		pass
	raise SystemExit(f'PANORAMAX_BEARING_BUCKETS must be an integer between 1 and 360, got {value!r}')


def cell_size_m() -> float:
	"""Edge of a selection grid cell, in projected metres."""
	value = _env('PANORAMAX_CELL_SIZE_M')
	try:
		size = float(value)
		if math.isfinite(size) and size > 0:
			return size
	except ValueError:
		pass
	raise SystemExit(f'PANORAMAX_CELL_SIZE_M must be a positive number of metres, got {value!r}')


# Fail at import (= container boot), not on the first request: a typo'd scope
# would otherwise leave a healthy-looking container that 500s every endpoint
# and dumps a KeyError per sequencer pass, and a missing variable would do the
# same on whichever request first reads it.
for _setting in (active_scope, base_url, viewer_url, logo_url, dev_mode, explorer_url, instance_name,
		session_gap_hours, sequencer_interval_s, sequencer_enabled, bearing_buckets, cell_size_m):
	_setting()


# Page sizes. The harvester follows rel=next links, so limits only shape page
# count, not completeness.
COLLECTIONS_PAGE_DEFAULT = 100
COLLECTIONS_PAGE_MAX = 1000
ITEMS_PAGE_DEFAULT = 100
ITEMS_PAGE_MAX = 1000
