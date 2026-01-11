#!/usr/bin/env python3

import os
import logging
import cv2
import torch
import subprocess
import shlex
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

BLUR_SIZES = {
	"person": 151,
	"bicycle": 123,
	"car": 101,
	"motorcycle": 91,
	"bus": 55,
	"truck": 55
}


# Load YOLO model
model = None
model_dir = "/app/worker/models"
model_name = "yolov5su.pt"
model_path = os.path.join(model_dir, model_name)

def detect_targets(image):
	"""Detect target objects in the image using YOLO."""
	global model

	if model is None:
		# Secure model loading with path validation
		from common.security_utils import verify_model_file

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


def apply_blur(image, detections):
	"""Apply Gaussian blur to the regions defined by boxes."""
	import cv2

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
		roi = image[y1:y2, x1:x2]
		if roi.size > 0:
			image[y1:y2, x1:x2] = cv2.GaussianBlur(roi, (blur, blur), 0)
			label = TARGET_CLASSES[cls_id]
			logging.info(f"Blurred {label} at ({x1},{y1})-({x2},{y2})")

	return image


def anonymize_image(source_path):
	"""
	Anonymize image by blurring detected objects and return detection results.
	"""

	# Validate file size before processing to prevent memory exhaustion
	try:
		file_size = os.path.getsize(source_path)
		if file_size > 50 * 1024 * 1024:  # 50MB limit
			logging.warning(f"Image file too large for processing: {file_size} bytes")
			raise ValueError(f"Image file too large for processing: {file_size} bytes")
	except OSError:
		logging.warning(f"Could not access image file: {source_path}")
		raise ValueError("Invalid image file path")

	image = cv2.imread(source_path)
	if image is None:
		logging.warning(f"Could not read image: {source_path}")
		raise ValueError("Invalid image file content")

	# Validate image dimensions to prevent memory exhaustion
	# height, width = image.shape[:2]
	# if width > 12192 or height > 12192 or (width * height) > 167108864:
	# 	raise ValueError(f"Image size too large or invalid ({width}x{height}). Please use a smaller image.")

	boxes = detect_targets(image)

	# Create detections data structure
	detections = {
		"objects": [],
		"model_name": model_name
	}

	for cls_id, (x1, y1, x2, y2) in boxes:
		label = TARGET_CLASSES[cls_id]

		detections["objects"].append({
			"class_id": cls_id,
			"class_name": label,
			'blur': BLUR_SIZES.get(label, 151),
			"bbox": {
				"x1": x1,
				"y1": y1,
				"x2": x2,
				"y2": y2
			}
		})

	if len(boxes) == 0:
		logging.info(f"{source_path}: No target objects detected. Skipping.")
		return source_path, detections
	masked = apply_blur(image.copy(), detections["objects"])

	output_path = source_path + '_anonymized'
	cv2.imwrite(output_path, masked)

	# Preserve EXIF data from original image
	try:
		# Copy EXIF data from source to output using exiftool
		cmd = ['exiftool', '-overwrite_original', '-TagsFromFile', source_path, '-all:all', output_path]
		logging.debug(f"Preserving EXIF data from {os.path.basename(source_path)} to anonymized version: {shlex.join(cmd)}")

		result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
		if result.returncode == 0:
			logging.info(f"Successfully preserved all EXIF metadata in anonymized image: {os.path.basename(output_path)}")

			# Reset orientation tag to 1 (normal orientation) - this is critical for privacy
			orientation_cmd = ['exiftool', '-overwrite_original', '-EXIF:Orientation=', output_path]
			logging.debug(f"Resetting orientation tag: {shlex.join(orientation_cmd)}")

			orientation_result = subprocess.run(orientation_cmd, capture_output=True, text=True, timeout=30)
			if orientation_result.returncode != 0:
				raise RuntimeError(f"Failed to reset orientation tag for {os.path.basename(output_path)}: {orientation_result.stderr}")

			logging.debug(f"Successfully reset orientation tag to 1 for {os.path.basename(output_path)}")
		else:
			logging.warning(f"Failed to preserve EXIF metadata in {os.path.basename(output_path)}: {result.stderr}")

	except subprocess.TimeoutExpired:
		logging.warning(f"Timeout while preserving EXIF data for {os.path.basename(output_path)}")
	except Exception as e:
		logging.warning(f"Error preserving EXIF data for {os.path.basename(output_path)}: {e}")

	logging.debug(f"Saved anonymized image with preserved metadata to: {output_path}")
	return output_path, detections


