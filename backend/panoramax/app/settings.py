"""Configuration for the Panoramax-compatible read API.

The instance serves exactly one *scope* — a partition of Hillview's photos by
license. The federation's meta-catalog accepts only CC-BY-SA-4.0 / Licence
Ouverte 2.0 instances (enforced by human review at registration, never by
code), so the single scope declared instance-wide is the CC-BY-SA one. The
scope object keeps code/data modular: a second "ARR + OSM mapper provision"
instance later is a new Scope entry + deployment, not a config framework.
"""
import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Scope:
	id: str
	# photos.legal_rights value that selects this scope's photos
	legal_rights: str
	# SPDX id declared instance-wide and on every collection/item
	license: str
	license_url: str


SCOPES = {
	'cc': Scope(
		id='cc',
		legal_rights='ccbysa4+osm',
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
	return SCOPES[_validated_scope_id(os.getenv('PANORAMAX_SCOPE', 'cc'))]


# Fail at import (= container boot), not on the first request: a typo'd scope
# would otherwise leave a healthy-looking container that 500s every endpoint
# and dumps a KeyError per sequencer pass.
_validated_scope_id(os.getenv('PANORAMAX_SCOPE', 'cc'))


def base_url() -> str:
	"""Public canonical base URL of this instance (no trailing slash, no /api).

	Registered in the meta-catalog verbatim. Caveat on the registered string:
	the catalog's canonical_url() does a char-class rstrip("/api"), so a URL
	ending in any of '/', 'a', 'p', 'i' loses those characters. `.cz` ends in
	'z', so every *.hillview.cz host is safe (and a trailing slash just gets
	stripped, which is the intent) — but a path-suffixed URL would need care
	(".../cc" is fine, ".../cc-osm-map" would be mangled to ".../cc-osm-m").

	Default host is cc.geovisio.hillview.cz: this service speaks the GeoVisio
	STAC dialect rather than being a Panoramax instance, and the `cc.` prefix
	leaves room for a second license scope on its own host later. It also
	keeps panoramax.hillview.cz free for an actual Panoramax deployment.
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


# Page sizes. The harvester follows rel=next links, so limits only shape page
# count, not completeness.
COLLECTIONS_PAGE_DEFAULT = 100
COLLECTIONS_PAGE_MAX = 1000
ITEMS_PAGE_DEFAULT = 100
ITEMS_PAGE_MAX = 1000
