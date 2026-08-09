#!/usr/bin/env python3
"""
Tests for short share links (/api/shared).

Covers:
- POST /api/shared (mint, anonymous)
- Idempotent minting: same view state returns the same link id
- GET /api/shared/{slug} (resolve by leading id; title part decorative)
- Input validation and 404s
"""

import requests
import os
import sys

# Add paths for imports
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from utils.base_test import BaseIntegrationTest
from utils.test_utils import API_URL


def mint(body):
	return requests.post(f"{API_URL}/shared", json=body)


class TestShareLinks(BaseIntegrationTest):
	"""Test suite for short share link minting and resolution."""

	MAPILLARY_BODY = {
		"photo_uid": "mapillary-123456789",
		"lat": 50.0755,
		"lon": 14.4378,
		"bearing": 270,
		"zoom": 17,
	}

	def test_mint_anonymous_mapillary(self):
		"""Anonymous mint for a mapillary-source photo returns slug + target."""
		response = mint(self.MAPILLARY_BODY)
		assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

		data = response.json()
		assert "slug" in data and "target" in data, f"Missing keys in {data}"
		# No title for non-hillview sources -> 'photo' base, id-first
		link_id, base = data["slug"].split("-", 1)
		assert link_id.isdigit(), f"Slug must start with the row id: {data['slug']}"
		assert base == "photo", f"Expected 'photo' base, got {data['slug']}"
		assert data["target"] == "/?lat=50.0755&lon=14.4378&zoom=17&bearing=270&photo=mapillary-123456789", data["target"]

	def test_mint_idempotent(self):
		"""Minting the same view state twice returns the same slug."""
		first = mint(self.MAPILLARY_BODY).json()
		second = mint(self.MAPILLARY_BODY).json()
		assert first["slug"] == second["slug"], f"{first['slug']} != {second['slug']}"

		# A different view state mints a different link
		other = mint({**self.MAPILLARY_BODY, "zoom": 12}).json()
		assert other["slug"] != first["slug"], f"Different targets must not share a slug: {other['slug']}"

	def test_mint_with_zoom_view_bounds(self):
		"""zoomview bounds are carried into the target with fixed 6-decimal format."""
		body = {**self.MAPILLARY_BODY, "zoom_view_bounds": {"x1": 0.1, "y1": 0.2, "x2": 0.5, "y2": 0.4}}
		data = mint(body).json()
		assert data["target"].endswith("&x1=0.100000&y1=0.200000&x2=0.500000&y2=0.400000"), data["target"]

	def test_resolve(self):
		"""Resolution uses the leading id; the title part is decorative."""
		minted = mint(self.MAPILLARY_BODY).json()

		response = requests.get(f"{API_URL}/shared/{minted['slug']}")
		assert response.status_code == 200, f"Expected 200, got {response.status_code}"
		assert response.json()["target"] == minted["target"]

		# Tail-truncated / mangled title part still resolves
		link_id = minted["slug"].split("-", 1)[0]
		response = requests.get(f"{API_URL}/shared/{link_id}-completely-mangled")
		assert response.status_code == 200
		assert response.json()["target"] == minted["target"]

		# Bare id resolves too
		response = requests.get(f"{API_URL}/shared/{link_id}")
		assert response.status_code == 200

	def test_resolve_unknown(self):
		"""Unknown ids and malformed slugs yield 404."""
		assert requests.get(f"{API_URL}/shared/999999999-nope").status_code == 404
		assert requests.get(f"{API_URL}/shared/no-leading-id").status_code == 404
		assert requests.get(f"{API_URL}/shared/-42").status_code == 404

	def test_mint_validation(self):
		"""Invalid input is rejected."""
		# Nonexistent hillview photo
		response = mint({"photo_uid": "hillview-00000000-0000-0000-0000-000000000000", "zoom": 17})
		assert response.status_code == 404, f"Expected 404, got {response.status_code}"

		# Malformed photo_uid (no source prefix)
		assert mint({**self.MAPILLARY_BODY, "photo_uid": "x"}).status_code == 422

		# Non-hillview source without coordinates
		assert mint({"photo_uid": "mapillary-123456789", "zoom": 17}).status_code == 422

		# Out-of-range values
		assert mint({**self.MAPILLARY_BODY, "lat": 91}).status_code == 422
		assert mint({**self.MAPILLARY_BODY, "bearing": 360}).status_code == 422
