"""Photo file management utilities."""
import os
import logging
from pathlib import Path
from typing import List, Dict, Any
from enum import Enum

logger = logging.getLogger(__name__)

# Upload directory configuration
UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", "./uploads"))


class StorageType(Enum):
	"""Photo storage type enumeration."""
	CDN = "cdn"
	LOCAL = "local"
	UNKNOWN = "unknown"


def determine_storage_type(size_data: Dict[str, Any]) -> StorageType:
	"""
	Determine storage type based on size data.

	Args:
		size_data: First size variant data from photo.sizes

	Returns:
		StorageType enum indicating where the photo is stored
	"""
	if not size_data or 'url' not in size_data:
		logger.warning(f"Size data is missing or lacks 'url' key: {size_data}")
		return StorageType.UNKNOWN

	cdn_base_url = os.getenv("CDN_BASE_URL")
	pics_url = os.getenv("PICS_URL")

	if cdn_base_url and size_data['url'].startswith(cdn_base_url):
		return StorageType.CDN
	elif pics_url and size_data['url'].startswith(pics_url):
		return StorageType.LOCAL
	else:
		logger.warning(f"Cannot determine storage type from URL: {size_data['url']}, CDN_BASE_URL: {cdn_base_url}, PICS_URL: {pics_url}")
		return StorageType.UNKNOWN


async def delete_photo_files(photo) -> bool:
	"""
	Delete physical files for a photo from CDN or local storage.

	Args:
		photo: Photo model instance with sizes data

	Returns:
		True if successful, False otherwise.
	"""
	try:
		if not photo.sizes:
			logger.debug(f"Photo {str(photo.id)} has no sizes to delete")
			return True

		# Check first size variant to determine storage type
		first_size_data = next(iter(photo.sizes.values()), None)
		storage_type = determine_storage_type(first_size_data)

		if storage_type == StorageType.CDN:
			# Photo is stored on CDN, use CDN deletion
			from common.cdn_uploader import cdn_uploader
			success = cdn_uploader.delete_photo_sizes(photo.sizes, photo.id)
			if not success:
				logger.warning(f"Some CDN files failed to delete for photo {str(photo.id)}")
			return success

		elif storage_type == StorageType.LOCAL:
			# Photo is stored locally, use filesystem deletion
			pics_url = os.getenv("PICS_URL")
			for size_info in photo.sizes.values():
				if 'url' in size_info:
					# Cut off PICS_URL prefix to get local path suffix
					local_path_suffix = size_info['url'][len(pics_url):].lstrip('/')
					full_path = os.path.join(UPLOAD_DIR, local_path_suffix)
					if os.path.exists(full_path):
						os.remove(full_path)
						logger.debug(f"Deleted photo file: {full_path}")
			return True

		else:
			logger.warning(f"Cannot determine photo storage type for photo {str(photo.id)}")
			return False

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
