"""
CDN Upload Service for S3-compatible storage.

Uploads optimized photo sizes to S3-compatible CDN when BUCKET_NAME is configured.
Uses standard AWS environment variables: AWS_ENDPOINT_URL_S3, AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY
"""
import os
import json
import logging
import mimetypes
from typing import Dict, Any, Optional

import boto3
from botocore.exceptions import ClientError, NoCredentialsError
from botocore.config import Config

logger = logging.getLogger(__name__)

class CDNUploader:
	"""S3-compatible CDN uploader for optimized photo sizes.

	A single instance targets one bucket/endpoint. Construct from env (the
	module-level `cdn_uploader`, used by the worker's write path) or per pool
	via `from_pool()` (used by the API to delete from any registered CDN).
	"""

	def __init__(self, bucket_name: Optional[str] = None, cdn_base_url: Optional[str] = None,
				 endpoint_url: Optional[str] = None, access_key_id: Optional[str] = None,
				 secret_access_key: Optional[str] = None, addressing_style: str = "virtual"):
		self.bucket_name = bucket_name
		self.cdn_base_url = cdn_base_url
		self.enabled = bool(self.bucket_name and self.cdn_base_url)

		if self.bucket_name and not self.cdn_base_url:
			logger.warning(f"BUCKET_NAME ({self.bucket_name}) set but CDN_BASE_URL missing - CDN upload disabled")

		if self.enabled:
			try:
				self.s3_client = boto3.client(
					's3',
					endpoint_url=endpoint_url,
					aws_access_key_id=access_key_id,
					aws_secret_access_key=secret_access_key,
					config=Config(s3={'addressing_style': addressing_style}))
				logger.info(f"CDN configured for bucket: {self.bucket_name}")
			except Exception as e:
				logger.error(f"Failed to initialize S3 client: {e}")
				raise
		else:
			self.s3_client = None
			logger.info("CDN upload disabled")

	@classmethod
	def from_pool(cls, pool: Dict[str, Any]) -> "CDNUploader":
		"""Build an uploader for a cdn-type pool from the storage registry.

		Credentials come from the pool's `secrets_file` (JSON with
		`access_key_id`/`secret_access_key`) when present.
		"""
		access_key_id = secret_access_key = None
		secrets_file = pool.get("secrets_file")
		if secrets_file:
			with open(secrets_file) as f:
				creds = json.load(f)
			access_key_id = creds["access_key_id"]
			secret_access_key = creds["secret_access_key"]
		return cls(
			bucket_name=pool.get("bucket"),
			cdn_base_url=pool.get("url"),
			endpoint_url=pool.get("endpoint"),
			access_key_id=access_key_id,
			secret_access_key=secret_access_key,
			addressing_style=pool.get("addressing_style", "virtual"),
		)

	def _url_to_key(self, url: str) -> str:
		"""Strip the CDN base URL to recover the S3 object key."""
		return url.replace(f"{self.cdn_base_url.rstrip('/')}/", "")


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
			if self.delete_size(size_data, size_key):
				deleted_count += 1
			else:
				success = False

		logger.info(f"CDN deletion completed: {deleted_count}/{len(sizes_info)} sizes deleted")
		return success

	def delete_size(self, size_data: Dict[str, Any], size_key: str = '') -> bool:
		"""Delete a single size variant (and its DZI pyramid, if present) from CDN."""
		success = True
		cdn_key = self._url_to_key(size_data.get('url'))

		if self._delete_file(cdn_key):
			logger.info(f"Deleted {size_key} from CDN: {cdn_key}")
		else:
			logger.error(f"Failed to delete {size_key} from CDN: {cdn_key}")
			success = False

		# A size may carry a DZI pyramid: a .dzi descriptor plus a directory
		# tree of tiles. Delete the descriptor and sweep the tiles by prefix.
		pyramid = size_data.get('pyramid')
		if pyramid:
			if not self._delete_file(self._url_to_key(pyramid['dzi_url'])):
				success = False
			if not self._delete_prefix(self._url_to_key(pyramid['tiles_url']).rstrip('/') + '/'):
				success = False

		return success

	def _delete_prefix(self, prefix: str) -> bool:
		"""Delete every object under a key prefix (e.g. a DZI tiles directory)."""
		try:
			paginator = self.s3_client.get_paginator('list_objects_v2')
			keys = [{'Key': obj['Key']}
					for page in paginator.paginate(Bucket=self.bucket_name, Prefix=prefix)
					for obj in page.get('Contents', [])]
			for i in range(0, len(keys), 1000):
				self.s3_client.delete_objects(Bucket=self.bucket_name, Delete={'Objects': keys[i:i + 1000]})
			logger.info(f"Deleted {len(keys)} objects under prefix: {prefix}")
			return True
		except (ClientError, NoCredentialsError, Exception) as e:
			logger.error(f"Error deleting prefix {prefix}: {e}")
			return False

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

# Global CDN uploader instance (env-configured; used by the worker's write path)
cdn_uploader = CDNUploader(
	bucket_name=os.getenv("BUCKET_NAME"),
	cdn_base_url=os.getenv("CDN_BASE_URL"),
	endpoint_url=os.getenv("AWS_ENDPOINT_URL_S3"),
	access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
	secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
)
