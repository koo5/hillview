#!/usr/bin/env python3
"""
Integration coverage for background-location provenance ingestion.

A browser capture carries no embedded EXIF — provenance (location_source,
bearing_source, and the background-tracking `alt_location`) rides the upload's
`metadata` JSON field. The worker synthesizes the same UserComment the Android
(Rust) EXIF writer produces, landing it at `exif_data['data']['UserComment']`
so both upload paths converge on one place (see
worker/photo_processor.py + BrowserMetadata in worker/app.py).

These tests drive the real secure upload flow with a no-EXIF image (the browser
case) and assert the synthesized UserComment, including that `alt_location` is
present when sent and omitted when not.
"""

import json
import os
import sys
import time

import pytest
import requests

sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from utils.base_test import BasePhotoTest
from utils.secure_upload_utils import SecureUploadClient, generate_test_captured_at
from utils.test_utils import API_URL
from utils.image_utils import create_test_image_no_exif

PRAGUE_LAT = 50.0755
PRAGUE_LON = 14.4378


class TestBackgroundLocationProvenance(BasePhotoTest):
	"""Browser-path provenance (incl. alt_location) lands in exif_data UserComment."""

	async def _upload_browser_style(self, metadata: dict) -> dict:
		"""Run the full secure upload with a no-EXIF image + a `metadata` field,
		wait for processing, and return the photo detail JSON (which includes
		`exif_data`). Mirrors the browser upload: no embedded EXIF, GPS supplied
		via metadata."""
		upload_client = SecureUploadClient(api_url=API_URL)
		client_keys = upload_client.generate_client_keys()
		await upload_client.register_client_key(self.test_token, client_keys)

		image_data = create_test_image_no_exif(640, 480, (0, 128, 255))
		filename = "bg_location_test.jpg"

		auth_data = await upload_client.authorize_upload_with_params(
			self.test_token, filename, len(image_data),
			PRAGUE_LAT, PRAGUE_LON, "background-location provenance test", True,
			captured_at=generate_test_captured_at(),
		)
		await upload_client.upload_to_worker(
			image_data, auth_data, client_keys, filename,
			metadata=json.dumps(metadata),
		)

		photo_id = auth_data["photo_id"]
		for _ in range(30):  # up to ~30s for processing
			resp = requests.get(f"{API_URL}/photos/{photo_id}", headers=self.test_headers)
			if resp.status_code == 200:
				body = resp.json()
				status = body.get("processing_status")
				if status in ("completed", "failed"):
					assert status == "completed", f"processing failed: {body.get('error')}"
					return body
			time.sleep(1)
		pytest.fail(f"Photo {photo_id} processing timed out after 30s")

	@staticmethod
	def _user_comment(photo: dict) -> str:
		exif = photo.get("exif_data") or {}
		return (exif.get("data") or {}).get("UserComment")

	@pytest.mark.asyncio
	async def test_alt_location_synthesized_into_usercomment(self):
		"""A background capture: primary location is 'map', and the live GPS fix
		rides along in `alt_location`. Both must surface in the UserComment."""
		alt = {
			"lat": 50.0760,
			"lng": 14.4400,
			"ts": 1_700_000_000_000,
			"accuracy": 5.0,
			"source": "gps-background",
		}
		metadata = {
			"latitude": PRAGUE_LAT,
			"longitude": PRAGUE_LON,
			"bearing": 90.0,
			"orientation_code": 1,
			"location_source": "map",
			"bearing_source": "enhanced-sensor",
			"alt_location": alt,
			"captured_at": generate_test_captured_at(),
		}

		photo = await self._upload_browser_style(metadata)

		user_comment = self._user_comment(photo)
		assert user_comment, f"UserComment missing; exif_data keys: {list((photo.get('exif_data') or {}).get('data', {}).keys())}"
		prov = json.loads(user_comment)

		assert prov["location_source"] == "map"
		assert prov["bearing_source"] == "enhanced-sensor"
		assert prov["alt_location"]["source"] == "gps-background"
		assert abs(prov["alt_location"]["lat"] - 50.0760) < 1e-6
		assert abs(prov["alt_location"]["lng"] - 14.4400) < 1e-6

	@pytest.mark.asyncio
	async def test_no_alt_location_when_not_provided(self):
		"""A normal capture (no background tracking): location_source/bearing_source
		still land in the UserComment, but no spurious `alt_location` key appears."""
		metadata = {
			"latitude": PRAGUE_LAT,
			"longitude": PRAGUE_LON,
			"bearing": 90.0,
			"location_source": "gps",
			"bearing_source": "gps-kalman",
			"captured_at": generate_test_captured_at(),
		}

		photo = await self._upload_browser_style(metadata)

		user_comment = self._user_comment(photo)
		assert user_comment, "UserComment should still carry location_source/bearing_source"
		prov = json.loads(user_comment)

		assert prov["location_source"] == "gps"
		assert prov["bearing_source"] == "gps-kalman"
		assert "alt_location" not in prov
