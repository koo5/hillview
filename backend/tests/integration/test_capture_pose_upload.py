#!/usr/bin/env python3
"""photos.pitch, photos.roll and photos.bearing_source through the real upload flow.

The capture stamp travels as upload metadata, the worker synthesizes the
UserComment from it, and the processed-photo handler derives pitch and roll
with common/capture_pose.py, in GPano conventions. The upload's own `pitch`
field, the positive-down tilt that rides along with the bearing, must not reach
the column as sent: that is how photos.pitch came to hold the wrong sign. It is
read only for an unstamped portrait photo, negated.

The stamp is a real one, from the deliberate roll series of 2026-11-15: the
camera looked 3.7° up with the scene turned clockwise by 22.9° in the frame.
See docs/todo/photo-pose-and-level-gates.md.
"""

import json
import os
import shlex
import subprocess
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

STAMP = {
	'attitude': {'pitch_deg': -3.741011, 'roll_deg': 22.856102, 'device_rotation_deg': 0},
	'inertial': {'gravity': [3.802262, 9.020489, -0.640069]},
	'capture_timing': {'metadata_version': 3},
}


def psql(query: str) -> str:
	default = ['docker', 'exec', '-i', 'hillview_postgres', 'psql',
			   '-U', os.getenv('POSTGRES_USER', 'hillview'), '-d', os.getenv('POSTGRES_DB', 'hillview')]
	command = shlex.split(os.environ['PANORAMAX_TEST_PSQL']) if 'PANORAMAX_TEST_PSQL' in os.environ else default
	result = subprocess.run(command + ['-v', 'ON_ERROR_STOP=1', '-tA'], input=query, text=True, capture_output=True)
	assert result.returncode == 0, result.stderr
	return result.stdout.strip()


class TestCapturePoseUpload(BasePhotoTest):

	async def _upload(self, metadata: dict, size=(640, 480)) -> str:
		upload_client = SecureUploadClient(api_url=API_URL)
		client_keys = upload_client.generate_client_keys()
		await upload_client.register_client_key(self.test_token, client_keys)

		image_data = create_test_image_no_exif(*size, (40, 120, 60))
		filename = "capture_pose_test.jpg"
		auth_data = await upload_client.authorize_upload_with_params(
			self.test_token, filename, len(image_data),
			PRAGUE_LAT, PRAGUE_LON, "capture pose test", True,
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
				status = resp.json().get("processing_status")
				if status in ("completed", "failed", "error"):
					assert status == "completed", f"processing failed: {resp.json().get('error')}"
					return photo_id
			time.sleep(1)
		pytest.fail(f"Photo {photo_id} processing timed out after 30s")

	@staticmethod
	def _metadata(**extra) -> dict:
		return {
			"latitude": PRAGUE_LAT,
			"longitude": PRAGUE_LON,
			"bearing": 90.0,
			"orientation_code": 1,
			"location_source": "gps",
			"captured_at": generate_test_captured_at(),
			**extra,
		}

	@staticmethod
	def _pose(photo_id: str) -> tuple:
		row = psql(f"SELECT pitch, roll, bearing_source FROM photos WHERE id = '{photo_id}';")
		pitch, roll, source = row.split('|')
		return (float(pitch) if pitch else None, float(roll) if roll else None, source or None)

	@pytest.mark.asyncio
	async def test_a_stamped_photo_gets_gpano_pitch_and_roll(self):
		# The upload's own pitch rides along, positive down; it must be ignored.
		photo_id = await self._upload(self._metadata(
			bearing_source="android-compass-true", pitch=-3.741011, **STAMP))
		pitch, roll, source = self._pose(photo_id)
		assert pitch == pytest.approx(3.741, abs=0.01)   # looking up: positive
		assert roll == pytest.approx(-22.856, abs=0.01)  # scene turned clockwise: negative
		assert source == "android-compass-true"
		# The info overlay reads these GPano values from the public record,
		# rather than displaying the raw stamp's opposite pitch/roll signs.
		public = requests.get(f"{API_URL}/photos/public/hillview-{photo_id}")
		assert public.status_code == 200, public.text
		assert public.json()["pitch"] == pytest.approx(pitch)
		assert public.json()["roll"] == pytest.approx(roll)

	@pytest.mark.asyncio
	async def test_an_unstamped_portrait_photo_keeps_its_upload_pitch_negated(self):
		# frontend2 before 2026-09-22: no attitude, only the positive-down upload pitch.
		photo_id = await self._upload(self._metadata(bearing_source="android-compass-true", pitch=12.0),
									  size=(480, 640))
		assert self._pose(photo_id) == (-12.0, None, "android-compass-true")

	@pytest.mark.asyncio
	async def test_an_unstamped_landscape_photo_has_no_pose(self):
		# That era's landscape pitch carries the landscape fault, so it is not read.
		photo_id = await self._upload(self._metadata(bearing_source="gps-kalman", pitch=10.0))
		assert self._pose(photo_id) == (None, None, "gps-kalman")
		public = requests.get(f"{API_URL}/photos/public/hillview-{photo_id}")
		assert public.status_code == 200, public.text
		assert public.json()["pitch"] is None
		assert public.json()["roll"] is None

	@pytest.mark.asyncio
	async def test_a_web_stamp_gets_gpano_pitch_and_roll(self):
		# The web app's stamp: `inertial` alone, from deviceorientation's
		# beta/gamma, with the keys frontend2 does not send. No attitude, no
		# capture_timing, no upload pitch. Portrait, 5° down, rolled 4° counterclockwise
		# (common/capture_pose_cases.json, 'portrait-down-5-ccw-4').
		inertial = {"gravity": [0.68147, 9.745536, 0.854699], "age_ms": 40,
					"gravity_source": "deviceorientation", "sample_count": 18,
					"window_ms": 300, "gravity_spread_deg": 0.8}
		photo_id = await self._upload(self._metadata(bearing_source="map", inertial=inertial),
									  size=(480, 640))
		pitch, roll, source = self._pose(photo_id)
		assert pitch == pytest.approx(-5.0, abs=0.01)
		assert roll == pytest.approx(-4.0, abs=0.01)
		assert source == "map"
		# The whole object reaches the stored UserComment, extra keys included.
		comment = json.loads(psql(f"SELECT exif_data->'data'->>'UserComment' FROM photos WHERE id = '{photo_id}';"))
		assert comment["inertial"] == inertial
