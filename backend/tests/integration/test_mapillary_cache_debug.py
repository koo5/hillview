#!/usr/bin/env python3
"""
Integration tests for the Mapillary cache debug endpoint.
Tests DELETE /mapillary/debug/cache functionality.
"""

import pytest
import requests
import sys
import os

sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from utils.test_utils import API_URL


class TestMapillaryCacheDebug:
	"""Tests for the Mapillary cache debug endpoint."""

	def test_clear_cache_in_debug_mode(self):
		"""Test clearing Mapillary cache when DEBUG mode is enabled."""
		response = requests.delete(f"{API_URL}/mapillary/debug/cache")

		# The endpoint is protected by @debug_only decorator
		# In debug mode: returns 200 with success message
		# In production: returns 404 (endpoint not available)

		if response.status_code == 200:
			data = response.json()
			assert data["status"] == "success"
			assert "message" in data
			assert "details" in data
			assert "mapillary_cache_deleted" in data["details"]
			assert "cached_regions_deleted" in data["details"]
			print(f"✓ Cache cleared: {data['details']}")
		elif response.status_code == 404:
			# Debug mode is disabled - endpoint not available
			print("✓ Debug endpoint correctly disabled in production mode")
		else:
			pytest.fail(f"Unexpected status code: {response.status_code}")

	def test_clear_cache_response_structure(self):
		"""Test that cache clear response has expected structure when available."""
		response = requests.delete(f"{API_URL}/mapillary/debug/cache")

		if response.status_code == 200:
			data = response.json()

			# Check structure
			assert "status" in data
			assert "message" in data
			assert "details" in data

			details = data["details"]
			assert isinstance(details.get("mapillary_cache_deleted"), int)
			assert isinstance(details.get("cached_regions_deleted"), int)

			# Counts should be non-negative
			assert details["mapillary_cache_deleted"] >= 0
			assert details["cached_regions_deleted"] >= 0

	def test_clear_cache_idempotent(self):
		"""Test that clearing cache multiple times is safe."""
		# First clear
		response1 = requests.delete(f"{API_URL}/mapillary/debug/cache")

		if response1.status_code == 200:
			# Second clear immediately after
			response2 = requests.delete(f"{API_URL}/mapillary/debug/cache")

			assert response2.status_code == 200
			data2 = response2.json()

			# Second clear should succeed but delete 0 items
			assert data2["details"]["mapillary_cache_deleted"] == 0
			assert data2["details"]["cached_regions_deleted"] == 0
			print("✓ Cache clear is idempotent")

	def test_clear_cache_no_auth_required(self):
		"""Test that cache debug endpoint doesn't require auth (debug mode only)."""
		# Debug endpoints typically don't require auth since they're
		# only available in development
		response = requests.delete(f"{API_URL}/mapillary/debug/cache")

		# Should not return 401 (auth required)
		assert response.status_code != 401, \
			"Debug endpoint should not require authentication"


if __name__ == "__main__":
	pytest.main([__file__, "-v", "-s"])
