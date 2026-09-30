
# Define target classes for full anonymization (people + vehicles)
TARGET_CLASSES = {
	0: "person",
	1: "bicycle",
	2: "car",
	3: "motorcycle",
	5: "bus",
	7: "truck"
}

# Two decoupled thresholds (spot-checked 2026-06-12: tile-edge partials and
# zoomed-in false positives sit at 0.25-0.38, real hits at 0.70+):
#
#   DETECT_CONFIDENCE — floor passed to the model's predict(). Every detection
#     at or above this is RECORDED in detected_objects, so the debug overlay
#     can show near-misses and the blur threshold can be re-tuned downward from
#     stored data without reprocessing. Matches ultralytics' own default.
#   BLUR_CONFIDENCE — detections at or above this are actually blurred (and
#     blacked out in the LLM variant). Below it, they're recorded but left
#     visible — distinguishable in the overlay because blurred pixels are, well,
#     blurred.
DETECT_CONFIDENCE = 0.25

# BLUR_CONFIDENCE and should_blur live in common/detections.py, together with
# the four detected_objects formats they have to cope with: the API serves this
# column too and must reach the same verdict. Re-exported so the worker's own
# `from detections import ...` reads as before.
from common.detections import BLUR_CONFIDENCE, should_blur  # noqa: F401,E402


BLUR_SIZES = {
	"person": 151,
	"bicycle": 123,
	"car": 101,
	"motorcycle": 91,
	"bus": 55,
	"truck": 55
}
