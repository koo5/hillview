"""Utilities for debug endpoints and common operations."""

import os
import shutil
import logging
from functools import wraps
from fastapi import HTTPException
from typing import Any, Callable, Dict
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from pathlib import Path


def debug_only(func: Callable) -> Callable:
    """Decorator to restrict endpoints to debug mode only.

    Checks DEBUG_ENDPOINTS environment variable and raises 404 if not enabled.
    This centralizes the debug endpoint security check.
    """
    @wraps(func)
    async def wrapper(*args, **kwargs) -> Any:
        if not os.getenv("DEBUG_ENDPOINTS", "false").lower() in ("true", "1", "yes"):
            raise HTTPException(status_code=404, detail="Debug endpoints disabled")
        return await func(*args, **kwargs)
    return wrapper


def safe_str_id(obj: Any) -> str:
    """Safely convert UUID/ID to string for logging and queries.

    Args:
        obj: Object with .id attribute or string/UUID directly

    Returns:
        String representation of the ID
    """
    if hasattr(obj, 'id'):
        return str(obj.id)
    return str(obj)


async def clear_system_tables(db: AsyncSession) -> Dict[str, int]:
    """Clear system/audit tables that don't have foreign key dependencies.

    Args:
        db: Database session

    Returns:
        Dict with deletion counts for each table
    """
    # Clear system tables that don't have foreign key dependencies
    token_blacklist_result = await db.execute(text("DELETE FROM token_blacklist"))
    audit_log_result = await db.execute(text("DELETE FROM security_audit_log"))
    hidden_photos_result = await db.execute(text("DELETE FROM hidden_photos"))
    hidden_users_result = await db.execute(text("DELETE FROM hidden_users"))

    await db.commit()

    return {
        "token_blacklist_deleted": token_blacklist_result.rowcount,
        "audit_log_deleted": audit_log_result.rowcount,
        "hidden_photos_deleted": hidden_photos_result.rowcount,
        "hidden_users_deleted": hidden_users_result.rowcount
    }


async def cleanup_upload_directories() -> Dict[str, int]:
    """Clean up all files in upload directories.

    This function removes all user-uploaded files and directories, including:
    - Original uploads in uploads/
    - Optimized sizes in uploads/opt/
    - Processed photos in pics/ (PICS_DIR)
    - Any temporary files

    Returns:
        Dict with cleanup statistics
    """
    logger = logging.getLogger(__name__)

    # Get directories from environment or use defaults
    upload_dir = Path(os.getenv("UPLOAD_DIR", "./uploads"))
    pics_dir = Path(os.getenv("PICS_DIR", "./pics"))

    total_files_deleted = 0
    total_directories_deleted = 0

    # Clean upload directory
    try:
        if upload_dir.exists():
            # Count files and directories before deletion
            for root, dirs, files in os.walk(upload_dir):
                total_files_deleted += len(files)
                total_directories_deleted += len(dirs)

            # Remove the entire uploads directory tree
            shutil.rmtree(upload_dir)
            logger.info(f"Removed upload directory: {upload_dir}")

            # Recreate the base upload directory for future uploads
            upload_dir.mkdir(parents=True, exist_ok=True)
            logger.info(f"Recreated empty upload directory: {upload_dir}")

        else:
            logger.info(f"Upload directory {upload_dir} does not exist, nothing to clean")

    except Exception as e:
        logger.error(f"Error cleaning upload directory: {str(e)}")
        # Don't raise exception, just log it as this is cleanup

    # Clean pics directory contents (but keep the directory itself)
    try:
        if pics_dir.exists():
            # Count and remove all contents of pics directory
            for root, dirs, files in os.walk(pics_dir):
                total_files_deleted += len(files)
                total_directories_deleted += len(dirs)

            # Remove only the contents, not the pics directory itself
            for item in pics_dir.iterdir():
                if item.is_dir():
                    shutil.rmtree(item)
                else:
                    item.unlink()

            logger.info(f"Cleaned contents of pics directory: {pics_dir}")

        else:
            logger.info(f"Pics directory {pics_dir} does not exist, nothing to clean")

    except Exception as e:
        logger.error(f"Error cleaning pics directory: {str(e)}")
        # Don't raise exception, just log it as this is cleanup

    return {
        "upload_files_deleted": total_files_deleted,
        "upload_directories_deleted": total_directories_deleted,
        "upload_directory_recreated": True,
        "pics_directory_cleaned": True
    }