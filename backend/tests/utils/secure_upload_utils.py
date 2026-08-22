"""
Secure Upload Workflow Utilities for Tests

This module provides reusable utilities for testing the secure three-phase upload workflow:
1. Client authentication & public key registration
2. Upload authorization from API server
3. Worker processing with client signature verification

Use these utilities instead of calling the old /upload endpoint directly.
"""

import httpx
import json
import base64
import contextlib
import os
from datetime import timedelta
import datetime
import uuid
from common.utc import utcnow, format_utc
from common.jwt_utils import generate_ecdsa_key_pair, serialize_private_key, serialize_public_key
import sys
import pytest
import hashlib
import asyncio
import random

# Add backend directory to path for imports
backend_dir = os.path.join(os.path.dirname(__file__), '..', '..')
sys.path.append(backend_dir)

from common.jwt_utils import generate_ecdsa_key_pair, serialize_private_key, serialize_public_key
from .test_utils import recreate_test_users


# TLS verification is ON unless explicitly disabled, and that default matters:
# this module is not test-only. backend/debug.sh -> utils.debug_utils is the
# production hillview CLI, and an unconditional verify=False there would make it
# silently accept ANY certificate — a real downgrade, on the upload path, in
# prod. So the loosening is opt-in and lives behind one env var, set by the test
# entry points only (see backend/tests/run_integration_tests.sh).
INSECURE_TLS_ENV = "HILLVIEW_INSECURE_TLS"


def tls_verify() -> bool:
	"""False only when the caller has explicitly opted out of verification."""
	return os.getenv(INSECURE_TLS_ENV, "").strip().lower() not in ("1", "true", "yes")


def dev_origin_client(**kwargs) -> httpx.AsyncClient:
	"""httpx client for URLs the APP advertises: the worker from authorize-upload,
	a photo's size URLs from its record.

	Following the advertised URL is the property under test — "the client uses
	the URL it was given" — and the one that must survive the worker moving to
	its own hostname, or becoming several for different task kinds. So when dev
	serves that URL from a Caddy origin whose `tls internal` CA Python does not
	trust, relax verification rather than routing around the URL, which would
	delete the coverage. The browser suite relaxes the same check, via
	`ignoreHTTPSErrors` in playwright.config.ts, against the same origin.

	Verification still applies unless HILLVIEW_INSECURE_TLS is set — see above.
	"""
	return httpx.AsyncClient(verify=tls_verify(), **kwargs)


class WorkerUnavailableError(Exception):
	"""Raised when the worker server can't be reached at its advertised URL.

	This is an expected, self-explanatory failure (the message already names the
	worker URL and underlying cause), so callers should print it plainly instead
	of dumping a full traceback.
	"""
	pass


# --- Upload backpressure handling -----------------------------------------
# The worker accepts only MAX_PENDING_TASKS concurrent uploads and rejects the
# rest with 503 (a client mid-upload may instead see a transport reset). For a
# bulk uploader (the luigi upload fan-out) these are transient "server busy"
# signals, not failures — the queue drains in seconds as in-flight uploads
# finish — so upload_to_worker retries them with bounded, jittered exponential
# backoff instead of surfacing queue-full as a hard upload failure. We
# deliberately do NOT follow the server's Retry-After verbatim: it's a static
# policy value (QUEUE_FULL_RETRY_AFTER_SECONDS, ~500s) meant for mobile clients
# that should back off for minutes, whereas a colocated bulk uploader wants to
# re-probe within seconds and a 503 is cheap (sent before the body is read).
# Bounded by a total wait budget so a genuinely wedged worker still surfaces
# instead of hanging forever; set HILLVIEW_UPLOAD_RETRY_BUDGET_S=0 to disable
# (fail fast on the first 503).
# Default ~8h: a long bulk run can sit behind sustained backpressure, and
# waiting is almost always better than failing a task — this budget is only the
# backstop for a genuinely wedged worker, not the expected wait.
_DEFAULT_UPLOAD_RETRY_BUDGET_S = 8 * 60 * 60


def _upload_retry_budget_s() -> float:
	try:
		return max(0.0, float(os.getenv(
			"HILLVIEW_UPLOAD_RETRY_BUDGET_S", str(_DEFAULT_UPLOAD_RETRY_BUDGET_S))))
	except (TypeError, ValueError):
		return float(_DEFAULT_UPLOAD_RETRY_BUDGET_S)


def _backpressure_delay(attempt: int, base: float = 0.5, cap: float = 20.0) -> float:
	"""Full-jittered exponential backoff (seconds) before upload retry ``attempt``.

	Full jitter (uniform in [0, ceiling]) decorrelates the many concurrent
	uploaders — separate luigi processes — so they don't retry in lockstep and
	re-saturate the worker the instant a slot frees.
	"""
	ceiling = min(base * (2 ** max(0, attempt - 1)), cap)
	return random.uniform(0.0, ceiling) if ceiling > 0 else 0.0


def generate_test_captured_at(minutes_ago: int = 10) -> str:
	"""Generate a fake captured_at timestamp for test images.

	Use this when uploading generated test images that don't have real EXIF data.
	Real file uploads should omit captured_at and let the worker extract it from EXIF.
	"""
	return format_utc(utcnow() - timedelta(minutes=minutes_ago))


class SecureUploadClient:
	"""
	Utility class for testing the secure upload workflow.

	Handles client key generation, signature creation, and the full three-phase workflow.
	"""

	def __init__(self, api_url: str = None):
		self.api_url = api_url or os.getenv("API_URL", "http://localhost:8055")
		self.client_keys = None
		self.key_id = None

	async def setup_test_environment(self):
		"""Set up test environment using shared test utility."""
		return recreate_test_users()


	def test_image(self):
		"""Create a test image file with EXIF data."""
		img = Image.new('RGB', (400, 300), color='blue')
		temp_file = tempfile.NamedTemporaryFile(suffix='.jpg', delete=False)
		img.save(temp_file.name, 'JPEG', quality=95)
		temp_file.close()

		yield temp_file.name
		os.unlink(temp_file.name)

	async def test_user_auth(self, setup_result):
		"""Get authentication token for the test user."""
		if not setup_result:
			raise Exception("Test environment not available")

		async with httpx.AsyncClient() as client:
			response = await client.post(f"{self.api_url}/auth/token", data={
				"username": "test",
				"password": "StrongTestPassword123!"
			})

			if response.status_code == 200:
				return response.json()["access_token"]
			else:
				raise Exception(f"Failed to get test user token: {response.status_code}")

	def client_key_pair(self):
		"""Generate a real ECDSA key pair for testing client operations."""
		sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

		private_key, public_key = generate_ecdsa_key_pair()
		return {
			"private_key": private_key,
			"public_key": public_key,
			"private_pem": serialize_private_key(private_key),
			"public_pem": serialize_public_key(public_key)
		}

	def generate_client_signature(self, client_private_key, photo_id: str, filename: str, timestamp: int) -> str:
		"""Generate a proper ECDSA client signature matching the API server's verification logic."""
		from cryptography.hazmat.primitives.asymmetric import ec
		from cryptography.hazmat.primitives import hashes

		# Create the exact message format matching frontend and API server verification.
		# Frontend: JSON.stringify([filename, photo_id, timestamp], null, 0)  — raw unicode
		# Server:   json.dumps(..., separators=(',',':'), ensure_ascii=False, sort_keys=True)
		# ensure_ascii=False is critical: without it, non-ASCII filenames (emojis etc.)
		# get \uXXXX-escaped, producing a different string than the server expects.
		message_data = [filename, photo_id, timestamp]
		message = json.dumps(message_data, separators=(',', ':'), ensure_ascii=False)

		# Sign the message using the client's private key
		signature_bytes = client_private_key.sign(
			message.encode('utf-8'),
			ec.ECDSA(hashes.SHA256())
		)

		# Return base64-encoded signature
		return base64.b64encode(signature_bytes).decode('ascii')

	def generate_client_keys(self):
		"""Generate ECDSA key pair for client operations."""
		if not self.client_keys:
			private_key, public_key = generate_ecdsa_key_pair()
			self.client_keys = {
				"private_key": private_key,
				"public_key": public_key,
				"private_pem": serialize_private_key(private_key),
				"public_pem": serialize_public_key(public_key)
			}
		return self.client_keys

	async def register_client_key(self, auth_token: str, client_key_pair: dict = None):
		"""Phase 1: Register client public key with the API server."""
		if not client_key_pair:
			client_key_pair = self.generate_client_keys()

		# Test authentication first
		async with httpx.AsyncClient() as client:
			response = await client.get(
				f"{self.api_url}/auth/me/",
				headers={"Authorization": f"Bearer {auth_token}"},
				follow_redirects=True,
				# Match the sibling register-client-key POST below: without an
				# explicit timeout httpx defaults to 5s, which a backend under a
				# thundering herd of concurrent uploaders can't always answer in
				# time — that 5s ReadTimeout was the spurious upload failure.
				timeout=600_00.0,
			)
			if response.status_code != 200:
				print(f"❌ Phase 1a failed: {response.status_code} - {response.text}")
				raise Exception(f"Authentication test failed: {response.status_code} - {response.text}")
			#print("✅ Phase 1a: Client authentication successful")

			# Register client public key
			key_id = client_key_pair.get("key_id", f"test-key-{datetime.datetime.now().strftime('%Y%m%d-%H%M%S')}-{str(uuid.uuid4())[:8]}")
			response = await client.post(
				f"{self.api_url}/auth/register-client-key",
				json={
					"public_key_pem": client_key_pair["public_pem"],
					"key_id": key_id,
					"created_at": datetime.datetime.now().isoformat()
				},
				headers={"Authorization": f"Bearer {auth_token}"},
				timeout=600_00.0
			)

			if response.status_code in [200, 201]:
				key_data = response.json()
				#print(f"✅ Phase 1b: Client key registered successfully")
				#print(f"✅  Key ID: {key_data.get('key_id', 'unknown')}")
				# Store the key_id for later use
				self.key_id = key_data.get('key_id', key_id)
				return key_data
			else:
				raise Exception(f"Client key registration failed: {response.status_code} - {response.text}")

	async def _request_upload_authorization(self, auth_token: str, upload_request: dict):
		"""Internal method to make upload authorization request and handle response."""
		async with httpx.AsyncClient() as client:

			request_start_time = utcnow()

			response = await client.post(
				f"{self.api_url}/photos/authorize-upload",
				json=upload_request,
				headers={"Authorization": f"Bearer {auth_token}"},
				timeout=600_00.0
			)

			request_end_time = utcnow()
			request_duration = (request_end_time - request_start_time).total_seconds()
			print(f"   Upload authorization request took {request_duration:.2f} seconds")


			if response.status_code == 200:
				auth_data = response.json()
				if auth_data.get("duplicate"):
					return auth_data
				assert "upload_jwt" in auth_data
				assert "worker_url" in auth_data
				assert "photo_id" in auth_data
				return auth_data
			elif response.status_code == 404:
				raise Exception("Upload authorization endpoint not implemented")
			else:
				raise Exception(f"Upload authorization failed: {response.status_code} - {response.text}")

	async def authorize_upload(self, auth_token: str, filename: str = "secure_test.jpg", **kwargs):
		"""Test Phase 2: Request upload authorization from API with default test values."""
		auth_data = await self.authorize_upload_with_params(
			auth_token=auth_token,
			filename=filename,
			file_size=5120,
			latitude=50.0755,
			longitude=14.4378,
			description="End-to-end secure upload test",
			is_public=True
		)
		print("✅ Phase 2: Upload authorization successful")
		print(f"   Photo ID: {auth_data['photo_id']}")
		print(f"   Worker URL: {auth_data['worker_url']}")
		return auth_data

	async def authorize_upload_with_params(self, auth_token: str, filename: str, file_size: int,
										   latitude: float, longitude: float, description: str,
										   is_public: bool = True, file_data=None,  # bytes, or a path str (see docstring)
										   captured_at: str = None, version: int = None,
										   license: str = 'ccbysa4+osm',
										   title: str = None, keywords: list = None,
										   featured: bool = False,
										   fast_md5: bool = False):
		"""Request upload authorization with custom parameters.

		Args:
			file_data: File bytes, or a filesystem path (str). A path is hashed
			           from disk in chunks (same digest as hashing the whole
			           bytes) so a multi-GB pano never has to fit in RAM; pass
			           the same path to upload_to_worker so the body streams too.
			           KNOWN DISCREPANCY (accepted 2026-08-14): with a path the
			           file is read twice — once here for the MD5, once in
			           upload_to_worker for the body — while the bytes variant
			           hashes the exact in-memory snapshot it uploads. If the
			           file changes between the two reads, the stored file_md5
			           (duplicate detection, MD5-based lookup) silently disagrees
			           with the uploaded bytes: the worker does NOT re-verify the
			           body against the authorized hash. Only pass paths to files
			           that are immutable for the duration of the upload.
			captured_at: Optional ISO timestamp. If None, the server will extract it from EXIF.
			             For test images without real EXIF, use generate_test_captured_at().
			version: Optional version number. If >1, allows re-uploading completed photos.
			fast_md5: Path input only — hash just the first MiB + byte length
			          instead of the whole file (see the inline comment for the
			          dedup-identity trade-off).
		"""

		hash_start_time = utcnow()

		if isinstance(file_data, str):
			hasher = hashlib.md5()
			with open(file_data, 'rb') as f:
				if fast_md5:
					# --fast-md5: identity = first MiB + byte length, not the
					# full content. Trades dedup rigor for skipping a full read
					# of a multi-GB pano; two DIFFERENT files that share their
					# first MiB and exact size would collide (accepted). Same
					# file always maps to the same id either way — but note a
					# file's fast id differs from its full-hash id, so switching
					# the flag between runs re-uploads instead of deduping.
					hasher.update(f.read(1024 * 1024))
					hasher.update(str(os.path.getsize(file_data)).encode())
				else:
					for chunk in iter(lambda: f.read(8 * 1024 * 1024), b''):
						hasher.update(chunk)
			file_md5 = hasher.hexdigest()
		elif file_data:
			file_md5 = hashlib.md5(file_data).hexdigest()
		else:
			file_md5 = hashlib.md5(f"{filename}_{file_size}".encode()).hexdigest()

		hash_end_time = utcnow()
		hash_duration = (hash_end_time - hash_start_time).total_seconds()
		print(f"   Calculated file MD5: {file_md5} (took {hash_duration:.2f} seconds){' (fast-md5: first MiB + size)' if fast_md5 else ''}")

		upload_request = {
			"filename": filename,
			"content_type": get_content_type(filename),
			"file_size": file_size,
			"file_md5": file_md5,
			"client_key_id": getattr(self, 'key_id', None),
			"latitude": latitude,
			"longitude": longitude,
			"description": description,
			"is_public": is_public,
			"license": license,
		}

		# Only include title/keywords when set, so non-pipeline callers are unchanged.
		if title is not None:
			upload_request["title"] = title
		if keywords is not None:
			upload_request["keywords"] = keywords
		# featured is admin-only server-side. Only send it when actually requested:
		# omitting it on the false/default path keeps the request byte-identical to
		# pre-feature clients (backwards compatibility — an older API server never
		# sees an unknown field, and the schema default fills in False).
		if featured:
			upload_request["featured"] = True

		# Only include captured_at if explicitly provided
		if captured_at is not None:
			upload_request["captured_at"] = captured_at

		if version is not None:
			upload_request["version"] = version

		if not upload_request["client_key_id"]:
			raise Exception("client_key_id is required - make sure to call register_client_key first")

		return await self._request_upload_authorization(auth_token, upload_request)

	async def upload_to_worker(self, file_input, auth_data, client_keys, filename="secure_test.jpg", timeout: float = 600_00.0, anonymization_override: str = None, quality: int = None, fast: bool = False, metadata: str = None, keep_pics_in_worker: bool = False, no_upload: bool = False, local_pyramid_path: str = None):
		"""Phase 3: Upload file to worker with proper client signature.

		Args:
			file_input: Either a file path (str) or file data (bytes). A path is
			            streamed from disk instead of loaded into memory — see
			            authorize_upload_with_params for the hash/body
			            double-read discrepancy that comes with paths.
			anonymization_override: JSON string - None=auto, "[]"=skip anonymization
			quality: WebP quality (1-100). None=use worker default (97).
			fast: Skip pyramid, 640_llm, EXIF copy, use fast WebP encoding.
			metadata: JSON string (BrowserMetadata schema) — lat/lon/bearing/etc
			          fallback for formats that can't carry EXIF (e.g. EXR).
			keep_pics_in_worker: serve artifacts from the worker's own uploads
			          volume instead of shipping them to the API's storage pool.
			          The worker 400s unless it runs with ALLOW_KEEP_PICS_IN_WORKER.
			no_upload: send only the file's PATH (file_input must be a path the
			          worker can see under its LOCAL_PHOTO_ROOTS mounts) — no
			          body transfer at all. The worker walks symlinks and
			          validates containment itself, so the path is sent as
			          given. 400s unless the worker has LOCAL_PHOTO_ROOTS.
			local_pyramid_path: OFFER an externally rendered DZI pyramid
			          (<prefix>.dzi, tiles in <prefix>_files/ beside it) that the
			          worker MAY use instead of rendering its own — the worker
			          decides from anonymization / dev-vs-prod / parameter
			          policy, and declining is silent. Same LOCAL_PHOTO_ROOTS
			          gate as no_upload.
		"""
		upload_jwt = auth_data["upload_jwt"]
		worker_url = auth_data["worker_url"]
		photo_id = auth_data["photo_id"]

		# Get timestamp - now comes as Unix timestamp directly
		timestamp = auth_data["upload_authorized_at"]

		client_signature = self.generate_client_signature(
			client_keys["private_key"],
			photo_id,
			filename,
			timestamp
		)

		async with contextlib.AsyncExitStack() as stack:
			client = await stack.enter_async_context(dev_origin_client())
			# Handle both file paths and file data
			if no_upload:
				if isinstance(file_input, bytes):
					raise ValueError("no_upload requires a file path, not bytes")
				# Path-only ingestion: no file part, no body transfer — the
				# worker reads the file itself from its LOCAL_PHOTO_ROOTS
				# mounts (and walks any symlinks server-side).
				files = None
			elif isinstance(file_input, bytes):
				# File data provided directly
				files = {'file': (filename, file_input, 'image/jpeg')}
			else:
				# File path provided: hand httpx the open file so the multipart
				# body streams from disk in 64 KiB chunks. Reading the whole
				# file into one bytes blob gave the TLS layer the entire body as
				# a single write, and OpenSSL's outgoing buffer then had to hold
				# the whole encrypted request in one contiguous allocation — on
				# a multi-GB pano that fails as "SSLError: [BUF] malloc failure
				# (_ssl.c)". httpx rewinds seekable files (seek(0)) on every
				# send, so the backpressure retries below still transmit the
				# full body.
				f = stack.enter_context(open(file_input, 'rb'))
				files = {'file': (filename, f, get_content_type(filename))}

			data = {'client_signature': client_signature}
			if anonymization_override is not None:
				data['anonymization_override'] = anonymization_override
			if quality is not None:
				data['quality'] = str(quality)
			if fast:
				data['fast'] = 'true'
			if metadata is not None:
				data['metadata'] = metadata
			if keep_pics_in_worker:
				data['keep_pics_in_worker'] = 'true'
			if no_upload:
				data['local_photo_path'] = file_input
			if local_pyramid_path:
				data['local_pyramid_path'] = local_pyramid_path
			headers = {
				'Authorization': f'Bearer {upload_jwt}',
				'Expect': '100-continue'
			}

			await self.test_worker_server_connectivity(worker_url)

			# Backpressure-aware retry: a 503 (queue full) or a transport reset is
			# the worker telling us it's busy, not that the upload failed. Retry
			# with bounded jittered backoff so a bulk uploader can saturate the
			# worker; any other non-200 (bad license/auth/payload) is permanent
			# and re-raised at once. See the notes above _backpressure_delay.
			budget_s = _upload_retry_budget_s()
			waited_s = 0.0
			attempt = 0
			while True:
				attempt += 1
				try:
					response = await client.post(
						f"{worker_url}/upload",
						files=files,
						data=data,
						headers=headers,
						timeout=timeout
					)
				except httpx.TransportError as e:
					delay = _backpressure_delay(attempt)
					if waited_s + delay > budget_s:
						raise WorkerUnavailableError(
							f"Worker upload to {worker_url} kept hitting transport "
							f"errors after {waited_s:.1f}s / {attempt} attempt(s): {e}"
						) from e
					await asyncio.sleep(delay)
					waited_s += delay
					continue

				if response.status_code == 200:
					return response.json()

				if response.status_code == 503:
					delay = _backpressure_delay(attempt)
					if waited_s + delay > budget_s:
						# Budget exhausted: surface the queue-full rather than lose
						# it silently (fail fast at the boundary).
						raise Exception(
							f"Worker upload failed: 503 - still backpressured after "
							f"{waited_s:.1f}s / {attempt} attempt(s): {response.text}"
						)
					await asyncio.sleep(delay)
					waited_s += delay
					continue

				raise Exception(f"Worker upload failed: {response.status_code} - {response.text}")


	async def test_worker_token_validation(self, test_user_auth):
		"""Test that worker properly validates JWT authorization tokens."""
		# First get a valid authorization to get the worker URL
		auth_data = await self.authorize_upload(test_user_auth, "test.jpg")
		worker_url = auth_data["worker_url"]

		# Test with invalid token
		async with dev_origin_client() as client:
			try:
				fake_token = "invalid.jwt.token"
				files = {'file': ('test.jpg', b'fake image', 'image/jpeg')}
				data = {'client_signature': 'fake_sig'}
				headers = {'Authorization': f'Bearer {fake_token}'}

				response = await client.post(
					f"{worker_url}/upload",
					files=files,
					data=data,
					headers=headers
				)

				# Worker should reject invalid token
				assert response.status_code == 401
				print("✅ Worker correctly rejects invalid JWT tokens")

			except httpx.ConnectError:
				raise Exception("Worker not available")

	async def test_api_server_connectivity(self):
		"""Test basic API server health."""
		async with httpx.AsyncClient() as client:
			response = await client.get(f"{self.api_url}/debug")
			assert response.status_code == 200
			assert response.json()["status"] == "ok"

	async def test_worker_server_connectivity(self, worker_url: str = None):
		"""Test basic worker server health."""
		if worker_url is None:
			worker_url = os.getenv("TEST_WORKER_URL", "http://localhost:8056")
		try:
			async with dev_origin_client() as client:
				response = await client.get(f"{worker_url}/health", timeout=100.0)
				if response.status_code == 200:
					print(f"✅ Worker server is healthy ({worker_url})")
				else:
					print(f"⚠️ Worker server at {worker_url} returned {response.status_code}")
		except httpx.ConnectError as e:
			raise WorkerUnavailableError(f"Worker server not available at {worker_url} (from upload authorization): {e}") from None


def get_content_type(filename: str) -> str:
	"""Get content type based on file extension."""
	ext = os.path.splitext(filename)[1].lower()
	if ext in ['.jpg', '.jpeg']:
		return 'image/jpeg'
	elif ext == '.png':
		return 'image/png'
	elif ext == '.gif':
		return 'image/gif'
	elif ext == '.bmp':
		return 'image/bmp'
	elif ext == '.webp':
		return 'image/webp'
	elif ext in ['.tiff', '.tif']:
		return 'image/tiff'
	elif ext == '.exr':
		return 'image/x-exr'
	elif ext == '.cr2':
		return 'image/x-canon-cr2'
	else:
		return 'application/octet-stream'


if __name__ == "__main__":
	# Run with: python -m pytest tests/test_secure_upload_workflow.py -v -s
	pytest.main([__file__, "-v", "-s", "--tb=short"])
