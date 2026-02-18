import logging, os
import cv2
from detections import TARGET_CLASSES


def read_image(source_path):
	# Validate file size before processing to prevent memory exhaustion
	try:
		file_size = os.path.getsize(source_path)
		if file_size > 300 * 1024 * 1024:
			logging.warning(f"Image file too large for processing: {file_size} bytes")
			raise ValueError(f"Image file too large for processing: {file_size} bytes")
	except OSError:
		logging.warning(f"Could not access image file: {source_path}")
		raise ValueError("Invalid image file path")

	logging.info(f"Reading image: {source_path}")
	image = cv2.imread(source_path)
	if image is None:
		logging.warning(f"Could not read image: {source_path}")
		raise ValueError("Invalid image file content")

	# Validate image dimensions to prevent memory exhaustion
	height, width = image.shape[:2]
	if width > 65536 or height > 65536 or (width * height) > 65536*10000:
		raise ValueError(f"Image size too large or invalid ({width}x{height}). Please use a smaller image.")

	return image


def apply_blur(image, detections):
	"""Apply Gaussian blur to the regions defined by boxes."""

	#for cls_id, (x1, y1, x2, y2) in boxes:

	for det in detections:
		x1 = det['bbox']['x1']
		y1 = det['bbox']['y1']
		x2 = det['bbox']['x2']
		y2 = det['bbox']['y2']
		cls_id = det['class_id']
		blur = det['blur']

		x1, y1 = max(0, x1), max(0, y1)
		x2, y2 = min(x2, image.shape[1]), min(y2, image.shape[0])
		# if x2 - x1 % 2 == 0:
		# 	x2 -= 1
		# if y2 - y1 % 2 == 0:
		# 	y2 -= 1
		if blur % 2 == 0:
			blur += 1
			logging.debug(f"Adjusted blur kernel size to {blur} for object at ({x1},{y1})-({x2},{y2})")
		roi = image[y1:y2, x1:x2]
		if roi.size > 0:
			image[y1:y2, x1:x2] = cv2.GaussianBlur(roi, (blur, blur), 0)
			label = TARGET_CLASSES.get(cls_id, "unknown")
			logging.info(f"Blurred {label} at ({x1},{y1})-({x2},{y2})")

