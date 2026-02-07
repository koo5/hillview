"""
Logging context management for task/photo ID tracking.

This module provides context variables and logging filters to automatically
include task identifiers in all log messages during photo processing.
"""
import logging
from contextvars import ContextVar
from contextlib import contextmanager

# Context variables for task tracking
current_photo_id: ContextVar[str] = ContextVar('current_photo_id', default=None)
current_task_id: ContextVar[int] = ContextVar('current_task_id', default=None)


class TaskContextFilter(logging.Filter):
    """
    Logging filter that adds task context (photo_id, task_id) to log records.

    This filter runs for every log message and adds context attributes
    that can be used in the log format string.
    """

    def filter(self, record):
        # Add context to every log record
        photo_id = current_photo_id.get()
        task_id = current_task_id.get()

        # Build context prefix
        parts = []
        if task_id is not None:
            parts.append(f"task={task_id}")
        if photo_id is not None:
            # Truncate long photo IDs for readability
            short_id = photo_id[:8] if len(photo_id) > 8 else photo_id
            parts.append(f"photo={short_id}")

        record.task_context = f"[{' '.join(parts)}] " if parts else ""
        return True


@contextmanager
def task_context(photo_id: str = None, task_id: int = None):
    """
    Context manager to set the current photo/task ID for logging.

    Usage:
        with task_context(photo_id="abc123", task_id=5):
            logger.info("Processing...")  # Will include [task=5 photo=abc123]
    """
    old_photo_id = current_photo_id.get()
    old_task_id = current_task_id.get()

    if photo_id is not None:
        current_photo_id.set(photo_id)
    if task_id is not None:
        current_task_id.set(task_id)

    try:
        yield
    finally:
        # Restore previous context
        if photo_id is not None:
            if old_photo_id is not None:
                current_photo_id.set(old_photo_id)
            else:
                current_photo_id.set(None)
        if task_id is not None:
            if old_task_id is not None:
                current_task_id.set(old_task_id)
            else:
                current_task_id.set(None)


def setup_task_logging():
    """
    Configure the root logger to include task context in all log messages.

    Call this once at application startup.
    """
    # Create and add the filter to the root logger
    task_filter = TaskContextFilter()

    # Get the root logger
    root_logger = logging.getLogger()

    # Add filter to all handlers
    for handler in root_logger.handlers:
        handler.addFilter(task_filter)

    # Also add to root logger itself (catches loggers without handlers)
    root_logger.addFilter(task_filter)

    # Update format to include task context
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(task_context)s%(message)s'
    )

    for handler in root_logger.handlers:
        handler.setFormatter(formatter)

    return task_filter