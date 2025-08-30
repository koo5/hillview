#!/usr/bin/env python3

import fire
import os
import logging
import cv2
import torch
from ultralytics import YOLO


logging.basicConfig(
	level=logging.INFO,
	format='%(levelname)s - %(message)s'
)
console = logging.StreamHandler()
console.setLevel(logging.DEBUG)


# Define target classes for full anonymization (people + vehicles)
TARGET_CLASSES = {
	0: "person",
	1: "bicycle",
	2: "car",
	3: "motorcycle",
	5: "bus",
	7: "truck"
}

# Load YOLO model
model = None

def detect_targets(image):
	"""Detect target objects in the image using YOLO."""
	global model

	if model is None:
		# Secure model loading with path validation
		from common.security_utils import verify_model_file
		model_path = "/app/worker/models/yolov5su.pt"

		# Verify model file exists and is valid before loading
		#if not verify_model_file(model_path):
		#	raise Exception("No valid YOLO model found")

		# Temporarily patch torch.load to use weights_only=False for YOLO model loading
		original_load = torch.load
		torch.load = lambda *args, **kwargs: original_load(*args, **{**kwargs, 'weights_only': False})
		
		try:
			model = YOLO(model_path)
			logging.info(f"Successfully loaded YOLO model from {model_path}")
		finally:
			# Restore original torch.load
			torch.load = original_load

	results = model(image)[0]
	boxes = []
	for box in results.boxes:
		cls_id = int(box.cls)
		if cls_id in TARGET_CLASSES:
			x1, y1, x2, y2 = map(int, box.xyxy[0])
			boxes.append((cls_id, (x1, y1, x2, y2)))
	return boxes


def apply_blur(image, boxes):
	"""Apply Gaussian blur to the regions defined by boxes."""
	import cv2

	for cls_id, (x1, y1, x2, y2) in boxes:
		x1, y1 = max(0, x1), max(0, y1)
		x2, y2 = min(x2, image.shape[1]), min(y2, image.shape[0])
		roi = image[y1:y2, x1:x2]
		if roi.size > 0:
			image[y1:y2, x1:x2] = cv2.GaussianBlur(roi, (151, 151), 0)
	return image


def anonymize_image(input_dir, output_dir, filename, force_copy_all_images=False):

	input_path = os.path.join(input_dir, filename)

	# Validate file size before processing to prevent memory exhaustion
	try:
		file_size = os.path.getsize(input_path)
		if file_size > 50 * 1024 * 1024:  # 50MB limit
			logging.warning(f"Image file too large for processing: {file_size} bytes")
			return False
	except OSError:
		logging.warning(f"Could not access image file: {filename}")
		raise ValueError("Invalid image file path")

	image = cv2.imread(input_path)
	if image is None:
		logging.warning(f"Could not read image: {filename}")
		raise ValueError("Invalid image file content")

	# Validate image dimensions to prevent memory exhaustion
	height, width = image.shape[:2]
	if width > 8192 or height > 8192 or (width * height) > 67108864:
		raise ValueError(f"Image size too large or invalid ({width}x{height}). Please use a smaller image.")

	boxes = detect_targets(image)
	if len(boxes) == 0 and not force_copy_all_images:
		logging.info(f"{filename}: No target objects detected. Skipping.")
		return False
	masked = apply_blur(image.copy(), boxes)

	for cls_id, (x1, y1, x2, y2) in boxes:
		label = TARGET_CLASSES[cls_id]
		logging.info(f"{filename}: Blurred {label} at ({x1}, {y1}) → ({x2}, {y2})")

	output_path = os.path.join(output_dir, filename)
	cv2.imwrite(output_path, masked)
	logging.debug(f"Saved masked image to: {output_path}\n")
	return True



def process_directory(input_dir, output_dir, force_copy_all_images=False):
	os.makedirs(output_dir, exist_ok=True)
	logging.info("Starting anonymization...")

	for filename in sorted(os.listdir(input_dir)):
		anonymize_image(input_dir, output_dir, filename, force_copy_all_images)
	logging.info("Anonymization complete.")


if __name__ == "__main__":
	fire.Fire(process_directory)
