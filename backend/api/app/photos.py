"""Photo file management utilities."""
import os
import shutil
import logging
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


async def delete_photo_files(photo) -> bool:
	"""
	Delete physical files for a photo from its storage pool(s).

	Each size variant's pool is resolved independently from its stored URL via
	the FILE_POOLS registry, so a photo's sizes may live on different pools.

	Args:
		photo: Photo model instance with sizes data

	Returns:
		True if successful, False otherwise.
	"""
	try:
		if not photo.sizes:
			logger.debug(f"Photo {str(photo.id)} has no sizes to delete")
			return True

		success = True
		for size_info in photo.sizes.values():
			if not _delete_size(size_info):
				success = False
		return success

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
	deleted_count = 0
	for photo in photos:
		try:
			success = await delete_photo_files(photo)
			if success:
				deleted_count += 1
			else:
				logger.error(f"Failed to delete files for photo {str(photo.id)}")
		except Exception as e:
			logger.error(f"Exception deleting files for photo {str(photo.id)}: {str(e)}")

	logger.info(f"Deleted files for {deleted_count}/{len(photos)} photos")
	return deleted_count
