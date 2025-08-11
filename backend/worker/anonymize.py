#!/usr/bin/env python3

import fire
import os
import logging

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
        from ultralytics import YOLO
        model = YOLO("yolov5su.pt")

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

def process_directory(input_dir, output_dir, force_copy_all_images=False):
    os.makedirs(output_dir, exist_ok=True)
    logging.info("Starting anonymization...")

    for filename in sorted(os.listdir(input_dir)):
        anonymize_image(input_dir, output_dir, filename, force_copy_all_images)
    logging.info("Anonymization complete.")


def anonymize_image(input_dir, output_dir, filename, force_copy_all_images=False):
    if not filename.lower().endswith(('.jpg', '.jpeg', '.png')):
        return False

    import cv2

    input_path = os.path.join(input_dir, filename)
    image = cv2.imread(input_path)
    if image is None:
        logging.warning(f"Could not read image: {filename}")
        return False

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


if __name__ == "__main__":
    fire.Fire(process_directory)

