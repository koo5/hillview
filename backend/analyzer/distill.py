"""
Distillation library for merging multiple analysis sessions into a single result.
"""

import fcntl
import hashlib
import json
import os
import re
import sys
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

# Independent of the model selected for acquisition. Adding a model here makes
# its already-recorded answers eligible; no history needs rewriting.
TRUSTED_MODELS = tuple(model.strip() for model in os.environ.get(
	"ANALYZER_TRUSTED_MODELS",
	"nvidia/nemotron-nano-12b-v2-vl:free,qwen/qwen3-vl-30b-a3b-thinking,haiku,claude-haiku-4-5-20251001,claude-haiku-5-5,dots-studio/dots-3-note-preview:free",
).split(",") if model.strip())

def lock_path_for(json_path: Path) -> Path:
	"""The lock file guarding a sessions JSON file."""
	return json_path.parent / f"{json_path.name}.lock"


def acquire_file_lock(lock_path: Path, blocking: bool = True):
	"""
	Take the cross-process flock on lock_path.

	Returns the open lock file (pass it to release_file_lock). With
	blocking=False returns None immediately if another process holds it.

	The kernel drops an flock when its holder dies, which is what lets the
	analyzer use "is the file locked" as "is someone still working on this
	photo" — on a local filesystem only; do not rely on flock over NFS.

	Note flock is per open file description: a second acquire of the same path
	from the same process (a fresh fd) blocks against the first. Callers that
	already hold the lock must not re-take it (see load_sessions(lock=False)).
	"""
	lock_path.parent.mkdir(parents=True, exist_ok=True)
	lock_file = open(lock_path, 'w')
	try:
		fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | (0 if blocking else fcntl.LOCK_NB))
	except BlockingIOError:
		lock_file.close()
		if blocking:
			raise
		return None
	return lock_file


def release_file_lock(lock_file) -> None:
	fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
	lock_file.close()


@contextmanager
def file_lock(lock_path: Path, blocking: bool = True):
	"""Cross-process file lock using fcntl. Yields True once held; with blocking=False yields False instead of waiting."""
	lock_file = acquire_file_lock(lock_path, blocking)
	try:
		yield lock_file is not None
	finally:
		if lock_file is not None:
			release_file_lock(lock_file)


def load_sessions(json_path: Path, *, lock: bool = True) -> list[dict]:
	"""Load sessions from a JSON file with locking. lock=False when the caller already holds file_lock() for this file."""
	if not json_path.exists():
		return []

	if not lock:
		with open(json_path, "r") as f:
			return json.load(f)

	with file_lock(lock_path_for(json_path)):
		with open(json_path, "r") as f:
			return json.load(f)


def save_sessions(json_path: Path, sessions: list[dict], *, lock: bool = True, durable: bool = True):
	"""Atomically save history; native answers are durable by default.

	durable=False is only for rebuildable derived records. lock=False means
	the caller already holds file_lock() for this file.
	"""
	json_path.parent.mkdir(parents=True, exist_ok=True)

	if not lock:
		# A stopped collector must not leave the trusted history truncated.
		with tempfile.NamedTemporaryFile(mode="w", dir=json_path.parent, delete=False) as f:
			try:
				json.dump(sessions, f, indent=2)
				f.flush()
				if durable:
					os.fsync(f.fileno())
				os.replace(f.name, json_path)
			finally:
				if os.path.exists(f.name):
					os.unlink(f.name)
		return

	with file_lock(lock_path_for(json_path)):
		save_sessions(json_path, sessions, lock=False, durable=durable)


def session_fingerprint(session: dict) -> str:
	"""Stable evidence reference without changing the recorded model answer."""
	return hashlib.sha256(json.dumps(session, sort_keys=True, separators=(",", ":"),
		ensure_ascii=False).encode()).hexdigest()


def append_assessment(json_path: Path, assessment: dict) -> bool:
	"""Append a review under the collector's lock; replaying the same review is safe."""
	if assessment.get("kind") != "assessment" or not assessment.get("review_id"):
		raise ValueError("An assessment needs kind='assessment' and a review_id")
	with file_lock(lock_path_for(json_path)):
		history = load_sessions(json_path, lock=False)
		for record in history:
			if record.get("kind") == "assessment" and record.get("review_id") == assessment["review_id"]:
				if record != assessment:
					raise ValueError("Review ID already exists with different content; append a new revision")
				return False
		history.append(assessment)
		save_sessions(json_path, history, lock=False)
	return True


def _session_matches(
	session: dict,
	model: str,
	prompt_text: str,
	temperature: float,
	max_tokens: int,
	verbose: bool = False,
	label: str = "",
	response_format: dict | None = None,
) -> bool:
	"""True if the session was run with exactly these parameters (model, temperature, max_tokens, full prompt text)."""
	if not is_model_session(session):
		return False
	meta = session.get("metadata", {})
	req = session.get("request", {})

	# Check model
	if meta.get("model") != model:
		if verbose:
			print(f"  Session {label}: different model ({meta.get('model')} != {model})")
		return False

	# Check temperature
	if req.get("temperature") != temperature:
		if verbose:
			print(f"  Session {label}: different temperature")
		return False

	# Check max_tokens
	if req.get("max_tokens") != max_tokens:
		if verbose:
			print(f"  Session {label}: different max_tokens")
		return False
	if req.get("response_format", {"type": "json_object"}) != (response_format or {"type": "json_object"}):
		return False

	# Check full prompt text
	entry_prompt = ""
	try:
		entry_prompt = req.get("messages", [{}])[0].get("content", [{}])[0].get("text", "")
	except (IndexError, TypeError):
		pass

	if entry_prompt != prompt_text:
		if verbose:
			print(f"  Session {label}: different prompt")
		return False

	return True


def find_duplicate(
	sessions: list[dict],
	model: str,
	prompt_text: str,
	temperature: float,
	max_tokens: int,
	image_hash: str | None = None,
	verbose: bool = False,
	response_format: dict | None = None,
) -> dict | None:
	"""
	Find an existing successful session with matching parameters.

	Args:
		sessions: List of analysis session dicts
		model: Model identifier
		prompt_text: Full prompt text (includes schema and focal length context)
		temperature: API temperature setting
		max_tokens: API max_tokens setting
		image_hash: Hash of the processed image (optional, for extra verification)
		verbose: Print debug info

	Returns:
		Matching session dict, or None if no duplicate found
	"""
	if verbose:
		failed = [s for s in sessions if s.get('result', {}).get('parse_error')]
		if failed:
			requests = sum(bool(s.get('result', {}).get('error')) for s in failed)
			print(f"  Saved failures ignored: {requests} request/provider errors, {len(failed) - requests} invalid answers")
	for i, session in enumerate(sessions):
		# Skip sessions with parse errors - allow rerun
		if session.get("result", {}).get("parse_error"):
			continue

		if _session_matches(session, model, prompt_text, temperature, max_tokens, verbose=verbose, label=str(i), response_format=response_format):
			if verbose:
				print(f"  Session {i}: DUPLICATE FOUND")
			return session

	return None


def count_failed_attempts(
	sessions: list[dict],
	model: str,
	prompt_text: str,
	temperature: float,
	max_tokens: int,
	response_format: dict | None = None,
) -> int:
	"""
	How many times this exact configuration (same match as find_duplicate) has
	produced unparseable output for this photo. The sessions file is the record
	of attempts; the analyzer uses this count to back off and eventually give up.
	"""
	return sum(
		1 for session in sessions
		if session.get("result", {}).get("parse_error")
		and not session.get("result", {}).get("error")
		and _session_matches(session, model, prompt_text, temperature, max_tokens, response_format=response_format)
	)


def matching_request_rejections(sessions, model, prompt, temperature, max_tokens, response_format):
	return [s for s in sessions if s.get('result', {}).get('http_status') == 400
	        and s.get('result', {}).get('error')
	        and _session_matches(s, model, prompt, temperature, max_tokens, response_format=response_format)]

CATEGORY_DEFAULTS = {
	"kilometers": 100000,
	"hundreds_of_meters": 500,
	"tens_of_meters": 50,
	"meters": 5,
}

WORD_NUMBERS = {
	"one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
	"six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
	"eleven": 11, "twelve": 12, "fifteen": 15, "twenty": 20,
	"thirty": 30, "forty": 40, "fifty": 50, "sixty": 60,
	"seventy": 70, "eighty": 80, "ninety": 90,
}

MULTIPLIERS = {
	"tens": 10,
	"hundred": 100,
	"hundreds": 100,
	"thousand": 1000,
	"thousands": 1000,
}


def word_to_number(text: str) -> str:
	"""Convert word numbers to digits, handling compounds like 'two hundred'."""
	# Handle "X multiplier" compounds first (e.g., "two hundred" -> "200", "five thousand" -> "5000")
	for word, num in WORD_NUMBERS.items():
		for mult_word, mult_val in MULTIPLIERS.items():
			text = re.sub(rf'\b{word}\s+{mult_word}\b', str(num * mult_val), text)

	# Then simple word numbers
	for word, num in WORD_NUMBERS.items():
		text = re.sub(rf'\b{word}\b', str(num), text)

	return text


def _parse_legacy_distance_estimate(estimate: str) -> float | None:
	"""Parse a distance estimate string into meters. Returns None if unparseable."""
	text = estimate.lower().strip()

	# Convert word numbers to digits
	text = word_to_number(text)

	# First, normalize "kilometers" -> "km", "meters" -> "m"
	text = re.sub(r'\bkilometers?\b', 'km', text)
	text = re.sub(r'\bmeters?\b', 'm', text)

	# Handle "less than X" / "under X" / "< X" patterns
	less_than_match = re.search(r'(?:less than|under|<)\s*(\d+(?:\.\d+)?)\s*(km|m)', text)
	if less_than_match:
		val = float(less_than_match.group(1))
		unit = less_than_match.group(2)
		if unit == 'km':
			return val * 1000
		return val

	# Handle "more than X" / "over X" / "> X" / "X+" patterns
	more_than_match = re.search(r'(?:more than|over|>)\s*(\d+(?:\.\d+)?)\s*(km|m)', text)
	if more_than_match:
		val = float(more_than_match.group(1))
		unit = more_than_match.group(2)
		if unit == 'km':
			return val * 1000
		return val

	# Handle "X+" pattern (e.g., "10+ km")
	plus_match = re.search(r'(\d+(?:\.\d+)?)\+\s*(km|m)', text)
	if plus_match:
		val = float(plus_match.group(1))
		unit = plus_match.group(2)
		if unit == 'km':
			return val * 1000
		return val

	# Handle "several hundred meters" / "a few hundred meters" etc.
	if re.search(r'(?:several|a few|few)\s+hundred\s+m', text):
		return 500  # reasonable estimate for "several hundred meters"

	# Handle "several kilometers" / "a few kilometers" etc.
	if re.search(r'(?:several|a few|few)\s+km', text):
		return 5000  # reasonable estimate for "several kilometers"

	# Handle "a few meters" / "several meters"
	if re.search(r'(?:several|a few|few)\s+m\b', text):
		return 5  # reasonable estimate for "a few meters"

	# Handle "tens of meters" / "dozens of meters"
	if re.search(r'(?:tens|dozens)\s+of\s+m', text):
		return 50  # reasonable estimate for "tens of meters"

	# Handle "hundreds of meters"
	if re.search(r'hundreds\s+of\s+m', text):
		return 500  # reasonable estimate for "hundreds of meters"

	# Handle "tens of kilometers"
	if re.search(r'tens\s+of\s+km', text):
		return 50000  # reasonable estimate for "tens of kilometers"

	# Handle "hundreds of kilometers"
	if re.search(r'hundreds\s+of\s+km', text):
		return 500000  # reasonable estimate for "hundreds of kilometers"

	# Handle vague distance terms
	if re.search(r'\b(?:immediately\s+)?adjacent\b', text):
		return 1  # "adjacent" or "immediately adjacent"
	if re.search(r'\b(?:very\s+)?close\b', text):
		return 2  # "close" or "very close"
	if re.search(r'\bnearby\b', text):
		return 5
	if re.search(r'\b(?:very\s+)?far\b', text):
		return 1000  # "far" or "very far"

	# Handle bare unit (no number) - use category defaults
	if re.search(r'^\s*m\s*$', text):
		return 5  # just "meters" with no number
	if re.search(r'^\s*km\s*$', text):
		return 1000  # just "kilometers" with no number

	# Handle "within meters" / "within kilometers"
	if re.search(r'within\s+m\b', text):
		return 5  # "within meters"
	if re.search(r'within\s+km\b', text):
		return 1000  # "within kilometers"

	# Try to find range pattern: "X-Y" or "X to Y" followed by unit
	range_match = re.search(r'(\d+(?:\.\d+)?)\s*(?:-|to)\s*(\d+(?:\.\d+)?)\s*(km|m)', text)
	if range_match:
		val1 = float(range_match.group(1))
		val2 = float(range_match.group(2))
		unit = range_match.group(3)
		avg = (val1 + val2) / 2
		if unit == 'km':
			return avg * 1000
		return avg

	# Try single value with unit
	single_match = re.search(r'(\d+(?:\.\d+)?)\s*(km|m)', text)
	if single_match:
		val = float(single_match.group(1))
		unit = single_match.group(2)
		if unit == 'km':
			return val * 1000
		return val

	return None


@dataclass(frozen=True)
class DistanceEstimate:
	"""Keep bounds and interpretation alongside the legacy scalar DB value."""
	estimate_m: float
	lower_m: float | None
	upper_m: float | None
	kind: str  # point | range | upper_bound | lower_bound | heuristic | category_default
	source: str = "distance_estimate"


def parse_distance_details(estimate: str) -> DistanceEstimate | None:
	"""Parse explicit quantities before vague words, preserving mixed-unit bounds."""
	if not isinstance(estimate, str):
		return None
	text = word_to_number(estimate.lower().strip())
	# Natural-language quantities from older responses, before unit normalization.
	text = re.sub(r"\ba couple of\s+(?=(?:kilo)?met(?:er|re)s?\b)", "2 ", text)
	text = re.sub(r"\b(?:a|an)\s+(?=(?:kilo)?met(?:er|re)s?\b)", "1 ", text)
	text = re.sub(r"[–—−]", "-", text)
	text = re.sub(r"(?<=\d),(?=\d{3}(?:\D|$))", "", text)
	text = re.sub(r"\bkilomet(?:er|re)s?\b", "km", text)
	text = re.sub(r"\bmet(?:er|re)s?\b", "m", text)
	number = r"(?:\d+(?:\.\d+)?|\.\d+)"
	range_match = re.search(
		rf"(?<![\d.\-])(?P<first>{number})\s*(?P<u1>km\b|m\b)?\s*"
		rf"(?P<join>-|\bto\b|\band\b)\s*(?P<second>{number})\s*(?P<u2>km\b|m\b)?",
		text,
	)
	if range_match and (range_match["u1"] or range_match["u2"]):
		# "and" is a range only in "between X and Y", not two unrelated quantities.
		if range_match["join"] != "and" or re.search(r"\bbetween\s*$", text[:range_match.start()]):
			u1 = range_match["u1"] or range_match["u2"]
			u2 = range_match["u2"] or range_match["u1"]
			first = float(range_match["first"]) * (1000 if u1 == "km" else 1)
			second = float(range_match["second"]) * (1000 if u2 == "km" else 1)
			lower, upper = sorted((first, second))
			if re.search(r"(?:less than|under|<|≤)\s*$", text[:range_match.start()]):
				# The first endpoint is open-ended: don't claim it is a lower bound.
				return DistanceEstimate((lower + upper) / 2, None, upper, "range")
			return DistanceEstimate((lower + upper) / 2, lower, upper, "range")
	if re.search(r"(?:^|\s)-\s*\d", text):
		return None
	quantity = re.search(rf"(?<![\d.\-])(?P<value>{number})\s*(?P<plus>\+)?\s*(?P<unit>km\b|m\b)", text)
	if quantity:
		value = float(quantity["value"]) * (1000 if quantity["unit"] == "km" else 1)
		prefix = text[:quantity.start()]
		if re.search(r"(?:less than|under|up to|at most|within|<=|<|≤)\s*$", prefix):
			return DistanceEstimate(value, None, value, "upper_bound")
		if quantity["plus"] or re.search(r"(?:more than|over|at least|>=|>|≥)\s*$", prefix):
			return DistanceEstimate(value, value, None, "lower_bound")
		return DistanceEstimate(value, value, value, "point")
	value = _parse_legacy_distance_estimate(text)
	if value is not None:
		return DistanceEstimate(value, None, None, "heuristic")
	return None


def parse_distance_estimate(estimate: str) -> float | None:
	"""Backward-compatible scalar: midpoint for ranges, stated limit for bounds."""
	parsed = parse_distance_details(estimate)
	return parsed.estimate_m if parsed else None


def parse_object_distance_details(obj: dict) -> DistanceEstimate | None:
	parsed = parse_distance_details(obj.get("distance_estimate"))
	if parsed is not None:
		return parsed
	default = CATEGORY_DEFAULTS.get(obj.get("distance_category"))
	if default is not None:
		return DistanceEstimate(default, None, None, "category_default", "distance_category")
	return None


def is_model_session(record: dict) -> bool:
	"""Existing untagged records are model sessions; assessments are never answers."""
	return record.get("kind", "llm_session") == "llm_session"


def parse_object_distance(obj: dict, context: str) -> float | None:
	"""Parse distance from an object dict. Returns None on failure."""
	estimate = obj.get("distance_estimate")
	category = obj.get("distance_category")

	# Try distance_estimate first
	if estimate:
		distance = parse_distance_estimate(estimate)
		if distance is not None:
			return distance
		# If estimate exists but couldn't parse, log warning
		print(f"Warning: Could not parse distance_estimate '{estimate}' for {context}")

	# Fall back to category
	if category:
		if category in CATEGORY_DEFAULTS:
			return CATEGORY_DEFAULTS[category]
		print(f"Warning: Unknown distance_category '{category}' for {context}")

	return None


def get_sorted_successful_sessions(sessions: list[dict]) -> list[dict]:
	"""Return sessions without parse errors, sorted by timestamp (most recent first)."""
	successful = [s for s in sessions
		if is_model_session(s) and not s.get("result", {}).get("parse_error", True)
		and s.get("metadata", {}).get("model") in TRUSTED_MODELS]
	successful.sort(key=lambda s: s.get("metadata", {}).get("timestamp", ""), reverse=True)
	return successful


def find_field(sessions: list[dict], *field_names: str) -> tuple[str | None, any]:
	"""Walk sessions and return first found field (tries each name in order)."""
	for session in sessions:
		analysis = session.get("analysis", {})
		for field_name in field_names:
			if field_name in analysis:
				return field_name, analysis[field_name]
	return None, None


def find_metadata_field(sessions: list[dict], field_name: str) -> any:
	"""Walk sessions and return first found metadata field."""
	for session in sessions:
		metadata = session.get("metadata", {})
		if field_name in metadata and metadata[field_name] is not None:
			return metadata[field_name]
	return None


def distill_sessions(sessions: list[dict]) -> dict | None:
	"""
	Merge fields from multiple analysis sessions, preferring most recent.

	Args:
		sessions: List of analysis session dicts

	Returns:
		Distilled analysis dict, or None if no successful sessions
	"""
	sorted_sessions = get_sorted_successful_sessions(sessions)
	if not sorted_sessions:
		return None

	distilled = {
		"image_url": find_metadata_field(sorted_sessions, "image_url"),
		#"focal_length_35mm": find_metadata_field(sorted_sessions, "focal_length_35mm"),
	}

	# Distance fields - accept both _object and _structure variants
	_, farthest = find_field(sorted_sessions, "farthest_object", "farthest_structure")
	if farthest:
		distilled["farthest_object"] = farthest
		distance = parse_object_distance(farthest, "farthest_object")
		if distance is not None:
			distilled["farthest_object_distance"] = distance

	_, closest = find_field(sorted_sessions, "closest_object", "closest_structure")
	if closest:
		distilled["closest_object"] = closest
		distance = parse_object_distance(closest, "closest_object")
		if distance is not None:
			distilled["closest_object_distance"] = distance

	# Other analysis fields
	for field in ["time_of_day", "location_type", "scenic_score", "visibility_distance",
				  "tallest_building", "description"]:
		_, value = find_field(sorted_sessions, field)
		if value is not None:
			distilled[field] = value

	# Features - collect true ones
	_, features = find_field(sorted_sessions, "features")
	true_features = []
	if features:
		true_features = [k for k, v in features.items() if v is True]

	distilled["features"] = true_features

	return distilled
