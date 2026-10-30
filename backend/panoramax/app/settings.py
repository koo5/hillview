"""Configuration for the p1.geovisio.hillview.cz federation read API.

Only intake grants allowing Hillview to publish under a Panoramax-compatible
licence qualify. Owner consent and moderation further gate participation.
The SPDX declaration remains a placeholder until the outflow wording is final.
"""
import os
from dataclasses import dataclass


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


def _validated_scope_id(value: str) -> str:
	if value not in SCOPES:
		raise SystemExit(
			f"unknown PANORAMAX_SCOPE {value!r}; allowed: {', '.join(sorted(SCOPES))}")
	return value


def active_scope() -> Scope:
	return SCOPES[_validated_scope_id(os.getenv('PANORAMAX_SCOPE', 'p1'))]


# Fail at import (= container boot), not on the first request: a typo'd scope
# would otherwise leave a healthy-looking container that 500s every endpoint
# and dumps a KeyError per sequencer pass.
_validated_scope_id(os.getenv('PANORAMAX_SCOPE', 'p1'))


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
	return os.getenv('PANORAMAX_BASE_URL', 'http://localhost:8058').rstrip('/')


def viewer_url() -> str:
	"""Where a human landing on this service's root should go.

	The meta-catalog attaches a `rel=via` link to every harvested item whose
	href is the registered instance URL, presented as "Link to the original
	instance" — i.e. it is a viewer link, not an API link. Serving raw STAC
	JSON there would be a dead end, so `/` redirects here.
	"""
	return os.getenv('PANORAMAX_VIEWER_URL', 'https://hillview.cz').rstrip('/')


def logo_url() -> str:
	"""The logo the meta-catalog shows for this instance. It stores
	/api/configuration's `logo` and /api/instances/<name>/logo redirects to it;
	the web viewer's picture panel asks the public catalog for that URL."""
	return os.getenv('PANORAMAX_LOGO_URL', 'https://hillview.cz/favicon.png')


def instance_name() -> str:
	# Unique key in the meta-catalog's `instances` table (the URL is not
	# unique, the name is).
	return os.getenv('PANORAMAX_INSTANCE_NAME', 'Hillview')


def session_gap_hours() -> float:
	return float(os.getenv('PANORAMAX_SESSION_GAP_HOURS', '3'))


def sequencer_interval_s() -> int:
	return int(os.getenv('PANORAMAX_SEQUENCER_INTERVAL_S', '300'))


def sequencer_enabled() -> bool:
	return os.getenv('PANORAMAX_SEQUENCER_ENABLED', 'true').lower() in ('1', 'true', 'yes')


def bearing_buckets() -> int:
	value = os.getenv('PANORAMAX_BEARING_BUCKETS', '8')
	try:
		count = int(value)
		if 1 <= count <= 360:
			return count
	except ValueError:
		pass
	raise SystemExit(f'PANORAMAX_BEARING_BUCKETS must be an integer between 1 and 360, got {value!r}')


bearing_buckets()  # Fail at boot, like scope validation.


# Page sizes. The harvester follows rel=next links, so limits only shape page
# count, not completeness.
COLLECTIONS_PAGE_DEFAULT = 100
COLLECTIONS_PAGE_MAX = 1000
ITEMS_PAGE_DEFAULT = 100
ITEMS_PAGE_MAX = 1000
