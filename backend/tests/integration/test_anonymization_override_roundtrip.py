"""
Integration test for the precomputed-detections round-trip — the pics
pipeline's dev-check → prod flow in miniature.

Uploads a real photo with an unmissable truck three times (same bytes, same
user, version-bumped so the md5 dedup allows each re-upload):

  v1  auto        — the "dev server" leg: real YOLO runs; capture the
                    persisted detected_objects.
  v2  skip ("[]") — the unblurred pixel reference, and the manual-skip
                    record the override must NOT be confused with.
  v3  override    — the "prod" leg: the captured detections ride
                    anonymization_override; they must persist VERBATIM and
                    the truck region must actually get repainted.

The verbatim-persistence assertion is the loud canary for the old-worker
hazard (a worker without detections-mode parses the objects dict as an empty
rectangle list = skip, persisting {"objects": [], "manual": true} instead).
The pixel assertions catch a blur that silently no-ops while still
persisting nicely.
"""

import json
import os
import sys
from io import BytesIO

import httpx
import pytest
from PIL import Image, ImageChops, ImageStat

# Add the backend and tests directory to the path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from utils.secure_upload_utils import SecureUploadClient, generate_test_captured_at
from utils.test_utils import wait_for_photo_processing

ASSET = os.path.join(os.path.dirname(__file__), '..', 'assets', 'truck.jpg')

# YOLO vehicle classes (worker detections.TARGET_CLASSES). The subject is a
# truck, but car/bus/truck taxonomy is the model's call, not this test's —
# asserting "some blurred vehicle" keeps the test model-upgrade-proof.
VEHICLE_CLASS_IDS = {1, 2, 3, 5, 7}


def _intersects(a, b):
	return not (a[2] <= b[0] or a[0] >= b[2] or a[3] <= b[1] or a[1] >= b[3])


def _corner_away_from(w, h, boxes, size=32):
	"""A size×size corner patch intersecting none of ``boxes`` — the
	untouched reference region for the pixel comparison."""
	for cx, cy in ((0, 0), (w - size, 0), (0, h - size), (w - size, h - size)):
		patch = (cx, cy, cx + size, cy + size)
		if all(not _intersects(patch, b) for b in boxes):
			return patch
	pytest.skip("detections cover every corner; no clean reference patch")


def _mean_diff(diff_image):
	"""Largest per-channel MEAN of a difference image. Mean, not max: WebP
	re-allocates quantization globally when part of the frame changes, so
	isolated pixels far from the repaint can drift by ~30 between encodes —
	but the ripple's mean stays ~1-3 while a repaint's mean is 40+."""
	return max(ImageStat.Stat(diff_image).mean)


class TestAnonymizationOverrideRoundtrip:

	@pytest.fixture
	def upload_client(self):
		return SecureUploadClient(api_url=os.getenv("API_URL", "http://localhost:8055/api"))

	@pytest.mark.asyncio
	async def test_precomputed_detections_roundtrip(self, upload_client):
		with open(ASSET, 'rb') as f:
			file_bytes = f.read()

		setup_result = await upload_client.setup_test_environment()
		assert setup_result, "test environment setup failed"
		auth_token = await upload_client.test_user_auth(setup_result)
		client_keys = upload_client.generate_client_keys()
		await upload_client.register_client_key(auth_token, client_keys)

		async def upload(version, override=None):
			auth_data = await upload_client.authorize_upload_with_params(
				auth_token=auth_token,
				filename="truck.jpg",
				file_size=len(file_bytes),
				latitude=50.0755,
				longitude=14.4378,
				description="anonymization override roundtrip",
				is_public=True,
				file_data=file_bytes,
				captured_at=generate_test_captured_at(),
				version=version,
			)
			await upload_client.upload_to_worker(
				file_bytes, auth_data, client_keys, "truck.jpg",
				anonymization_override=override)
			photo = wait_for_photo_processing(
				auth_data["photo_id"], auth_token, timeout=300)
			assert photo.get("processing_status") == "completed", \
				f"v{version} processing failed: {photo.get('error')}"
			return auth_data["photo_id"], photo

		async def detections_of(photo_id):
			async with httpx.AsyncClient() as client:
				response = await client.get(
					f"{upload_client.api_url}/photos/{photo_id}/detections",
					headers={"Authorization": f"Bearer {auth_token}"},
					follow_redirects=True)
				response.raise_for_status()
				return response.json()["detected_objects"]

		async def full_image_of(photo):
			url = photo["sizes"]["full"]["url"]
			async with httpx.AsyncClient() as client:
				response = await client.get(url, follow_redirects=True)
				response.raise_for_status()
				return Image.open(BytesIO(response.content)).convert("RGB")

		# --- v1: auto — capture what the detector found -------------------
		print("\n--- v1: auto anonymization (capture detections) ---")
		photo_id, _ = await upload(version=1)
		captured = await detections_of(photo_id)
		assert captured and captured.get("objects"), \
			"auto run recorded no detections at all"
		assert not captured.get("manual")
		blurred_vehicles = [
			o for o in captured["objects"]
			if o.get("blurred") and o.get("class_id") in VEHICLE_CLASS_IDS
		]
		# Canary: if the model ever stops seeing this broadside truck,
		# that's worth a loud failure regardless of this feature.
		assert blurred_vehicles, \
			f"expected a blurred vehicle in the frame, got {captured['objects']}"

		# --- v2: skip — unblurred reference + the manual-skip record ------
		print("\n--- v2: skip anonymization (unblurred reference) ---")
		photo_id2, photo2 = await upload(version=2, override="[]")
		assert photo_id2 == photo_id, "same md5 + user should reuse the photo id"
		assert await detections_of(photo_id2) == {"objects": [], "manual": True}
		unblurred = await full_image_of(photo2)

		# --- v3: precomputed override — the prod leg ----------------------
		print("\n--- v3: precomputed detections override ---")
		photo_id3, photo3 = await upload(version=3, override=json.dumps(captured))
		persisted = await detections_of(photo_id3)
		assert persisted == captured, (
			"precomputed detections must persist VERBATIM; an override-as-skip "
			f"regression persists a manual record instead. Got: {persisted}")
		painted = await full_image_of(photo3)

		# --- pixels: repainted inside the detection, untouched outside ----
		assert painted.size == unblurred.size
		w, h = unblurred.size
		bbox = blurred_vehicles[0]["bbox"]
		x1, y1 = max(0, bbox["x1"]), max(0, bbox["y1"])
		x2, y2 = min(w, bbox["x2"]), min(h, bbox["y2"])
		assert x2 > x1 and y2 > y1

		diff = ImageChops.difference(unblurred, painted)
		inside = _mean_diff(diff.crop((x1, y1, x2, y2)))
		assert inside > 20, \
			f"override run did not visibly repaint the detected region (mean diff {inside:.1f})"
		# The reference patch must dodge EVERY blurred detection (the frame
		# has more than the one truck — e.g. the car at the edge).
		all_blurred_boxes = [
			(max(0, o["bbox"]["x1"]), max(0, o["bbox"]["y1"]),
			 min(w, o["bbox"]["x2"]), min(h, o["bbox"]["y2"]))
			for o in captured["objects"] if o.get("blurred")
		]
		corner = _corner_away_from(w, h, all_blurred_boxes)
		outside = _mean_diff(diff.crop(corner))
		assert outside < 8, (
			f"pixels far from every detection differ (mean diff {outside:.1f} in "
			f"{corner}) — the override run should only touch detected regions")

		print(f"✅ roundtrip ok: {len(captured['objects'])} objects persisted "
			  f"verbatim; region mean diff {inside:.1f}, reference patch {outside:.1f}")
