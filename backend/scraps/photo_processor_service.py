#!/usr/bin/env python3
"""
Independent photo processing service
Scans database for unprocessed photos and processes them
"""
import os
import sys
import time
import logging
import asyncio
import uuid
from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

# Add common directory to path
sys.path.append('/app/common')

from common.database import SessionLocal
from common.models import Photo

# Import processing functions from photo_processor.py
from photo_processor import photo_processor

# Setup logging
logging.basicConfig(
	level=logging.INFO,
	format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


upload_dir = "/app/uploads"
scan_interval = int(os.getenv("SCAN_INTERVAL_SECONDS", "2"))


class PhotoProcessorService:
	"""Independent photo processing service."""

	async def process_photo(self, db: AsyncSession, photo: Photo):
		"""Process a single photo."""
		try:
			logger.info(f"Processing photo {photo.id}: {photo.filename}")

			# Update status to processing
			photo.processing_status = "processing"
			await db.commit()

			result = None
			try:
				result = await photo_processor.process_uploaded_photo(
				file_path, filename, user_id, description, is_public
			)
				if result.error:
					photo.processing_status = "error"
					photo.error = result.error
					await db.commit()
					return

			except Exception as e:
				logger.error(e)
				return

			# Update photo with processed data
			photo.latitude = gps_data.get('latitude')
			photo.longitude = gps_data.get('longitude')
			photo.compass_angle = gps_data.get('bearing')
			photo.altitude = gps_data.get('altitude')
			photo.width = width
			photo.height = height
			photo.sizes = sizes_info
			photo.processing_status = "completed"
			photo.error = None  # Clear any previous error
			await db.commit()
			logger.info(f"Successfully processed photo {photo.id}")

		except Exception as e:
			error_msg = "Photo processing failed. The image may be corrupted or in an unsupported format."
			logger.error(f"Error processing photo {photo.id}: {str(e)}")
			photo.processing_status = "error"
			photo.error = error_msg
			await db.commit()



	async def scan_and_process(self):
		"""Scan for unprocessed photos and process them."""
		try:
			async with SessionLocal() as db:
				stmt = select(Photo).where(Photo.processing_status == "pending")
				result = await db.execute(stmt)
				pending_photos = result.scalars().all()

				if len(pending_photos) > 0:
					logger.info(f"Found {len(pending_photos)} photos to process")

				for photo in pending_photos:
					await self.process_photo(db, photo)

		except Exception as e:
			logger.error(f"Error during scan and process: {str(e)}")



	async def run_forever(self):
		"""Main service loop."""
		logger.info(f"Starting photo processor service (scan interval: {self.scan_interval}s)")

		while True:
			try:
				await self.scan_and_process()
				#logger.debug(f"Scan completed, sleeping for {self.scan_interval} seconds")
				await asyncio.sleep(self.scan_interval)

			except KeyboardInterrupt:
				logger.info("Received shutdown signal, stopping service")
				break
			except Exception as e:
				logger.error(f"Unexpected error in main loop: {str(e)}")
				await asyncio.sleep(self.scan_interval)

if __name__ == "__main__":
	service = PhotoProcessorService()
	asyncio.run(service.run_forever())
