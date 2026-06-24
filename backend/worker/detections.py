
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
BLUR_CONFIDENCE = 0.4


# detected_objects schema — FOUR variants coexist in the DB, in order of recency:
#   1.  Oldest model detections: {class_id, class_name, blur, bbox} — NO confidence,
#       scale, or blurred flag. should_blur() sees no confidence and treats them as
#       always-blurred, matching how they were processed at the time.
#   1b. Model detections WITH "confidence" + "scale" but still NO "blurred" flag (the
#       intermediate format). should_blur() correctly re-derives the decision from the
#       stored confidence (>= BLUR_CONFIDENCE). - the threshold may have moved a fer
#       times before settling on 0.4.
#   2.  Current model detections (anonymize.py): 1b + an explicit "blurred" bool
#       (= should_blur at write time), so consumers needn't re-derive anything.
#   3.  Manual overrides (photo_processor.py, container also carries "manual": True):
#       rects with class_id=None, no confidence, blur=500, "blurred": True — always
#       blurred.
# Consumer convention: `obj.get("blurred", should_blur(obj))` — uses the persisted flag
# for #2/#3 and falls back to should_blur() for #1 (always-blur) and #1b (from conf).
def should_blur(obj) -> bool:
	"""Whether a recorded detection should actually be blurred/blacked out.

	Manual override rectangles carry no confidence and are always blurred;
	model detections are blurred at or above BLUR_CONFIDENCE. Prefer the persisted
	`blurred` flag where present (formats #2/#3 above); this re-derives it for the
	legacy format #1 that predates the flag.
	"""
	conf = obj.get("confidence")
	return conf is None or conf >= BLUR_CONFIDENCE


BLUR_SIZES = {
	"person": 151,
	"bicycle": 123,
	"car": 101,
	"motorcycle": 91,
	"bus": 55,
	"truck": 55
}
