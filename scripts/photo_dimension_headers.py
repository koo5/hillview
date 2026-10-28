"""Bounded image-header reads for dimension evidence; no pixel decoding."""
from datetime import datetime, timezone
from io import BytesIO
import struct
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


def image_dimensions(data):
	if data[:4] == b'RIFF' and data[8:12] == b'WEBP':
		offset = 12
		while offset + 8 <= len(data):
			tag = data[offset:offset + 4]
			size = int.from_bytes(data[offset + 4:offset + 8], 'little')
			payload = data[offset + 8:]
			if tag == b'VP8X' and len(payload) >= 10:
				return (int.from_bytes(payload[4:7], 'little') + 1,
				        int.from_bytes(payload[7:10], 'little') + 1)
			if tag == b'VP8 ' and len(payload) >= 10 and payload[3:6] == b'\x9d\x01\x2a':
				width, height = struct.unpack('<HH', payload[6:10])
				return width & 0x3fff, height & 0x3fff
			if tag == b'VP8L' and len(payload) >= 5 and payload[0] == 0x2f:
				bits = int.from_bytes(payload[1:5], 'little')
				return (bits & 0x3fff) + 1, ((bits >> 14) & 0x3fff) + 1
			offset += 8 + size + (size & 1)
		raise ValueError('WebP dimensions not found in the bounded prefix')
	# Optional dependency needed only for JPEG/PNG, not WebP or cached checks.
	from PIL import Image

	with Image.open(BytesIO(data), formats=['JPEG', 'PNG']) as image:
		return image.size


def check_image(job):
	result = {k: job[k] for k in ('id', 'field', 'expected_dimensions')}
	result['checked_at'] = datetime.now(timezone.utc).isoformat()
	try:
		url = job.get('url')
		if not isinstance(url, str) or urlsplit(url).scheme not in ('http', 'https'):
			raise ValueError('Missing HTTP(S) image URL')
		request = Request(url, headers={'Range': 'bytes=0-65535', 'Accept-Encoding': 'identity',
		                               'User-Agent': 'Hillview-size-proposal/1'})
		with urlopen(request, timeout=12) as response:
			data = response.read(65536)
			result['http_status'] = response.status
		result.update(actual_dimensions=list(image_dimensions(data)), bytes_read=len(data))
	except Exception as exc:
		result['error'] = f'{type(exc).__name__}: {str(exc).split(" for url:")[0]}'
	return result
