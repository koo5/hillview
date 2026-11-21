"""Camera pitch and roll at the shutter: photos.pitch and photos.roll.

Derived by code from the capture app's stamp (the UserComment in exif_data),
the way photos.blurry is derived from image_metrics, and not by a generated
column: other sources (enrich's pose recovery, for one) are meant to write
better values later, and a rule change is a re-run of
backend/scripts/pose_backfill.py rather than a migration. The processed-photo
handler in photo_routes.py writes both on every processing.

The conventions are GPano's (Xmp.GPano.PosePitchDegrees / PoseRollDegrees,
which Panoramax reads), so bearing, pitch and roll are one standard triple:

- pitch: degrees above the horizon at the centre of the image, positive UP,
  in [-90, 90].
- roll: the roll of the published image, 0 when level. As it increases, the
  horizon rotates counterclockwise in the image. It is measured from the
  nearest quarter turn, so it lies in (-45, 45] and a level landscape shot
  reads 0: which quarter turn the photo was taken in is the image's own
  orientation, and the image already shows it.

The phone's stamp uses other signs, and both are negated here:
attitude.pitch_deg is positive LOOKING DOWN, and attitude.roll_deg is 0 with
the screen's top at the sky and positive when the phone is turned
counterclockwise as its user sees it. A deliberate 29-shot series (2026-11-15:
portrait and both landscapes, rolled 12-31°) confirmed the roll's sign and
size by eye. See docs/todo/photo-pose-and-level-gates.md.

The sources, first that applies:

- inertial.gravity, when it is three finite numbers of non-zero length:
  pitch_down = asin(g_z / |g|) and r = atan2(g_x, g_y), the formulas the app
  itself uses since capture_timing.metadata_version 3. Gravity never went
  through the remap that broke the older attitude angles, so it is good in
  every period.
- attitude.pitch_deg / roll_deg, when metadata_version is 1 or more.
- the same attitude angles on rows without metadata_version, only when
  device_rotation_deg is 0. Old portrait rows were right; landscape and
  upside-down ones were not.
- last, pitch only: the upload's own `pitch` field (exif_data's gps.pitch),
  negated, when the stamp has no attitude and no inertial object at all and the
  image is portrait-shaped (taller than wide). See below.
- otherwise nothing: the Tauri app and the web app stamp no attitude, nor does
  an external camera. A top-level {"pitch", "roll"} in the UserComment, from a
  client outside this tree, is deliberately not read: it holds the old
  landscape fault.

The upload's `pitch` field is the tilt that rode along with the bearing
(frontend2's BearingState.pitch): the same smoothed sensor reading as
attitude.pitch_deg, but taken when the bearing was last set, NULL whenever the
bearing source measures no tilt (car mode, a hand-set arrow), and positive
down. Nothing elects pitch today. It is only a fallback, because it is rough:
against gravity on photos that carry both, portrait values are off by 3.3° at
the median, 10° at the 90th percentile and 20° at the 99th, and landscape
values by up to 97° (that era's landscape fault), so landscape is not read.
Image shape tells landscape apart reliably; an upside-down portrait cannot be
told apart, but those are about 1 in 2,500. In the 2026-11 data the fallback
reaches only frontend2 photos from 2026-08-27 to 2026-09-24, captured before
the stamp carried attitude: every frontend2 capture since stamps both objects,
and no other client sends the field. An app that lets the user override pitch
should send a source marker with it, and this function should read that first
(see the plan's follow-ups, and "Pitch has three homes" in
docs/recon-capture-metadata.md).

Within about 15° of flat, which way gravity points in the image plane says
where the phone's top was turned, not how the horizon leans, and the app's own
roll falls back to the fused matrix there (GRAVITY_ROLL_FLOOR in
CameraPose.kt). So roll is None there and pitch is kept. Such a photo is more
than 75° from level and fails the Panoramax pitch gate anyway.
"""

import math
from typing import Any, Optional, Tuple

from common.user_comment import user_comment

# The share of gravity in the image plane below which roll is not a horizon
# tilt: sin(15°). Mirrors GRAVITY_ROLL_FLOOR in frontend2's CameraPose.kt.
ROLL_FLOOR = 0.26


def _number(value: Any) -> Optional[float]:
	"""A finite JSON number as a float; None for anything else, booleans included."""
	if isinstance(value, bool) or not isinstance(value, (int, float)):
		return None
	value = float(value)
	return value if math.isfinite(value) else None


def level_roll(roll_deg: float) -> float:
	"""GPano roll from the stamp's roll_deg: its residual from the nearest quarter turn, negated.

	The residual lies in [-45, 45), so the result lies in (-45, 45].
	"""
	residual = roll_deg - 90.0 * math.floor(roll_deg / 90.0 + 0.5)
	return -residual + 0.0   # + 0.0 turns -0.0 into 0.0


def _from_gravity(inertial: Any) -> Optional[Tuple[float, Optional[float]]]:
	gravity = inertial.get('gravity') if isinstance(inertial, dict) else None
	if not isinstance(gravity, list) or len(gravity) != 3:
		return None
	gx, gy, gz = (_number(v) for v in gravity)
	if gx is None or gy is None or gz is None:
		return None
	norm = math.sqrt(gx * gx + gy * gy + gz * gz)
	if norm == 0 or not math.isfinite(norm):
		return None
	pitch = -math.degrees(math.asin(max(-1.0, min(1.0, gz / norm)))) + 0.0
	if math.hypot(gx, gy) / norm < ROLL_FLOOR:
		return pitch, None
	return pitch, level_roll(math.degrees(math.atan2(gx, gy)))


def _from_attitude(attitude: Any, capture_timing: Any) -> Optional[Tuple[float, Optional[float]]]:
	if not isinstance(attitude, dict):
		return None
	version = _number(capture_timing.get('metadata_version')) if isinstance(capture_timing, dict) else None
	if version is None:
		if _number(attitude.get('device_rotation_deg')) != 0:
			return None
	elif version < 1:
		return None
	pitch_down = _number(attitude.get('pitch_deg'))
	if pitch_down is None or abs(pitch_down) > 90:
		return None
	pitch = -pitch_down + 0.0
	roll_deg = _number(attitude.get('roll_deg'))
	if roll_deg is None or math.cos(math.radians(pitch_down)) < ROLL_FLOOR:
		return pitch, None
	return pitch, level_roll(roll_deg)


def _from_upload_pitch(exif_data: Optional[dict], stamp: dict, width: Optional[int],
					   height: Optional[int]) -> Optional[Tuple[float, None]]:
	if 'attitude' in stamp or 'inertial' in stamp:
		return None   # a stamped photo whose stamp gave nothing: its pitch came the same broken way
	w, h = _number(width), _number(height)
	if w is None or h is None or not 0 < w < h:
		return None
	gps = exif_data.get('gps') if isinstance(exif_data, dict) else None
	pitch_down = _number(gps.get('pitch')) if isinstance(gps, dict) else None
	if pitch_down is None or abs(pitch_down) > 90:
		return None
	return -pitch_down + 0.0, None


def capture_pose(exif_data: Optional[dict], width: Optional[int] = None,
				 height: Optional[int] = None) -> Tuple[Optional[float], Optional[float]]:
	"""(pitch, roll) in GPano conventions for one photo; None where unmeasured.

	width and height are the stored image's, which only the last-resort source
	needs, to tell portrait from landscape.
	"""
	stamp = user_comment(exif_data)
	pose = (_from_gravity(stamp.get('inertial'))
			or _from_attitude(stamp.get('attitude'), stamp.get('capture_timing'))
			or _from_upload_pitch(exif_data, stamp, width, height))
	return pose if pose is not None else (None, None)
