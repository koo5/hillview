"""
Distillation library for merging multiple analysis sessions into a single result.
"""

import fcntl
import json
import re
import sys
from contextlib import contextmanager
from pathlib import Path


@contextmanager
def file_lock(lock_path: Path):
	"""Cross-process file lock using fcntl."""
	lock_path.parent.mkdir(parents=True, exist_ok=True)
	lock_file = open(lock_path, 'w')
	try:
		fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
		yield
	finally:
		fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
		lock_file.close()


def load_sessions(json_path: Path) -> list[dict]:
	"""Load sessions from a JSON file with locking."""
	if not json_path.exists():
		return []

	lock_path = json_path.parent / f"{json_path.name}.lock"
	with file_lock(lock_path):
		with open(json_path, "r") as f:
			return json.load(f)


def save_sessions(json_path: Path, sessions: list[dict]):
	"""Save sessions to a JSON file with locking."""
	json_path.parent.mkdir(parents=True, exist_ok=True)
	lock_path = json_path.parent / f"{json_path.name}.lock"
	with file_lock(lock_path):
		with open(json_path, "w") as f:
			json.dump(sessions, f, indent=2)


def find_duplicate(
	sessions: list[dict],
	model: str,
	prompt_text: str,
	temperature: float,
	max_tokens: int,
	image_hash: str | None = None,
	verbose: bool = False
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
	for i, session in enumerate(sessions):
		# Skip sessions with parse errors - allow rerun
		if session.get("result", {}).get("parse_error"):
			if verbose:
				print(f"  Session {i}: skipping (parse_error)")
			continue

		meta = session.get("metadata", {})
		req = session.get("request", {})

		# Check model
		if meta.get("model") != model:
			if verbose:
				print(f"  Session {i}: different model ({meta.get('model')} != {model})")
			continue

		# Check temperature
		if req.get("temperature") != temperature:
			if verbose:
				print(f"  Session {i}: different temperature")
			continue

		# Check max_tokens
		if req.get("max_tokens") != max_tokens:
			if verbose:
				print(f"  Session {i}: different max_tokens")
			continue

		# Check full prompt text
		entry_prompt = ""
		try:
			entry_prompt = req.get("messages", [{}])[0].get("content", [{}])[0].get("text", "")
		except (IndexError, TypeError):
			pass

		if entry_prompt != prompt_text:
			if verbose:
				print(f"  Session {i}: different prompt")
			continue

		if verbose:
			print(f"  Session {i}: DUPLICATE FOUND")
		return session

	return None


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


def parse_distance_estimate(estimate: str) -> float | None:
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
	successful = [s for s in sessions if not s.get("result", {}).get("parse_error", True)]
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
