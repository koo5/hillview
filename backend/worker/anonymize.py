#!/usr/bin/env python3

import os
import logging
import torch
from ultralytics import YOLO
from detections import TARGET_CLASSES
from blur import apply_blur, read_image

logging.basicConfig(
	level=logging.INFO,
	format='%(levelname)s - %(message)s'
)
console = logging.StreamHandler()
console.setLevel(logging.DEBUG)



# Load YOLO model
model = None
model_dir = "/app/worker/models"
model_name = "yolov5s6u.pt"
model_path = os.path.join(model_dir, model_name)

def detect_targets(image):
	"""Detect target objects in the image using YOLO."""
	global model

	if model is None:

		# Secure model loading with path validation
		#from common.security_utils import verify_model_file
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



def anonymize_image(source_path):
	"""
	Anonymize image by blurring detected objects and return detection results.
	"""

	image = read_image(source_path)

	logging.info(f"Image read, detecting target objects in image: {source_path}")
	boxes = detect_targets(image)

	logging.info(f"{source_path}: {len(boxes)} target objects detected.")

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
			'blur': max(abs(x2 - x1), abs(y2 - y1)),
			"bbox": {
				"x1": x1,
				"y1": y1,
				"x2": x2,
				"y2": y2
			}
		})

	logging.info(f"Applying blur to detected objects in image: {source_path}")
	apply_blur(source_path, image, detections["objects"])
	return image, detections




