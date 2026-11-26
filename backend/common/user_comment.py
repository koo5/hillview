"""The capture app's provenance JSON, as stored in exif_data's UserComment.

Shared by the API, which serves typed projections of it (photo_routes.py), and
by common/capture_pose.py, which derives photos.pitch and photos.roll from it.
"""

import json
from typing import Optional


def user_comment(exif_data: Optional[dict]) -> dict:
	"""The capture app's provenance JSON (UserComment), or ``{}``.

	Written into ``exif_data['data']['UserComment']`` by two routes that agree on
	the shape: the Android EXIF writer embeds it in the file, and for everything
	that cannot write EXIF — browser uploads, the fast-write path — the worker
	synthesizes the same object from the upload metadata. Anything else that ends
	up in that tag is some other camera's free text, so a value that is not a JSON
	object is treated as absent rather than parsed hopefully.
	"""
	if not isinstance(exif_data, dict):
		return {}
	data = exif_data.get('data')
	uc = data.get('UserComment') if isinstance(data, dict) else None
	if not isinstance(uc, str) or not uc.startswith('{'):
		return {}
	try:
		parsed = json.loads(uc)
	except (json.JSONDecodeError, ValueError):
		return {}
	return parsed if isinstance(parsed, dict) else {}
