import logging
import os
from typing import Dict, Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from common.database import get_db
from debug_utils import debug_only, clear_system_tables, cleanup_upload_directories

log = logging.getLogger(__name__)

USER_ACCOUNTS = os.getenv("USER_ACCOUNTS", "false").lower() in ("true", "1", "yes")

router = APIRouter(prefix="/api/debug", tags=["debug"])


@router.get("")
async def debug_endpoint():
	"""Debug endpoint to check if the API is working properly"""
	return {"status": "ok", "message": "API is working properly"}


@router.post("/recreate-test-users")
@debug_only
async def recreate_test_users():
	if not USER_ACCOUNTS:
		return {"error": "User accounts are not enabled"}

	import auth
	result = await auth.recreate_test_users()
	return {"status": "success", "message": "Test users re-created", "details": result}


@router.post("/clear-database")
@debug_only
async def clear_database():
	from sqlalchemy import select, text
	import auth
	from common.database import get_db
	from common.models import User

	# Get database session
	async for db in get_db():
		# Get all usernames
		usernames_query = select(User.username)
		usernames_result = await db.execute(usernames_query)
		all_usernames = [row[0] for row in usernames_result.fetchall()]

		# Use the existing safe deletion function to delete all users and their photos
		delete_summary = await auth.delete_users_by_usernames(db, all_usernames)

		# Clear any remaining orphaned photos (photos without owners)
		from common.models import Photo
		from photos import delete_all_user_photo_files

		# Get any remaining photos in the database
		remaining_photos_query = select(Photo)
		remaining_photos_result = await db.execute(remaining_photos_query)
		remaining_photos = remaining_photos_result.scalars().all()

		orphaned_photos_deleted = 0
		if remaining_photos:
			# Delete the physical files for orphaned photos
			deleted_files_count = await delete_all_user_photo_files(remaining_photos)
			log.info(f"Deleted {deleted_files_count}/{len(remaining_photos)} orphaned photo files")

			# Delete orphaned photos from database
			orphaned_delete_stmt = text("DELETE FROM photos")
			orphaned_result = await db.execute(orphaned_delete_stmt)
			orphaned_photos_deleted = orphaned_result.rowcount
			log.info(f"Deleted {orphaned_photos_deleted} orphaned photos from database")

		# Clear Mapillary cache tables (no foreign key dependencies from other tables)
		from mapillary_routes import clear_mapillary_cache_tables
		mapillary_deletion_counts = await clear_mapillary_cache_tables(db)

		# Clear other tables that might not be covered by user deletion
		system_deletion_counts = await clear_system_tables(db)

		# Final cleanup: remove any remaining files in upload directories
		# This ensures we clean up files even if database records are inconsistent
		upload_dirs_cleaned = await cleanup_upload_directories()

		await db.commit()
		break

	log.info("Database cleared completely")
	return {
		"status": "success",
		"message": "Database cleared successfully",
		"details": {
			"users_deleted": delete_summary["users_deleted"],
			"photos_deleted": delete_summary["photos_deleted"],
			"orphaned_photos_deleted": orphaned_photos_deleted,
			"mapillary_cache_deleted": mapillary_deletion_counts["mapillary_cache_deleted"],
			"cached_regions_deleted": mapillary_deletion_counts["cached_regions_deleted"],
			**system_deletion_counts,
			**upload_dirs_cleaned
		}
	}


@router.post("/mock-mapillary")
@debug_only
async def set_mock_mapillary_data(mock_data: Dict[str, Any], db: AsyncSession = Depends(get_db)):
	from mock_mapillary import mock_mapillary_service, generate_mock_images
	mock_data = generate_mock_images(mock_data)
	mock_mapillary_service.set_mock_data(mock_data)

	# Get cache info to warn about potential confusion
	from sqlalchemy import text
	try:
		cache_photos_result = await db.execute(text("SELECT COUNT(*) as count FROM mapillary_cache"))
		cache_photos_count = cache_photos_result.scalar()

		cache_areas_result = await db.execute(text("SELECT COUNT(*) as count FROM mapillary_cached_areas"))
		cache_areas_count = cache_areas_result.scalar()
	except Exception as e:
		# Tables might not exist yet - that's fine, means no cached data
		log.debug(f"Cache tables don't exist yet (normal for fresh database): {e}")
		cache_photos_count = 0
		cache_areas_count = 0

	return {
		"status": "success",
		"message": "Mock Mapillary data set",
		"details": {
			"photos_count": len(mock_data.get('data', [])),
			"cache_info": {
				"cached_photos": cache_photos_count,
				"cached_areas": cache_areas_count,
				"warning": "If cache_photos > 0, cached data may override mock data. Use clear-database first for pure mock testing." if cache_photos_count > 0 else None
			}
		}
	}


@router.delete("/mock-mapillary")
@debug_only
async def clear_mock_mapillary_data():
	from mock_mapillary import mock_mapillary_service, cleanup_mock_images
	mock_mapillary_service.clear_mock_data()
	cleanup_mock_images()

	return {
		"status": "success",
		"message": "Mock Mapillary data cleared"
	}


@router.post("/set-featured")
@debug_only
async def set_featured(photo_id: str, featured: bool):
	"""Set or unset the featured flag on a photo"""
	from common.database import get_db
	from common.models import Photo
	from sqlalchemy import select

	async for db in get_db():
		result = await db.execute(select(Photo).where(Photo.id == photo_id))
		photo = result.scalar_one_or_none()
		if not photo:
			raise HTTPException(status_code=404, detail="Photo not found")
		photo.featured = featured
		await db.commit()
		return {"status": "ok", "photo_id": photo_id, "featured": featured}
