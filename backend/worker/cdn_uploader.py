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
				logger.info(f"CDN upload enabled for bucket: {self.bucket_name}")
			except Exception as e:
				logger.error(f"Failed to initialize S3 client: {e}")
				raise
		else:
			self.s3_client = None
			logger.info("CDN upload disabled")

	def upload_photo_sizes(self, sizes_info: Dict[str, Dict[str, Any]], unique_id: str) -> Dict[str, Dict[str, Any]]:
		"""
		Upload all photo sizes to CDN and return updated sizes_info with CDN URLs.

		Args:
			sizes_info: Dictionary of size variants with local paths
			unique_id: Unique identifier for this photo

		Returns:
			Updated sizes_info with cdn_url fields added

		Raises:
			Exception: If any upload fails (fail fast)
		"""
		if not self.enabled:
			return sizes_info

		updated_sizes = {}

		for size_key, size_data in sizes_info.items():
			local_path = size_data.get('path')
			if not local_path:
				raise ValueError(f"No path found for size {size_key}")

			# Full path to the file
			full_local_path = os.path.join("/app/uploads", local_path)

			if not os.path.exists(full_local_path):
				raise FileNotFoundError(f"Local file not found: {full_local_path}")

			# Generate CDN key/path
			cdn_key = f"photos/{unique_id}/{local_path}"

			# Upload to S3 - fail fast on error
			cdn_url = self._upload_file(full_local_path, cdn_key)
			if not cdn_url:
				raise RuntimeError(f"Failed to upload {size_key} to CDN")

			# Add CDN URL to size data
			updated_size_data = size_data.copy()
			updated_size_data['cdn_url'] = cdn_url
			updated_sizes[size_key] = updated_size_data
			logger.info(f"Uploaded {size_key} to CDN: {cdn_url}")

		logger.info(f"CDN upload completed: {len(updated_sizes)} sizes uploaded")
		return updated_sizes

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
