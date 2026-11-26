"""Worker input policy, checked before invoking native image parsers.

Public workers accept JPEG input only. HILLVIEW_AUX enables other supported
formats for trusted internal workloads, by default only for files named by
local_photo_path (require_supported_source). These additional parsers and their
resource behavior may need further security audits before public exposure.
In particular, system OpenEXR retains outstanding advisories.
"""
import os
from pathlib import Path

HILLVIEW_AUX = os.environ.get('HILLVIEW_AUX', '').strip().lower() in ('1', 'true', 'yes')

# Even with HILLVIEW_AUX on, a non-JPEG file in an upload BODY is refused by
# default: those bytes come from whoever holds an upload token, and tokens are
# not bound to a worker, so any signed-in account can reach an aux worker. A
# file named by local_photo_path is already on this box, under a read-only
# LOCAL_PHOTO_ROOTS mount (local_photos), so only someone who can write those
# host trees can feed it to the auxiliary parsers. That trust comes from the
# filesystem, not from the client's address or a proxy header. Set
# ALLOW_AUX_FORMATS_IN_UPLOADS=1 to accept non-JPEG bodies again.
ALLOW_AUX_FORMATS_IN_UPLOADS = os.environ.get('ALLOW_AUX_FORMATS_IN_UPLOADS', '').strip().lower() in ('1', 'true', 'yes')

# Decoder selection is explicit on public paths. Importing this policy must
# not change libvips operations globally or alter auxiliary decoder behavior.


def _is_public_jpeg(format, suffix):
	"""The public worker's whole input policy: JPEG content under a JPEG name."""
	return format == 'jpeg' and suffix in ('.jpg', '.jpeg')


def require_supported_image(path):
	"""Return the content format or reject before a decoder sees the file.

	Check both suffix and magic so renaming an internal format cannot bypass
	the policy. CR2 shares TIFF magic; its suffix also selects dcraw elsewhere.
	"""
	suffix = Path(path).suffix.lower()
	with open(path, 'rb') as source:
		header = source.read(16)
	if suffix == '.bmp' or header.startswith(b'BM'):
		raise ValueError('BMP images are not supported')
	if header.startswith(b'\x76\x2f\x31\x01'):
		format = 'exr'
	elif header.startswith((b'II*\x00', b'MM\x00*', b'II+\x00', b'MM\x00+')):
		format = 'tiff'
	elif header.startswith(b'\xff\xd8\xff'):
		format = 'jpeg'
	elif header.startswith(b'\x89PNG\r\n\x1a\n'):
		format = 'png'
	elif header.startswith((b'GIF87a', b'GIF89a')):
		format = 'gif'
	elif header.startswith(b'RIFF') and header[8:12] == b'WEBP':
		format = 'webp'
	else:
		raise ValueError('Unsupported image file content')
	if not HILLVIEW_AUX and not _is_public_jpeg(format, suffix):
		raise ValueError('Only JPEG input is enabled; other supported formats require HILLVIEW_AUX=1')
	return format


def require_supported_source(path, *, local_source):
	"""The job entry gate: require_supported_image, plus where the bytes came from.

	local_source is True only when the file was named by local_photo_path (see
	the ALLOW_AUX_FORMATS_IN_UPLOADS note above). An upload body must pass the
	public policy, JPEG content AND a JPEG suffix, so on an aux worker a renamed
	CR2/TIFF cannot reach dcraw or another suffix-selected reader either. The
	later require_supported_image calls only apply the process-wide policy, so
	this gate has to run before any of them.
	"""
	format = require_supported_image(path)
	if not local_source and not ALLOW_AUX_FORMATS_IN_UPLOADS and not _is_public_jpeg(format, Path(path).suffix.lower()):
		raise ValueError(
			'Only JPEG is accepted in an upload body; other formats must be named '
			'by local_photo_path (a file under LOCAL_PHOTO_ROOTS), or set '
			'ALLOW_AUX_FORMATS_IN_UPLOADS=1')
	return format
