
# Define target classes for full anonymization (people + vehicles)
TARGET_CLASSES = {
	0: "person",
	1: "bicycle",
	2: "car",
	3: "motorcycle",
	5: "bus",
	7: "truck"
}

# Minimum YOLO confidence for a detection to be kept (passed to predict()).
# Ultralytics' default is 0.25, which lets through tile-edge partials and
# zoomed-in false positives (spot-checked 2026-06-12: junk at 0.25-0.38,
# real hits at 0.70+). Detections' confidences are stored in the DB, so this
# can be re-tuned against real data.
MIN_CONFIDENCE = 0.4

BLUR_SIZES = {
	"person": 151,
	"bicycle": 123,
	"car": 101,
	"motorcycle": 91,
	"bus": 55,
	"truck": 55
}
