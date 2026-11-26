"""
Anonymize a directory of photos the way the worker does, outside the worker.

	python anonymize_cli.py INPUT_DIR OUTPUT_DIR [--force_copy_all_images]

Each readable image in INPUT_DIR is run through anonymize_image (YOLO
detection + blur), and the result is written to OUTPUT_DIR as
<stem>.jpg beside a <stem>.detections.json holding the detection record
the worker would store. Images with nothing blurred are skipped unless
--force_copy_all_images, so OUTPUT_DIR holds exactly what changed.

anonymize_image used to take (input_dir, output_dir, filename, force) and
write the file itself; it now takes a source path, blurs in memory and
returns (image, detections), so the writing moved here.
"""
import json
import logging
import os

import cv2
import fire

from anonymize import anonymize_image


def process_directory(input_dir, output_dir, force_copy_all_images=False):
	os.makedirs(output_dir, exist_ok=True)
	logging.info("Starting anonymization...")

	# for filename in sorted(os.listdir(input_dir)):
	# 	anonymize_image(input_dir, output_dir, filename, force_copy_all_images)
	written = skipped = failed = 0
	for filename in sorted(os.listdir(input_dir)):
		source_path = os.path.join(input_dir, filename)
		if not os.path.isfile(source_path):
			continue
		try:
			image, detections = anonymize_image(source_path)
		except Exception as e:
			# Unsupported or unreadable file: say so and move on.
			logging.warning(f"Could not anonymize {filename}: {e}")
			failed += 1
			continue

		blurred = sum(1 for o in detections["objects"] if o.get("blurred"))
		if not blurred and not force_copy_all_images:
			skipped += 1
			continue

		stem = os.path.splitext(filename)[0]
		out_path = os.path.join(output_dir, stem + ".jpg")
		if not cv2.imwrite(out_path, image, [cv2.IMWRITE_JPEG_QUALITY, 95]):
			logging.warning(f"Could not write {out_path}")
			failed += 1
			continue
		with open(os.path.join(output_dir, stem + ".detections.json"), "w") as f:
			json.dump(detections, f, indent=2)
		logging.info(f"{filename}: blurred {blurred}/{len(detections['objects'])} -> {out_path}")
		written += 1

	logging.info(f"Anonymization complete: {written} written, {skipped} with nothing to blur, {failed} failed.")


if __name__ == "__main__":
	logging.basicConfig(level=logging.INFO)
	fire.Fire(process_directory)
