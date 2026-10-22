"""Worker input policy, checked before invoking native image parsers.

Public workers accept JPEG input only. HILLVIEW_AUX enables other supported
formats for trusted internal workloads. These additional parsers and their
resource behavior may need further security audits before public exposure.
In particular, system OpenEXR retains outstanding advisories.
"""
import os
from pathlib import Path

HILLVIEW_AUX = os.environ.get('HILLVIEW_AUX', '').strip().lower() in ('1', 'true', 'yes')

# Decoder selection is explicit on public paths. Importing this policy must
# not change libvips operations globally or alter auxiliary decoder behavior.


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
	if not HILLVIEW_AUX and (
		format != 'jpeg' or suffix not in ('.jpg', '.jpeg')
	):
		raise ValueError('Only JPEG input is enabled; other supported formats require HILLVIEW_AUX=1')
	return format
