#!/usr/bin/env python3
"""End-to-end coverage for the raw IMU window as a stored artifact.

The capture app records accelerometer and gyroscope samples around every
exposure and sends them as a TOP-LEVEL `imu_samples` metadata field. Unlike
every other object added to that metadata, it must NOT become provenance: the
worker gzips it into the storage pool beside the photo's renditions and the row
keeps only `photos.imu_samples_url`. `exif_data` is read wholesale on every
photo detail request and has no business carrying a time series.

These tests drive the real secure upload flow and assert all three halves of
that design: the artifact exists and round-trips, the URL is served on both the
owner and the public endpoint, and the payload did NOT leak into the
UserComment. The last one is the easiest thing to regress by adding one string
to PROVENANCE_KEYS, and the only one no unit test can see.

See docs/recon-capture-metadata.md, Phase 5.
"""

import gzip
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

# The shape shared-kt's `imuSamplesPayloadJson` produces: columnar, one object
# per sensor, n-1 microsecond gaps for n samples.
IMU_SAMPLES = {
	"accel": {
		"t0_ms": 1_700_000_000_000,
		"t0_ns": 812_340_000_000,
		"dt_us": [2500, 2501, 2499],
		"x": [0.012, 0.013, 0.011, 0.012],
		"y": [-1.5, -1.51, -1.49, -1.5],
		"z": [9.81, 9.807, 9.812, 9.81],
	},
	"gyro": {
		"t0_ms": 1_700_000_000_000,
		"t0_ns": 812_340_000_000,
		"dt_us": [2500, 2500],
		"x": [0.0123, 0.0121, 0.0119],
		"y": [0.0, 0.0001, 0.0],
		"z": [-0.002, -0.0021, -0.002],
	},
}


class TestImuSamplesArtifact(BasePhotoTest):
	"""The raw window becomes a gzipped artifact, not a UserComment key."""

	async def _upload(self, metadata: dict) -> dict:
		upload_client = SecureUploadClient(api_url=API_URL)
		client_keys = upload_client.generate_client_keys()
		await upload_client.register_client_key(self.test_token, client_keys)

		image_data = create_test_image_no_exif(640, 480, (10, 90, 200))
		filename = "imu_samples_test.jpg"

		auth_data = await upload_client.authorize_upload_with_params(
			self.test_token, filename, len(image_data),
			PRAGUE_LAT, PRAGUE_LON, "imu samples artifact test", True,
			captured_at=generate_test_captured_at(),
		)
		await upload_client.upload_to_worker(
			image_data, auth_data, client_keys, filename,
			metadata=json.dumps(metadata),
		)

		photo_id = auth_data["photo_id"]
		for _ in range(30):
			resp = requests.get(f"{API_URL}/photos/{photo_id}", headers=self.test_headers)
			if resp.status_code == 200:
				body = resp.json()
				if body.get("processing_status") in ("completed", "failed"):
					assert body.get("processing_status") == "completed", \
						f"processing failed: {body.get('error')}"
					return body
			time.sleep(1)
		pytest.fail(f"Photo {photo_id} processing timed out after 30s")

	@staticmethod
	def _base_metadata(**extra) -> dict:
		return {
			"latitude": PRAGUE_LAT,
			"longitude": PRAGUE_LON,
			"bearing": 90.0,
			"orientation_code": 1,
			"location_source": "gps",
			"bearing_source": "enhanced-sensor",
			"captured_at": generate_test_captured_at(),
			**extra,
		}

	@pytest.mark.asyncio
	async def test_the_window_round_trips_as_a_gzipped_artifact(self):
		"""The samples reach the storage pool and come back byte-for-value equal."""
		photo = await self._upload(self._base_metadata(imu_samples=IMU_SAMPLES))

		url = photo.get("imu_samples_url")
		assert url, f"no imu_samples_url on the photo; keys: {sorted(photo)}"

		fetched = requests.get(url, timeout=30)
		assert fetched.status_code == 200, f"artifact not served at {url}: {fetched.status_code}"
		# Stored gzipped; requests does not transparently decode a .gz BODY
		# (that is Content-Encoding, not a gzip file), so unwrap it explicitly.
		body = json.loads(gzip.decompress(fetched.content))

		assert set(body) == {"accel", "gyro"}
		assert body["accel"]["t0_ms"] == IMU_SAMPLES["accel"]["t0_ms"]
		assert body["accel"]["dt_us"] == IMU_SAMPLES["accel"]["dt_us"]
		assert body["accel"]["x"] == IMU_SAMPLES["accel"]["x"]
		assert body["gyro"]["z"] == IMU_SAMPLES["gyro"]["z"]
		# The n-1 gap contract survived the whole trip.
		for kind in ("accel", "gyro"):
			assert len(body[kind]["dt_us"]) == len(body[kind]["x"]) - 1

	@pytest.mark.asyncio
	async def test_the_payload_matches_the_count_the_summary_claims(self):
		"""The end-to-end self-check, entirely server-side.

		`motion.imu_window.stored_count` is how many samples the device said this
		photo OWNS, and the payload is supposed to be exactly those. Both arrive
		here, so the two can be checked against each other with nothing from the
		phone — which is what made the on-device `imu_claims` CSV export
		unnecessary: the reconciliation it was added for is this assertion.

		A mismatch means the device's attribution and its payload disagree, which
		is the failure mode the claim table exists to prevent.
		"""
		# The device sends both halves: the summary in `motion.imu_window` and the
		# payload in `imu_samples`. stored_count is the sample total across
		# sensors, which is what the payload should hold.
		expected = sum(len(v["x"]) for v in IMU_SAMPLES.values())
		photo = await self._upload(self._base_metadata(
			imu_samples=IMU_SAMPLES,
			inertial={
				"gravity": [0.0, 0.0, 9.81],
				"imu_window": {
					"sample_count": expected,
					"window_start_ms": 1_700_000_000_000,
					"window_end_ms": 1_700_000_006_000,
					"stored_count": expected,
				},
			},
		))
		stored = (((photo.get("inertial") or {}).get("imu_window") or {})).get("stored_count")
		assert stored == expected, f"the summary did not survive the upload: {photo.get('inertial')}"

		body = json.loads(gzip.decompress(requests.get(photo["imu_samples_url"], timeout=30).content))
		carried = sum(len(v["x"]) for v in body.values())
		assert carried == stored, f"payload carries {carried} samples, summary claims {stored}"

	@pytest.mark.asyncio
	async def test_the_samples_never_enter_the_usercomment(self):
		"""The deliberate PROVENANCE_KEYS omission, verified where it matters.

		A time series in `exif_data` would be paid for by every reader of every
		photo detail response, forever. One string added to PROVENANCE_KEYS is all
		it would take, and no unit test would notice."""
		photo = await self._upload(self._base_metadata(imu_samples=IMU_SAMPLES))

		exif = photo.get("exif_data") or {}
		user_comment = (exif.get("data") or {}).get("UserComment") or ""
		assert user_comment, "expected a synthesized UserComment for a no-EXIF upload"
		prov = json.loads(user_comment)

		assert "imu_samples" not in prov, "the raw payload leaked into the UserComment"
		# Nor smuggled in under another name: no array of that length anywhere.
		assert "0.0123" not in user_comment, f"sample values leaked: {user_comment[:400]}"
		# The provenance the app DOES send still arrives, so this is not just an
		# upload that dropped everything.
		assert prov["location_source"] == "gps"

	@pytest.mark.asyncio
	async def test_the_url_is_public_because_reconstruction_is_not_private(self):
		"""Hillview is about sharing photos with position and orientation; a
		reconstruction limited to the caller's own frames reconstructs nowhere.
		So the URL rides the PUBLIC detail response too."""
		photo = await self._upload(self._base_metadata(imu_samples=IMU_SAMPLES))
		# The public detail endpoint keys on a composite UID, {source}-{id};
		# the owner response carries the bare id.
		uid = f"hillview-{photo['id']}"

		resp = requests.get(f"{API_URL}/photos/public/{uid}")
		assert resp.status_code == 200, f"public detail failed: {resp.status_code}"
		assert resp.json().get("imu_samples_url") == photo["imu_samples_url"]

	@pytest.mark.asyncio
	async def test_no_samples_means_no_artifact_and_no_url(self):
		"""Most uploads carry no window — an older app, a device with no
		gyroscope, an activity that did not ask for the IMU. None of that is an
		error, and none of it may invent a URL."""
		photo = await self._upload(self._base_metadata())
		assert photo.get("imu_samples_url") is None

	@pytest.mark.asyncio
	async def test_a_malformed_payload_is_dropped_without_failing_the_photo(self):
		"""The window is an enrichment. Losing it costs a reconstruction some
		precision; failing the upload costs the user their picture."""
		photo = await self._upload(self._base_metadata(imu_samples={
			"accel": {"t0_ms": 1_700_000_000_000, "dt_us": [2500],
					  "x": [0.1, 0.2], "y": [0.1], "z": [0.1, 0.2]},  # ragged
		}))
		assert photo.get("processing_status") == "completed"
		assert photo.get("imu_samples_url") is None
