"""Lightweight exception classes for the worker service.

Kept in a separate module so app.py can import them without pulling in
heavy dependencies (cv2, pyvips, numpy, …) from photo_processor.
"""


class PhotoDeletedException(Exception):
    """Raised when a photo was deleted during processing."""
    pass


class PoolMigrationError(Exception):
    """Raised when a photo's files land on different storage pools mid-upload
    (e.g. the API switched its write pool while DZI tiles were uploading),
    which would corrupt the derived DZI tile base URL. The whole upload fails
    so the client can retry cleanly."""
    pass
