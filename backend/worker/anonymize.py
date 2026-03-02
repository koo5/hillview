#!/usr/bin/env python3

import os
import logging
import cv2
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

def _tile_starts(length, tile_size, step):
	"""Return tile start positions along one axis, always covering the full length."""
	if length <= tile_size:
		return [0]
	starts = list(range(0, length - tile_size, step))
	# ensure the trailing edge is always covered
	if not starts or starts[-1] + tile_size < length:
		starts.append(length - tile_size)
	return starts


def deduplicate_boxes(boxes, tolerance=10, subsumption_threshold=0.8):
	"""Remove near-duplicate and subsumed bounding boxes.

	Two boxes are considered near-duplicates if all four coordinates are within
	`tolerance` pixels of each other. A box is considered subsumed if more than
	`subsumption_threshold` of its own area is covered by a single larger box.

	Boxes are processed in descending area order so larger boxes take precedence.
	This produces a minimally-redundant set suitable for manual editing.

	Args:
		boxes: list of (cls_id, (x1, y1, x2, y2)).
		tolerance: pixel tolerance for near-duplicate coordinate comparison.
		subsumption_threshold: fraction of a box's area that must be covered by
			a larger box to discard it (0.8 = 80%).

	Returns:
		Deduplicated list in the same format.
	"""
	if not boxes:
		return boxes

	def _area(coords):
		x1, y1, x2, y2 = coords
		return max(0, x2 - x1) * max(0, y2 - y1)

	# Sort by area descending; attach area to avoid recomputing in the loop
	sorted_boxes = sorted(boxes, key=lambda b: _area(b[1]), reverse=True)

	kept = []
	for cls_id, (x1, y1, x2, y2) in sorted_boxes:
		curr_area = _area((x1, y1, x2, y2))
		redundant = False
		for _, (kx1, ky1, kx2, ky2) in kept:
			# near-duplicate: all coordinates within tolerance
			if (abs(x1 - kx1) <= tolerance and abs(y1 - ky1) <= tolerance and
					abs(x2 - kx2) <= tolerance and abs(y2 - ky2) <= tolerance):
				redundant = True
				break
			# subsumption: current box is mostly inside the kept box
			if curr_area > 0:
				ix1, iy1 = max(x1, kx1), max(y1, ky1)
				ix2, iy2 = min(x2, kx2), min(y2, ky2)
				inter_area = max(0, ix2 - ix1) * max(0, iy2 - iy1)
				if inter_area / curr_area >= subsumption_threshold:
					redundant = True
					break
		if not redundant:
			kept.append((cls_id, (x1, y1, x2, y2)))
	return kept


def run_yolo_multiscale(image, model_instance, max_tile_size=1280, min_scale_size=4096, overlap=0.2):
	"""Run YOLO inference over a multi-scale pyramid with tiling.

	Starts at full resolution and halves the scale each iteration until the
	image fits within a single tile (max_tile_size) or the scaled image's
	smaller dimension drops to or below min_scale_size (coarsest useful scale).
	At each scale the image is split into overlapping tiles of max_tile_size
	and the model is run on each tile. Detections from all tiles at all scales
	are collected and returned in original-image pixel coordinates.
	No NMS is applied — all bounding boxes are returned so callers can simply
	paint over every detected region.

	Args:
		image: BGR numpy array (original full-resolution image).
		model_instance: loaded Ultralytics YOLO model.
		max_tile_size: tile size in pixels (should match the model's native
			input resolution, e.g. 1280 for yolov5s6u).
		min_scale_size: stop halving once the shorter side of the scaled image
			falls to or below this value (prevents runaway tiling on very wide
			or very tall images where one dimension is already tiny).
		overlap: fractional overlap between adjacent tiles (0.2 = 20%).

	Returns:
		List of (cls_id, (x1, y1, x2, y2)) in original image coordinates.
	"""
	h, w = image.shape[:2]
	all_boxes = []
	step = max(1, int(max_tile_size * (1.0 - overlap)))

	scale = 1.0
	while True:
		sw = max(1, int(w * scale))
		sh = max(1, int(h * scale))
		inv_scale = 1.0 / scale

		scaled = cv2.resize(image, (sw, sh), interpolation=cv2.INTER_AREA) if scale < 1.0 else image

		for ty in _tile_starts(sh, max_tile_size, step):
			for tx in _tile_starts(sw, max_tile_size, step):
				tile = scaled[ty:min(ty + max_tile_size, sh), tx:min(tx + max_tile_size, sw)]
				results = model_instance(tile)[0]
				for box in results.boxes:
					cls_id = int(box.cls)
					if cls_id in TARGET_CLASSES:
						tx1, ty1, tx2, ty2 = map(int, box.xyxy[0])
						all_boxes.append((cls_id, (
							int((tx + tx1) * inv_scale),
							int((ty + ty1) * inv_scale),
							int((tx + tx2) * inv_scale),
							int((ty + ty2) * inv_scale),
						)))

		# stop once the whole image fits in a single tile (we've done a full pass)
		if sw <= max_tile_size and sh <= max_tile_size:
			break
		# stop once the shorter side reaches the coarsest useful scale
		if sw <= min_scale_size or sh <= min_scale_size:
			break

		scale *= 0.5

	return deduplicate_boxes(all_boxes)


def detect_targets(image, max_tile_size=1280, min_scale_size=4096, overlap=0.2):
	"""Detect target objects in the image using YOLO with multi-scale tiling."""
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

	return run_yolo_multiscale(image, model, max_tile_size=max_tile_size, min_scale_size=min_scale_size, overlap=overlap)



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




