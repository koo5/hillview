import logging
import os
from typing import Dict, Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

import push_toggle
from auth import get_current_user_optional_with_query
from common.database import get_db
from debug_utils import debug_only, clear_system_tables, cleanup_upload_directories

log = logging.getLogger(__name__)

USER_ACCOUNTS = os.getenv("USER_ACCOUNTS", "false").lower() in ("true", "1", "yes")

router = APIRouter(prefix="/api/debug", tags=["debug"])


@router.get("")
async def debug_endpoint():
	"""Debug endpoint to check if the API is working properly"""
	return {"status": "ok", "message": "API is working properly"}


@router.get("/whoami-query")
@debug_only
async def whoami_query(current_user=Depends(get_current_user_optional_with_query)):
	"""Reflect who the optional-auth resolver (header / signed stream credential /
	legacy query token) identified. Test surface for stream-credential auth — the
	SSE endpoints that use this dependency are awkward to assert against directly."""
	if current_user is None:
		return {"authenticated": False}
	return {
		"authenticated": True,
		"user_id": current_user.id,
		"username": current_user.username,
	}


@router.post("/recreate-test-users")
@debug_only
async def recreate_test_users():
	if not USER_ACCOUNTS:
		return {"error": "User accounts are not enabled"}

	import auth
	result = await auth.recreate_test_users()

	# A test that opted in to real outgoing push shouldn't leak that
	# choice into the next test run. Reset to the DEV_MODE-driven default
	# (off in dev, on in prod) every time test state gets wiped.
	push_toggle.reset_to_default()
	# Same rationale for the in-memory auth debug overrides (short access-TTL /
	# force-logout): drop them so a crashed spec can't leak state into the next.
	auth.reset_debug_overrides()

	return {"status": "success", "message": "Test users re-created", "details": result}


@router.post("/clear-database")
@debug_only
async def clear_database():
	from sqlalchemy import select, text
	import auth
	from common.database import SessionLocal, engine
	from common.models import User, Photo
	from mapillary_routes import clear_mapillary_cache_tables
	from photos import delete_photo_files_for_sizes

	# Serialize concurrent clear-database calls with an EXPLICIT session-level advisory
	# lock. The old serialization was accidental — the sync file sweep blocked the event
	# loop — and it is gone now that file I/O is threaded; a lock makes the "one wipe at
	# a time" guarantee real (the dev Postgres is shared across worktrees). Held on a
	# dedicated session and committed right after acquisition so it lives at SESSION
	# scope (an xact-scoped lock would drop at the first commit below) and the lock
	# session itself never sits idle-in-transaction under the guardrail. Blocking on
	# purpose: a second caller waits rather than racing.
	CLEAR_DB_LOCK_KEY = 91001
	# A session-level advisory lock must live on ONE pinned connection: it is tied to the
	# backend connection, not the transaction, and SQLAlchemy hands a Session's connection
	# back to the pool on commit — so acquiring on a Session and unlocking later would run
	# the unlock on a different pooled connection and leak the lock. engine.connect() pins
	# one connection until close(). Commit right after acquiring so the lock's own
	# connection is not left idle-in-transaction; the session-level lock persists across
	# that commit. Returning the connection to the pool does NOT release the lock, so the
	# explicit unlock in `finally` is mandatory.
	async with engine.connect() as lock_conn:
		await lock_conn.execute(text("SELECT pg_advisory_lock(:k)"), {"k": CLEAR_DB_LOCK_KEY})
		await lock_conn.commit()
		try:
				# Delete every user and their photos. delete_users_by_usernames sweeps files
			# off the event loop and outside its write transaction.
			async with SessionLocal() as db:
				all_usernames = list((await db.execute(select(User.username))).scalars().all())
				delete_summary = await auth.delete_users_by_usernames(db, all_usernames)

			# Orphaned photos (no owner): capture sizes, end the read txn, sweep, then delete.
			async with SessionLocal() as db:
				orphan_sizes = [p.sizes for p in (await db.execute(select(Photo))).scalars().all()]
				await db.rollback()
			orphaned_photos_deleted = 0
			if orphan_sizes:
				await delete_photo_files_for_sizes(orphan_sizes)
				async with SessionLocal() as db:
					orphaned_result = await db.execute(text("DELETE FROM photos"))
					await db.commit()
					orphaned_photos_deleted = orphaned_result.rowcount
				log.info(f"Deleted {orphaned_photos_deleted} orphaned photos from database")

			# Cache + system tables (each commits internally).
			async with SessionLocal() as db:
				mapillary_deletion_counts = await clear_mapillary_cache_tables(db)
			async with SessionLocal() as db:
				system_deletion_counts = await clear_system_tables(db)

			# Wholesale filesystem sweep, last of all and outside any transaction.
			upload_dirs_cleaned = await cleanup_upload_directories()
		finally:
			await lock_conn.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": CLEAR_DB_LOCK_KEY})
			await lock_conn.commit()

	# Same reset rule as recreate-test-users — any test-only opt-in to
	# real push gets cleared when test state is wiped.
	push_toggle.reset_to_default()
	# Likewise drop the in-memory auth debug overrides (access-TTL / force-logout).
	auth.reset_debug_overrides()

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
	from common.database import SessionLocal
	from common.models import Photo
	from sqlalchemy import select

	async with SessionLocal() as db:
		result = await db.execute(select(Photo).where(Photo.id == photo_id))
		photo = result.scalar_one_or_none()
		if not photo:
			raise HTTPException(status_code=404, detail="Photo not found")
		photo.featured = featured
		await db.commit()
		return {"status": "ok", "photo_id": photo_id, "featured": featured}
