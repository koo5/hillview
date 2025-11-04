"""
CDN Upload Service for S3-compatible storage.

Uploads optimized photo sizes to S3-compatible CDN when BUCKET_NAME is configured.
Uses standard AWS environment variables: AWS_ENDPOINT_URL_S3, AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY
"""
import os
import logging
import mimetypes
from typing import Dict, Any, Optional

import boto3
from botocore.exceptions import ClientError, NoCredentialsError
from botocore.config import Config

logger = logging.getLogger(__name__)

class CDNUploader:
	"""S3-compatible CDN uploader for optimized photo sizes."""

	def __init__(self):
		self.bucket_name = os.getenv("BUCKET_NAME")
		self.cdn_base_url = os.getenv("CDN_BASE_URL")
		self.enabled = bool(self.bucket_name and self.cdn_base_url)

		if self.bucket_name and not self.cdn_base_url:
			logger.warning(f"BUCKET_NAME ({self.bucket_name}) set but CDN_BASE_URL missing - CDN upload disabled")

		if self.enabled:
			try:
				self.s3_client = boto3.client(
					's3',
					endpoint_url=os.getenv("AWS_ENDPOINT_URL_S3"),
					config=Config(s3={'addressing_style': 'virtual'}))
				logger.info(f"CDN configured for bucket: {self.bucket_name}")
			except Exception as e:
				logger.error(f"Failed to initialize S3 client: {e}")
				raise
		else:
			self.s3_client = None
			logger.info("CDN upload disabled")


	def delete_photo_sizes(self, sizes_info: Dict[str, Dict[str, Any]], unique_id: str) -> bool:
		"""
		Delete all photo sizes from CDN.

		Args:
			sizes_info: Dictionary of size variants with CDN URLs
			unique_id: Unique identifier for this photo

		Returns:
			True if all deletions succeeded, False if any failed
		"""
		if not self.enabled:
			return False

		success = True
		deleted_count = 0

		for size_key, size_data in sizes_info.items():
			cdn_key = size_data.get('url').replace(f"{self.cdn_base_url.rstrip('/')}/", "")

			if self._delete_file(cdn_key):
				deleted_count += 1
				logger.info(f"Deleted {size_key} from CDN: {cdn_key}")
			else:
				logger.error(f"Failed to delete {size_key} from CDN: {cdn_key}")
				success = False

		logger.info(f"CDN deletion completed: {deleted_count}/{len(sizes_info)} sizes deleted")
		return success

	def _delete_file(self, cdn_key: str) -> bool:
		"""
		Delete a single file from S3.

		Args:
			cdn_key: S3 object key to delete

		Returns:
			True if deletion succeeded, False if failed
		"""
		try:
			self.s3_client.delete_object(
				Bucket=self.bucket_name,
				Key=cdn_key
			)
			return True

		except (ClientError, NoCredentialsError, Exception) as e:
			logger.error(f"Error deleting {cdn_key}: {e}")
			return False

	def _upload_file(self, local_file_path: str, cdn_key: str) -> Optional[str]:
		"""
		Upload a single file to S3 and return its public URL.

		Args:
			local_file_path: Path to local file
			cdn_key: S3 object key

		Returns:
			Public URL of uploaded file, or None if failed
		"""
		try:
			# Determine content type
			content_type, _ = mimetypes.guess_type(local_file_path)
			if not content_type:
				content_type = 'application/octet-stream'

			# Upload to S3
			extra_args = {
				'ContentType': content_type,
				'ACL': 'public-read',
				'CacheControl': 'max-age=31536000'
			}

			self.s3_client.upload_file(
				local_file_path,
				self.bucket_name,
				cdn_key,
				ExtraArgs=extra_args
			)

			# Generate public URL using CDN_BASE_URL
			cdn_url = f"{self.cdn_base_url.rstrip('/')}/{cdn_key}"
			return cdn_url

		except (ClientError, NoCredentialsError, Exception) as e:
			logger.error(f"Error uploading {cdn_key}: {e}")
			return None

# Global CDN uploader instance
cdn_uploader = CDNUploader()
