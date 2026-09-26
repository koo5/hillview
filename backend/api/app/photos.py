"""Photo file management utilities."""
import os
import shutil
import logging
import anyio
from pathlib import Path
from typing import List, Dict, Any

from common.config import resolve_pool_for_url

logger = logging.getLogger(__name__)

# Upload directory configuration
UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", "./uploads"))


def _local_path_for_url(url: str, pool: Dict[str, Any]) -> str:
	"""Map a stored URL to its on-disk path within a files-type pool."""
	suffix = url[len(pool["url"]):].lstrip('/')
	return os.path.join(pool["path"], suffix)


def _delete_local_file(url: str) -> bool:
	"""Delete one local file, resolving its pool from the URL."""
	pool = resolve_pool_for_url(url)
	if pool is None or pool.get('type') != 'files':
		logger.warning(f"No local pool resolves URL, cannot delete: {url}")
		return False

	path = _local_path_for_url(url, pool)
	if os.path.exists(path):
		os.remove(path)
		logger.info(f"Deleted photo file: {path}")
	else:
		logger.warning(f"File not found for deletion: {path}")
	return True


def _delete_local_tiles(tiles_url: str) -> bool:
	"""Delete a local DZI tiles directory tree, resolving its pool from the URL."""
	pool = resolve_pool_for_url(tiles_url)
	if pool is None or pool.get('type') != 'files':
		logger.warning(f"No local pool resolves DZI tiles URL, cannot delete: {tiles_url}")
		return False

	path = _local_path_for_url(tiles_url, pool)
	if os.path.isdir(path):
		shutil.rmtree(path, ignore_errors=True)
		logger.info(f"Deleted DZI tiles directory: {path}")
	return True


def _delete_one_url(url: str, what: str) -> bool:
	"""Delete a single stored file by URL, whichever pool kind it lives in.

	`_delete_size` exists for the `sizes` dict shape (a url plus an optional DZI
	pyramid); this is for a bare URL held in its own column — currently
	`photos.imu_samples_url`. Every such column needs a line in
	`_photo_artifact_urls` or it leaks one file per deleted photo, silently and
	forever, which is the failure mode this helper is here to make cheap to avoid.
	"""
	pool = resolve_pool_for_url(url)
	if pool is None:
		logger.warning(f"No pool resolves {what} URL, cannot delete: {url}")
		return False
	if pool.get('type') == 'cdn':
		from common.cdn_uploader import CDNUploader
		return CDNUploader.from_pool(pool).delete_size({'url': url}, what)
	return _delete_local_file(url)


def _delete_size(size_info: Dict[str, Any]) -> bool:
	"""Delete one size variant (and its DZI pyramid, if present), resolving the
	pool of each file independently so sizes may span pools."""
	url = size_info.get('url')
	if not url:
		return True

	success = True
	pool = resolve_pool_for_url(url)
	if pool is None:
		logger.warning(f"No pool resolves URL, cannot delete: {url}")
		return False

	if pool.get('type') == 'cdn':
		from common.cdn_uploader import CDNUploader
		success = CDNUploader.from_pool(pool).delete_size(size_info)
	else:
		success = _delete_local_file(url)
		# DZI pyramid: a .dzi descriptor plus a directory of tiles, each resolved
		# to its own pool (the descriptor is a regular file, the tiles a tree).
		pyramid = size_info.get('pyramid')
		if pyramid:
			if not _delete_local_file(pyramid['dzi_url']):
				success = False
			if not _delete_local_tiles(pyramid['tiles_url']):
				success = False

	return success


# Every column on `photos` that holds a URL to a file this service stored, other
# than the `sizes` dict itself. ADD TO THIS LIST when a new artifact column
# lands — the delete path is the one place a new column silently costs money
# rather than silently doing nothing.
_PHOTO_ARTIFACT_URL_COLUMNS = ('imu_samples_url',)


def photo_artifacts(photo) -> Dict[str, Any]:
	"""Capture everything one photo row references on disk.

	Called while the ORM object is still attached, because every sweep below runs
	AFTER its caller ends the read transaction (the idle-txn guardrail) and in a
	worker thread that must not touch the session.

	A record rather than a bare `sizes` dict so that adding an artifact column
	changes ONE function instead of four call sites — and so the change is a type
	error at each of them rather than a leak nobody notices.
	"""
	return {
		'sizes': photo.sizes,
		'urls': {c: getattr(photo, c, None) for c in _PHOTO_ARTIFACT_URL_COLUMNS},
	}


def _delete_photo_artifacts_sync(artifacts: Dict[str, Any]) -> bool:
	"""Delete one photo's files: its size variants, and its standalone URLs."""
	success = _delete_photo_sizes_sync(artifacts.get('sizes'))
	for what, url in (artifacts.get('urls') or {}).items():
		if url and not _delete_one_url(url, what):
			success = False
	return success


def _delete_photo_sizes_sync(sizes) -> bool:
	"""Delete every size variant (and its DZI pyramid) for one photo's `sizes` dict.

	Pure and synchronous: no DB, no ORM, no event loop — safe to run in a worker
	thread (see delete_photo_files / delete_photo_files_for_artifacts). File deletion is
	blocking (os.remove, shutil.rmtree, and boto3 for cdn pools), so it must never run
	on the event loop: on a large delete it would freeze every other request, and
	inside an open transaction it would sit "idle in transaction" long enough for the
	idle-txn guardrail to kill it.
	"""
	if not sizes:
		return True
	success = True
	for size_info in sizes.values():
		if not _delete_size(size_info):
			success = False
	return success


async def delete_photo_files_for_artifacts(all_artifacts: List[Dict[str, Any]]) -> int:
	"""Delete files for many photos from their captured artifact records, off the
	event loop. Session-independent by design: the caller captures the records with
	`photo_artifacts`, ends its read transaction, and only then calls this — so the
	(possibly long) sweep holds no transaction. Returns how many photos had all
	their files deleted.

	Takes artifact RECORDS, not bare `sizes` dicts. That was the earlier signature,
	and it made a new artifact column (`imu_samples_url`) a silent per-photo leak:
	nothing about passing `[p.sizes for p in photos]` looks wrong. Renamed
	deliberately so the compiler-equivalent — a missing name — visits every caller."""
	def _run() -> int:
		deleted = 0
		for artifacts in all_artifacts:
			try:
				if _delete_photo_artifacts_sync(artifacts):
					deleted += 1
				else:
					logger.error("Failed to delete some files for a photo")
			except Exception as e:
				logger.error(f"Exception deleting photo files: {e}")
		return deleted
	return await anyio.to_thread.run_sync(_run)


async def delete_photo_files(photo) -> bool:
	"""
	Delete physical files for a photo from its storage pool(s).

	Each size variant's pool is resolved independently from its stored URL via
	the FILE_POOLS registry, so a photo's sizes may live on different pools.

	Note: a graduated terrain overlay's depth buffer
	(terrain/<sha256>.depth.bin.gz, referenced from photo.terrain_overlay) is
	deliberately NOT deleted here. Those blobs are content-addressed and
	therefore SHARED — two photos fitted against the same terrain render point
	at one file — so per-photo deletion cannot know whether it is the last
	reference without a query this function has no session for. Reclaiming
	them safely means an offline sweep: list terrain/*.depth.bin.gz, subtract
	every URL still referenced by a non-deleted photo, delete the remainder.
	At ~117 KB per render the leak is small and bounded by the number of
	curated overlays; a wrong guess here would break click-anywhere on a photo
	that is still live.

	Args:
		photo: Photo model instance with sizes data

	Returns:
		True if successful, False otherwise.
	"""
	# Capture the artifact record before the thread hop: after a caller ends its
	# transaction the ORM object may be expired, and the worker thread must not
	# touch the session.
	artifacts = photo_artifacts(photo)
	try:
		return await anyio.to_thread.run_sync(_delete_photo_artifacts_sync, artifacts)
	except Exception as e:
		logger.warning(f"Error deleting files for photo {str(photo.id)}: {str(e)}")
		return False


async def delete_all_user_photo_files(photos: List) -> int:
	"""
	Delete physical files for all photos in a list.
	If ANY deletion fails, this is considered a failure.

	Args:
		photos: List of Photo model instances

	Returns:
		Number of photos whose files were successfully deleted.
		If this doesn't equal len(photos), some deletions failed.
	"""
	# Capture sizes now, while the ORM objects are still attached, then delete off the
	# event loop. Callers that must be guardrail-safe end their read transaction
	# before the sweep; see delete_photo_files_for_artifacts.
	all_artifacts = [photo_artifacts(photo) for photo in photos]
	deleted_count = await delete_photo_files_for_artifacts(all_artifacts)
	logger.info(f"Deleted files for {deleted_count}/{len(photos)} photos")
	return deleted_count
