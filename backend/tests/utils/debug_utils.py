#!/usr/bin/env python3
"""
Debug utilities using the centralized API client.
"""

import os
import sys
import json
import traceback
from datetime import datetime
from .api_client import api_client
from .auth_utils import auth_helper


def tprint(*args, **kwargs):
	"""Print with timestamp prefix."""
	ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
	print(f"[{ts}]", *args, **kwargs)


def debug_photos():
	"""Debug user's photos."""
	try:
		# Get test user token
		token = auth_helper.get_test_user_token("test")

		# Get photos
		photos_data = api_client.get_photos(token)
		photos = photos_data.get('photos', [])
		counts = photos_data.get('counts', {})

		print("📸 Photo Summary:")
		print(f"   Total: {counts.get('total', len(photos))}")
		print(f"   Completed: {counts.get('completed', 0)}")
		print(f"   Failed: {counts.get('failed', 0)}")
		print(f"   Authorized: {counts.get('authorized', 0)}")

		# Show error photos
		error_photos = api_client.get_error_photos(token)
		if error_photos:
			print(f"\n🚨 {len(error_photos)} photos with errors:")
			for photo in error_photos:
				print(f"   {photo['id']}: {photo.get('error', 'no error message')}")
				print(f"      Filename: {photo.get('original_filename', 'unknown')}")
				print(f"      Uploaded: {photo.get('uploaded_at', 'unknown')}")

		# Show recent photos
		if photos:
			print("\n📋 Recent photos:")
			for photo in photos[:5]:
				status = photo.get('processing_status', 'unknown')
				filename = photo.get('original_filename', 'unknown')
				print(f"   {photo['id'][:8]}... - {status} - {filename}")

	except Exception as e:
		print(f"❌ Error: {e}")


def debug_photo_details(photo_id: str):
	"""Get detailed photo info."""
	try:
		token = auth_helper.get_test_user_token("test")
		photo = api_client.get_photo_details(photo_id, token)

		print(f"📸 Photo {photo_id}:")
		print(f"   Status: {photo.get('processing_status', 'unknown')}")
		print(f"   Error: {photo.get('error', 'none')}")
		print(f"   Filename: {photo.get('original_filename', 'unknown')}")
		print(f"   Owner: {photo.get('owner_id', 'unknown')}")
		print(f"   Uploaded: {photo.get('uploaded_at', 'unknown')}")

		if photo.get('latitude') and photo.get('longitude'):
			print(f"   Location: {photo['latitude']}, {photo['longitude']}")
		if photo.get('bearing'):
			print(f"   Bearing: {photo['bearing']}°")
		if photo.get('sizes'):
			print(f"   Sizes: {list(photo['sizes'].keys())}")

	except Exception as e:
		print(f"❌ Error: {e}")


def recreate_users():
	"""Recreate test users."""
	try:
		print("recreate test users..")
		result = api_client.recreate_test_users()
		print("✅ Test users recreated")
		details = result.get("details", {})
		passwords = details.get("user_passwords", {})
		for username, password in passwords.items():
			print(f"   {username}: {password}")
	except Exception as e:
		print(f"❌ Error: {e}")


def set_password(username: str, password: str):
	"""Set password for a user."""
	import asyncio
	from sqlalchemy import select
	from common.database import SessionLocal
	from common.models import User
	from common.auth_utils import get_password_hash

	async def _set_password():
		async with SessionLocal() as db:
			result = await db.execute(select(User).where(User.username == username))
			user = result.scalars().first()

			if not user:
				print(f"❌ User '{username}' not found")
				return

			user.hashed_password = get_password_hash(password)
			await db.commit()
			print(f"✅ Password set for user '{username}'")

	try:
		asyncio.run(_set_password())
	except Exception as e:
		print(f"❌ Error: {e}")
		traceback.print_exc()


def cleanup_photos():
	"""Clean up user's photos."""
	try:
		token = auth_helper.get_test_user_token("test")
		count = api_client.cleanup_user_photos(token)
		print(f"🗑️ Deleted {count} photos")
	except Exception as e:
		print(f"❌ Error: {e}")


def setup_mock_mapillary():
	"""Set up mock Mapillary data for browser testing."""
	import math

	try:
		# Clear database first to avoid cache/mock confusion
		print("🗑️ Clearing database (including Mapillary cache)...")
		clear_db_result = api_client.clear_database()
		print(f"✓ {clear_db_result['message']}")
		print(f"   Deleted {clear_db_result['details']['mapillary_cache_deleted']} cached photos")
		print(f"   Deleted {clear_db_result['details']['cached_regions_deleted']} cached areas")

		# Clear existing mock data
		print("🧹 Clearing existing mock data...")
		clear_result = api_client.clear_mock_mapillary_data()
		print(f"✓ {clear_result['message']}")

		# Create mock data around Prague coordinates (same as tests)
		print("📍 Creating mock Mapillary data...")
		center_lat = (50.114739147066835 + 50.114119952930224) / 2  # ~50.11443
		center_lng = (14.523099660873413 + 14.523957967758179) / 2  # ~14.5235

		base_latitude = center_lat
		base_longitude = center_lng
		photos = []

		for i in range(1, 16):  # 1 to 15 inclusive
			# Distribute photos in a circle around center
			angle = (i * 24) % 360
			distance = 0.0001 * ((i % 3) + 1)  # Very small distances
			lat_offset = distance * math.sin(angle * math.pi / 180)
			lng_offset = distance * math.cos(angle * math.pi / 180)

			photos.append({
				'id': f"mock_mapillary_{i:03d}",
				'geometry': {
					'type': "Point",
					'coordinates': [base_longitude + lng_offset, base_latitude + lat_offset]
				},
				'bearing': (i * 24) % 360,
				'computed_bearing': (i * 24) % 360,
				'computed_rotation': 0.0,
				'sequence_id': f"mock_sequence_{(i-1)//5 + 1}",
				'captured_at': f"2023-07-{10+i:02d}T12:00:00Z",
				'organization_id': "mock_org_001"
			})

		mock_data = {'data': photos}
		set_result = api_client.set_mock_mapillary_data(mock_data)
		print(f"✅ {set_result['message']}")
		print(f"   Mock photos: {set_result['details']['photos_count']}")

		# Show cache info and warnings
		cache_info = set_result['details']['cache_info']
		print(f"   Cached photos: {cache_info['cached_photos']}")
		print(f"   Cached areas: {cache_info['cached_areas']}")
		if cache_info.get('warning'):
			print(f"⚠️  {cache_info['warning']}")

		print(f"   Center: {center_lat:.6f}, {center_lng:.6f}")
		print()
		print("🗺️ To test in browser:")
		print("   1. Open your frontend app in browser")
		print("   2. Navigate to the map")
		print("   3. Enable Mapillary source in source buttons")
		print("   4. Pan around Prague center to see mock photos")
		print(f"   5. Good test area: lat={center_lat:.4f}, lng={center_lng:.4f}")
		print()
		print("💡 Testing tip: Mock data only works when no cached data exists.")
		print("   If you see real Mapillary photos, cached data is being used instead.")

	except Exception as e:
		print(f"❌ Error: {e}")


def clear_mock_mapillary():
	"""Clear mock Mapillary data."""
	try:
		result = api_client.clear_mock_mapillary_data()
		print(f"✅ {result['message']}")
	except Exception as e:
		print(f"❌ Error: {e}")


def verify_signature(message_json: str, signature_base64: str, public_key_pem: str):
	"""Verify an ECDSA signature given message JSON, signature, and public key."""
	try:
		# Import the verification function from common
		sys.path.insert(0, '.')
		from common.security_utils import verify_ecdsa_signature

		# Parse the message JSON
		message_data = json.loads(message_json)

		print("🔐 Verifying ECDSA signature...")
		print(f"   Message: {message_json[:100]}{'...' if len(message_json) > 100 else ''}")
		print(f"   Signature: {signature_base64[:50]}...")
		print(f"   Public key: {public_key_pem[:50]}...")

		# Verify the signature
		is_valid = verify_ecdsa_signature(signature_base64, public_key_pem, message_data)

		if is_valid:
			print("✅ Signature is VALID")
		else:
			print("❌ Signature is INVALID")

		return is_valid

	except json.JSONDecodeError as e:
		print(f"❌ Invalid JSON message: {e}")
		return False
	except Exception as e:
		print(f"❌ Error: {e}")
		return False


def base64_to_pem(base64_key: str):
	"""Convert base64-encoded public key (from Android log) to PEM format and show fingerprint."""
	try:
		sys.path.insert(0, '.')
		from common.security_utils import generate_client_key_id

		# Remove any whitespace/newlines from the base64
		base64_clean = base64_key.strip().replace('\n', '').replace(' ', '')

		# Chunk into 64-char lines (standard PEM format)
		lines = [base64_clean[i:i+64] for i in range(0, len(base64_clean), 64)]
		formatted = '\n'.join(lines)

		# Create PEM
		pem = f"-----BEGIN PUBLIC KEY-----\n{formatted}\n-----END PUBLIC KEY-----"

		print("📜 PEM format:")
		print(pem)
		print()

		# Calculate fingerprint
		fingerprint = generate_client_key_id(pem)
		print(f"🔑 Key fingerprint (key_id): {fingerprint}")

		return pem, fingerprint

	except Exception as e:
		print(f"❌ Error: {e}")
		return None, None


async def _parallel_upload(items, parallel, get_image_data, token_or_manager, format_success, timeout=60, get_captured_at=None, anonymization_override=None, version=None, quality=None):
	"""Core parallel upload logic.

	Args:
		items: List of (index, filename, description, extra_data) tuples
		parallel: Number of concurrent uploads
		get_image_data: Callable(extra_data) -> (bytes, lat, lon)
		token_or_manager: Auth token string or TokenManager instance
		format_success: Callable(index, total, filename, photo_data, extra_data) -> str
		timeout: Processing timeout per photo
		get_captured_at: Optional callable() -> str. If None, captured_at is omitted
		                 and the worker extracts it from EXIF. For test images,
		                 use generate_test_captured_at from secure_upload_utils.
		anonymization_override: JSON string passed to worker. None=auto, "[]"=skip.
		version: Optional version number for authorize-upload request.
		quality: WebP quality (1-100). None=use worker default (97).
	"""
	import asyncio
	from .secure_upload_utils import SecureUploadClient
	from .test_utils import wait_for_photo_processing, API_URL

	def get_token():
		if isinstance(token_or_manager, str):
			return token_or_manager
		return token_or_manager.get_token()

	total = len(items)
	results = {"created": 0, "duplicates": 0, "failed": 0}
	semaphore = asyncio.Semaphore(parallel)

	# Register client keys ONCE before starting parallel uploads
	# This avoids hammering the API with concurrent key registrations
	upload_client = SecureUploadClient(api_url=API_URL)
	client_keys = upload_client.generate_client_keys()
	token = get_token()
	tprint("  Registering client key...")
	await upload_client.register_client_key(token, client_keys)
	tprint(f"  Starting {total} uploads with {parallel} parallel workers...")

	async def upload_one(item):
		i, filename, description, extra_data = item
		async with semaphore:
			try:
				image_data, lat, lon = get_image_data(extra_data)
				token = get_token()

				# For real files, omit captured_at - worker extracts from EXIF
				# For test images, caller provides get_captured_at callable
				captured_at = get_captured_at() if get_captured_at else None

				auth_data = await upload_client.authorize_upload_with_params(
					token, filename, len(image_data), lat, lon,
					description, is_public=True, file_data=image_data,
					captured_at=captured_at, version=version
				)

				# Allow overriding the server-supplied worker URL via env var
				worker_url_override = os.getenv("WORKER_URL")
				if worker_url_override:
					auth_data["worker_url"] = worker_url_override

				if auth_data.get("duplicate"):
					tprint(f"  [{i+1}/{total}] {filename} ⏭ duplicate")
					results["duplicates"] += 1
					return

				result = await upload_client.upload_to_worker(image_data, auth_data, client_keys, filename, anonymization_override=anonymization_override, quality=quality)
				photo_id = result.get('photo_id', auth_data.get('photo_id'))

				photo_data = wait_for_photo_processing(photo_id, get_token(), timeout=timeout)
				if photo_data['processing_status'] == 'completed':
					results["created"] += 1
					tprint(format_success(i, total, filename, photo_data, extra_data))
				else:
					results["failed"] += 1
					tprint(f"  [{i+1}/{total}] {filename} ✗ {photo_data.get('error', 'Unknown error')}")
			except Exception as e:
				results["failed"] += 1
				err_text = getattr(e, "message", None) or str(e) or repr(e) or e.__class__.__name__
				tprint(f"  [{i+1}/{total}] {filename} ✗ {err_text}")
				traceback.print_exc()

	await asyncio.gather(*[upload_one(item) for item in items])

	tprint(f"\n✅ Uploaded {results['created']}/{total} "
		   f"({results['duplicates']} duplicates, {results['failed']} failed)")


class TokenManager:
	"""Manages auth tokens with automatic refresh."""

	def __init__(self, user: str = None, password: str = None):
		from .test_utils import API_URL
		self.api_url = API_URL
		self.user = user
		self.password = password
		self.access_token = None
		self.refresh_token = None
		self.expires_at = None
		self._login()

	def _login(self):
		import requests
		from datetime import datetime
		if self.user and self.password:
			response = requests.post(
				f"{self.api_url}/auth/token",
				data={"username": self.user, "password": self.password},
				headers={"Content-Type": "application/x-www-form-urlencoded"}
			)
			if response.status_code != 200:
				raise Exception(f"Login failed: {response.status_code} - {response.text}")
			data = response.json()
			self.access_token = data["access_token"]
			self.refresh_token = data.get("refresh_token")
			expires_str = data.get("expires_at")
			if expires_str:
				self.expires_at = datetime.fromisoformat(expires_str.replace("Z", "+00:00"))
		else:
			self.access_token = auth_helper.get_test_user_token("test")
			self.refresh_token = None
			self.expires_at = None

	def get_token(self) -> str:
		"""Get current token, refreshing if needed."""
		from datetime import datetime, timezone
		# Refresh if expiring in less than 5 minutes
		if self.expires_at and self.refresh_token:
			now = datetime.now(timezone.utc)
			if (self.expires_at - now).total_seconds() < 300:
				self._refresh()
		return self.access_token

	def _refresh(self):
		import requests
		from datetime import datetime
		print("🔄 Refreshing auth token...")
		response = requests.post(
			f"{self.api_url}/auth/refresh",
			json={"refresh_token": self.refresh_token}
		)
		if response.status_code != 200:
			print("⚠️ Refresh failed, re-logging in...")
			self._login()
			return
		data = response.json()
		self.access_token = data["access_token"]
		self.refresh_token = data.get("refresh_token", self.refresh_token)
		expires_str = data.get("expires_at")
		if expires_str:
			self.expires_at = datetime.fromisoformat(expires_str.replace("Z", "+00:00"))


def _get_token(user: str = None, password: str = None) -> str:
	"""Get auth token - either from provided credentials or test user."""
	if user and password:
		import requests
		from .test_utils import API_URL
		response = requests.post(
			f"{API_URL}/auth/token",
			data={"username": user, "password": password},
			headers={"Content-Type": "application/x-www-form-urlencoded"}
		)
		if response.status_code != 200:
			raise Exception(f"Login failed: {response.status_code} - {response.text}")
		return response.json()["access_token"]
	else:
		return auth_helper.get_test_user_token("test")


def upload_random_photos(count: int = 10, parallel: int = 1, user: str = None, password: str = None, quality: int = None):
	"""Upload photos with randomized locations and bearings."""
	import asyncio
	import random
	from .image_utils import create_test_image_full_gps
	from .secure_upload_utils import generate_test_captured_at

	async def _upload():
		tprint(f"📸 Uploading {count} random photos (parallelism: {parallel})...")

		random.seed(42)
		token_manager = TokenManager(user, password)

		center_lat, center_lon = 50.08, 14.42
		items = []
		for i in range(count):
			lat = center_lat + random.uniform(-0.05, 0.05)
			lon = center_lon + random.uniform(-0.05, 0.05)
			bearing = random.uniform(0, 360)
			color = (random.randint(50, 255), random.randint(50, 255), random.randint(50, 255))
			filename = f"random_photo_{i+1:03d}.jpg"
			items.append((i, filename, f"Random test photo #{i+1}", (color, lat, lon, bearing)))

		def gen_image(extra):
			color, lat, lon, bearing = extra
			return create_test_image_full_gps(400, 300, color, lat, lon, bearing), lat, lon

		def format_success(i, total, filename, photo_data, extra):
			_, lat, lon, bearing = extra
			return f"  [{i+1}/{total}] {filename} ✓ lat={lat:.4f}, lon={lon:.4f}, bearing={bearing:.0f}°"

		# Test images need fake captured_at since they don't have real EXIF
		await _parallel_upload(items, parallel, gen_image, token_manager, format_success, timeout=30,
							   get_captured_at=generate_test_captured_at, quality=quality)

	try:
		asyncio.run(_upload())
	except Exception as e:
		print(f"❌ Error: {e}")
		traceback.print_exc()


def upload_files(files: list, parallel: int = 1, user: str = None, password: str = None, skip_anonymization: bool = False, version: int = None, description: str = None, quality: int = None):
	"""Upload files from command line paths."""
	import asyncio
	import os

	async def _upload():
		anon_msg = " (anonymization skipped)" if skip_anonymization else ""
		ver_msg = f" (version {version})" if version is not None else ""
		qual_msg = f" (quality {quality})" if quality is not None else ""
		tprint(f"📸 Uploading {len(files)} files (parallelism: {parallel}){anon_msg}{ver_msg}{qual_msg}...")

		token_manager = TokenManager(user, password)

		items = [(i, os.path.basename(f), description, f) for i, f in enumerate(files)]

		def read_file(filepath):
			with open(filepath, 'rb') as f:
				return f.read(), 0.0, 0.0

		def format_success(i, total, filename, photo_data, extra):
			lat = photo_data.get('latitude')
			lon = photo_data.get('longitude')
			bearing = photo_data.get('bearing')
			if lat and lon:
				loc = f" lat={lat:.4f}, lon={lon:.4f}"
				if bearing:
					loc += f", bearing={bearing:.0f}°"
			else:
				loc = ""
			return f"  [{i+1}/{total}] {filename} ✓{loc}"

		anon_override = "[]" if skip_anonymization else None
		await _parallel_upload(items, parallel, read_file, token_manager, format_success, timeout=60, anonymization_override=anon_override, version=version, quality=quality)

	try:
		asyncio.run(_upload())
	except Exception as e:
		print(f"❌ Error: {e}")
		traceback.print_exc()


def populate_photos(count: int = 4):
	"""Populate the database with test Hillview photos at fixed Prague locations."""
	import asyncio
	from .image_utils import create_test_image_full_gps
	from .secure_upload_utils import SecureUploadClient, generate_test_captured_at
	from .test_utils import wait_for_photo_processing, API_URL

	async def _populate():
		tprint(f"📸 Creating {count} test Hillview photos...")

		# Get auth token for test user
		token = auth_helper.get_test_user_token("test")

		upload_client = SecureUploadClient(api_url=API_URL)

		# Test photo data: filename, color, lat, lon, bearing
		photo_configs = [
			("prague_castle.jpg", (255, 0, 0), 50.0755, 14.4378, 45.0),      # Red - Prague Castle
			("old_town.jpg", (0, 255, 0), 50.0865, 14.4175, 90.0),           # Green - Old Town Square
			("wenceslas_sq.jpg", (0, 0, 255), 50.0819, 14.4362, 135.0),      # Blue - Wenceslas Square
			("charles_bridge.jpg", (255, 255, 0), 50.0870, 14.4208, 180.0),  # Yellow - Charles Bridge
			("vysehrad.jpg", (255, 0, 255), 50.0643, 14.4178, 225.0),        # Magenta - Vysehrad
			("petrin.jpg", (0, 255, 255), 50.0833, 14.3950, 270.0),          # Cyan - Petrin Hill
		]

		created = 0
		for i in range(min(count, len(photo_configs))):
			filename, color, lat, lon, bearing = photo_configs[i]

			tprint(f"  Uploading {filename}...")

			# Create image with full GPS data
			image_data = create_test_image_full_gps(400, 300, color, lat, lon, bearing)

			# Secure upload workflow
			client_keys = upload_client.generate_client_keys()
			await upload_client.register_client_key(token, client_keys)

			# Test images need fake captured_at since they don't have real EXIF
			auth_data = await upload_client.authorize_upload_with_params(
				token, filename, len(image_data), lat, lon,
				f"Test photo at {filename.replace('.jpg', '').replace('_', ' ')}",
				is_public=True, file_data=image_data,
				captured_at=generate_test_captured_at()
			)

			result = await upload_client.upload_to_worker(image_data, auth_data, client_keys, filename)
			photo_id = result.get('photo_id', auth_data.get('photo_id'))

			# Wait for processing
			photo_data = wait_for_photo_processing(photo_id, token, timeout=30)
			if photo_data['processing_status'] == 'completed':
				created += 1
				tprint(f"    ✓ {filename}: lat={photo_data.get('latitude'):.4f}, lon={photo_data.get('longitude'):.4f}, bearing={photo_data.get('bearing')}°")
			else:
				tprint(f"    ✗ {filename} failed: {photo_data.get('error', 'Unknown error')}")

		tprint(f"\n✅ Created {created}/{count} test photos")

	try:
		asyncio.run(_populate())
	except Exception as e:
		print(f"❌ Error: {e}")


def find_duplicate_md5s():
	"""Find photos with duplicate MD5 hashes."""
	import asyncio
	from sqlalchemy import select, func
	from common.database import SessionLocal
	from common.models import Photo, User

	async def _find():
		async with SessionLocal() as db:
			# Find MD5s that appear more than once
			subquery = (
				select(Photo.file_md5, func.count(Photo.id).label('count'))
				.where(Photo.file_md5.isnot(None))
				.group_by(Photo.file_md5)
				.having(func.count(Photo.id) > 1)
				.subquery()
			)

			# Get the actual photos with duplicate MD5s, joined with user
			query = (
				select(Photo.id, Photo.file_md5, Photo.original_filename, Photo.uploaded_at, User.username)
				.join(User, Photo.owner_id == User.id)
				.where(Photo.file_md5.in_(select(subquery.c.file_md5)))
				.order_by(Photo.file_md5, Photo.uploaded_at)
			)

			result = await db.execute(query)
			rows = result.all()

			if not rows:
				print("✅ No duplicate MD5 hashes found")
				return

			print(f"⚠️  Found {len(rows)} photos with duplicate MD5 hashes:\n")

			current_md5 = None
			for photo_id, file_md5, filename, uploaded_at, username in rows:
				if file_md5 != current_md5:
					if current_md5:
						print()
					print(f"MD5: {file_md5}")
					current_md5 = file_md5
				print(f"  {photo_id}  {username}  {filename}  ({uploaded_at})")

	try:
		asyncio.run(_find())
	except Exception as e:
		print(f"❌ Error: {e}")
		traceback.print_exc()


def set_analyses(distilled_json_path: str):
	"""Set analysis data for photos from a distilled.json file."""
	import requests
	from .test_utils import API_URL

	try:
		with open(distilled_json_path, 'r') as f:
			entries = json.load(f)

		tprint(f"📊 Setting analysis for {len(entries)} photos...")

		success = 0
		not_found = 0
		failed = 0

		for entry in entries:
			file_md5 = entry.get('original_file_md5')
			if not file_md5:
				tprint(f"  ⚠ Skipping entry without MD5")
				continue

			# Extract the fields we want to set
			analysis = {}
			for field in ['features', 'time_of_day', 'closest_object_distance', 'farthest_object_distance', 'location_type', 'scenic_score', 'visibility_distance', 'tallest_building']:
				if field in entry:
					analysis[field] = entry[field]

			if not analysis:
				continue

			try:
				response = requests.post(
					f"{API_URL}/hillview/internal/set-analysis",
					json={"file_md5": file_md5, "analysis": analysis}
				)

				if response.status_code == 200:
					success += 1
				elif response.status_code == 404:
					not_found += 1
				elif response.status_code == 409:
					# Multiple photos with same MD5 - stop processing
					detail = response.json().get('detail', 'Multiple photos found')
					print(f"\n❌ {detail}")
					print("Stopping - please resolve duplicate MD5 hashes before continuing.")
					return
				else:
					failed += 1
					tprint(f"  ✗ MD5 {file_md5[:16]}... failed: {response.status_code}")
			except Exception as e:
				failed += 1
				tprint(f"  ✗ MD5 {file_md5[:16]}... error: {e}")

		tprint(f"\n✅ Set analysis: {success} success, {not_found} not found, {failed} failed")

	except Exception as e:
		print(f"❌ Error: {e}")
		traceback.print_exc()


def main():
	"""Command-line interface."""
	if len(sys.argv) < 2:
		print("Usage:")
		print("  python debug_utils.py recreate              # Recreate test users")
		print("  python debug_utils.py set-password <user> <pass>  # Set user password")
		print("  python debug_utils.py photos                # Show user's photos")
		print("  python debug_utils.py photo <id>            # Show photo details")
		print("  python debug_utils.py cleanup               # Delete user's photos")
		print("  python debug_utils.py populate-photos       # Create test photos (fixed locations)")
		print("  python debug_utils.py populate-photos 6     # Create N test photos (max 6)")
		print("  python debug_utils.py upload-random-photos [N] [--parallel P] [--user U --pass P] [--quality Q]")
		print("  python debug_utils.py upload-files [--parallel P] [--user U --pass P] [--skip-anonymization] [--version N] [--quality Q] file1.jpg ...")
		print("  python debug_utils.py mock-mapillary        # Set up mock Mapillary data")
		print("  python debug_utils.py clear-mapillary       # Clear mock Mapillary data")
		print("  python debug_utils.py verify-signature <message_json> <signature_base64> <public_key_pem>")
		print("                                              # Verify ECDSA signature")
		print("  python debug_utils.py base64-to-pem <base64_key>")
		print("                                              # Convert Android pubkey to PEM & show fingerprint")
		print("  python debug_utils.py set-analyses <distilled.json>")
		print("                                              # Set photo analysis from distilled.json")
		print("  python debug_utils.py find-duplicate-md5s   # Find photos with duplicate MD5 hashes")
		return

	command = sys.argv[1]

	if command == "recreate":
		recreate_users()
	elif command == "set-password":
		if len(sys.argv) < 4:
			print("Usage: set-password <username> <password>")
		else:
			set_password(sys.argv[2], sys.argv[3])
	elif command == "photos":
		debug_photos()
	elif command == "photo" and len(sys.argv) > 2:
		debug_photo_details(sys.argv[2])
	elif command == "cleanup":
		cleanup_photos()
	elif command == "populate-photos":
		count = int(sys.argv[2]) if len(sys.argv) > 2 else 4
		populate_photos(count)
	elif command == "upload-random-photos":
		args = sys.argv[2:]
		count, parallel, user, password, quality = 10, 1, None, None, None
		positional = []
		i = 0
		while i < len(args):
			if args[i] == "--parallel":
				parallel = int(args[i + 1])
				i += 2
			elif args[i] == "--user":
				user = args[i + 1]
				i += 2
			elif args[i] == "--pass":
				password = args[i + 1]
				i += 2
			elif args[i] == "--quality":
				quality = int(args[i + 1])
				i += 2
			elif args[i].startswith("--"):
				print(f"Unknown option: {args[i]}")
				return
			else:
				positional.append(args[i])
				i += 1
		if positional:
			count = int(positional[0])
		upload_random_photos(count, parallel, user, password, quality=quality)
	elif command == "upload-files":
		args = sys.argv[2:]
		parallel, user, password = 1, None, None
		skip_anonymization = False
		version = None
		description = None
		quality = None
		files = []
		i = 0
		while i < len(args):
			if args[i] == "--parallel":
				parallel = int(args[i + 1])
				i += 2
			elif args[i] == "--user":
				user = args[i + 1]
				i += 2
			elif args[i] == "--pass":
				password = args[i + 1]
				i += 2
			elif args[i] == "--skip-anonymization":
				skip_anonymization = True
				i += 1
			elif args[i] == "--version":
				version = int(args[i + 1])
				i += 2
			elif args[i] == "--description":
				description = args[i + 1]
				i += 2
			elif args[i] == "--quality":
				quality = int(args[i + 1])
				i += 2
			elif args[i].startswith("--"):
				print(f"Unknown option: {args[i]}")
				return
			else:
				files.append(args[i])
				i += 1
		if not files:
			print("Usage: upload-files [--parallel N] [--user U --pass P] [--skip-anonymization] [--version N] [--description TEXT] [--quality Q] file1.jpg ...")
		else:
			upload_files(files, parallel, user, password, skip_anonymization=skip_anonymization, version=version, description=description, quality=quality)
	elif command == "mock-mapillary":
		setup_mock_mapillary()
	elif command == "clear-mapillary":
		clear_mock_mapillary()
	elif command == "verify-signature":
		if len(sys.argv) < 5:
			print("Usage: verify-signature <message_json> <signature_base64> <public_key_pem>")
			print("  message_json: JSON string of the message data")
			print("  signature_base64: Base64-encoded ECDSA signature")
			print("  public_key_pem: PEM-formatted ECDSA P-256 public key")
			return
		verify_signature(sys.argv[2], sys.argv[3], sys.argv[4])
	elif command == "base64-to-pem":
		if len(sys.argv) < 3:
			print("Usage: base64-to-pem <base64_key>")
			print("  base64_key: Base64-encoded public key from Android log")
			print("              (the value logged by: Base64.encodeToString(publicKey.encoded, NO_WRAP))")
			return
		base64_to_pem(sys.argv[2])
	elif command == "set-analyses":
		if len(sys.argv) < 3:
			print("Usage: set-analyses <distilled.json>")
			return
		set_analyses(sys.argv[2])
	elif command == "find-duplicate-md5s":
		find_duplicate_md5s()
	else:
		print(f"Unknown command: {command}")


if __name__ == "__main__":
	main()
