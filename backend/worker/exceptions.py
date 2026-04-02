"""Lightweight exception classes for the worker service.

Kept in a separate module so app.py can import them without pulling in
heavy dependencies (cv2, pyvips, numpy, …) from photo_processor.
"""


class PhotoDeletedException(Exception):
    """Raised when a photo was deleted during processing."""
    pass
