"""
Photo analysis library using OpenRouter's vision models.
Provides functions for analyzing photos and extracting structured metadata.
"""

import base64
import copy
import hashlib
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
import httpx


# OpenRouter API configuration
OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_MODEL = "qwen/qwen3-vl-30b-a3b-thinking"
MAX_TOKENS = 6666
TEMPERATURE = 0


# JSON schema for structured response
SCHEMA_DISTANCES = {
	"type": "object",
	"properties": {
		"farthest_object": {
			"type": "object",
			"properties": {
				"description": {
					"type": "string",
					"description": "Description of the most far-away earth-bound object or structure"
				},
				"distance_category": {
					"type": "string",
					"enum": ["meters", "tens_of_meters", "hundreds_of_meters", "kilometers"],
					"description": "Rough distance category"
				},
				"distance_estimate": {
					"type": "string",
					"description": "More specific distance estimate if possible"
				}
			},
			"required": ["description", "distance_category"]
		},
		"closest_object": {
			"type": "object",
			"properties": {
				"description": {
					"type": "string",
					"description": "Description of the closest in-focus, consequential object or structure (ignore out-of-focus foreground or incidental obstructions like branches)"
				},
				"distance_category": {
					"type": "string",
					"enum": ["meters", "tens_of_meters", "hundreds_of_meters", "kilometers"],
					"description": "Rough distance category"
				},
				"distance_estimate": {
					"type": "string",
					"description": "More specific distance estimate if possible"
				}
			},
			"required": ["description", "distance_category"]
		}
	}
}

SCHEMA_FEATURES = {
	"type": "object",
	"properties": {
		"time_of_day": {
			"type": "string",
			"enum": ["day", "night", "dawn_dusk", "unclear"],
			"description": "Whether the photo appears to be taken during day or night"
		},
		"location_type": {
			"type": "string",
			"enum": ["indoors", "outdoors", "mixed", "unclear"],
			"description": "Whether the photo is taken indoors or outdoors"
		},
		"features": {
			"type": "object",
			"properties": {
				"playground": {"type": "boolean"},
				"hill": {"type": "boolean"},
				"mountain": {"type": "boolean"},
				"street": {"type": "boolean"},
				"building": {"type": "boolean"},
				"bench": {"type": "boolean"},
				"cityscape": {"type": "boolean"},
				"landscape": {"type": "boolean"},
				"art": {"type": "boolean"},
				"construction": {"type": "boolean"},
				"roadworks": {"type": "boolean"},
				"river": {"type": "boolean"},
				"stream": {"type": "boolean"},
				"water_body": {"type": "boolean"},
				"church": {"type": "boolean"},
				"mast": {"type": "boolean"},
				"tower": {"type": "boolean"},
				"observation_tower": {"type": "boolean"},
				"water_tower": {"type": "boolean"},
				"cooling_tower": {"type": "boolean"},
				"lamp_post": {"type": "boolean"},
				"high_rise_building": {"type": "boolean"},
				"ev_charger": {"type": "boolean"},
				"cat": {"type": "boolean"},
				"dog": {"type": "boolean"},
				"accident": {"type": "boolean"},
				"powerline_pole": {"type": "boolean"},
				"bridge": {"type": "boolean"},
				"tree_lined_path": {"type": "boolean"},
				"crane": {"type": "boolean"},
				"curved_structure": {"type": "boolean"},
				"nature": {"type": "boolean"},
				"signage": {"type": "boolean"},
				"ski_slope": {"type": "boolean"},
				"utility_pole": {"type": "boolean"},
				"rock_outcrop": {"type": "boolean"},
				"high_mast_lighting": {"type": "boolean"},
				"row_of_streetlights": {"type": "boolean"},
				"path": {"type": "boolean"}
			},
			"required": ["playground", "hill", "mountain", "street", "building", "bench", "cityscape", "landscape", "art", "construction", "roadworks", "river", "stream", "water_body", "church", "mast", "tower", "observation_tower", "water_tower", "cooling_tower", "lamp_post", "high_rise_building", "ev_charger", "cat", "dog", "accident", "powerline_pole", "bridge", "tree_lined_path", "crane", "curved_structure", "nature", "signage", "ski_slope", "utility_pole", "rock_outcrop", "high_mast_lighting", "row_of_streetlights", "path"]
		},
		"signs_or_writing": {
			"type": "object",
			"properties": {
				"present": {
					"type": "boolean",
					"description": "Whether signs or writing are featured"
				},
				"description": {
					"type": "string",
					"description": "description of the signs/writing if present"
				}
			},
			"required": ["present"]
		},
		"scenic_score": {
			"type": "integer",
			"minimum": 1,
			"maximum": 5,
			"description": "Scenic beauty rating from 1 (mundane) to 5 (exceptional)"
		},
		"visibility_distance": {
			"type": "string",
			"enum": ["near", "medium", "far", "panoramic"],
			"description": "How far you can see in the photo"
		},
		"has_horizon": {
			"type": "boolean",
			"description": "Whether a horizon line is visible (indicates open view)"
		},
		"tallest_building": {
			"type": "string",
			"enum": ["none", "low_rise", "mid_rise", "high_rise", "skyscraper"],
			"description": "Height category of the tallest building visible: none, low_rise (1-3 stories), mid_rise (4-8 stories), high_rise (9-20 stories), skyscraper (20+ stories)"
		},
		"buildings_on_horizon": {
			"type": "boolean",
			"description": "Whether buildings are visible on or near the horizon line"
		},
		"description": {
			"type": "string",
			"description": "A brief description of the image"
		},
		"objects": {
			"type": "array",
			"items": {"type": "string"},
			"description": "List of objects or phenomena visible in the image"
		}
	}
}

PROMPT_TEMPLATE_START = """Analyze this photo.

"""

PROMPT_TEMPLATE_DISTANCES = """
For distance estimation, consider only earth-bound objects or structures (exclude sky, clouds, birds, small objects).
For the closest object, ignore out-of-focus foreground or incidental obstructions like branches partially obscuring the view. {focal_length_note}
"""

PROMPT_TEMPLATE_FEATURES = """
Rate scenic beauty from 1 (mundane parking lot) to 5 (exceptional vista).
Visibility distance: near (few meters), medium (tens of meters), far (hundreds of meters), panoramic (kilometers).

Check for features in these categories:
- Nature: hill, mountain, river, stream, water body, landscape, rock outcrop, tree-lined path, path, nature
- Urban: street, building, cityscape, high-rise building, church, playground, bench
- Structures: bridge, tower, observation tower, water tower, cooling tower, crane, curved structure
- Infrastructure: lamp post, powerline pole, utility pole, mast, high-mast lighting, EV charger, row of streetlights
- Activity: construction, roadworks, ski slope, accident
- Animals: cat, dog
- Other: art, signage

Also note: signs/writing present, horizon visible.

Tallest building visible:
- none: no buildings
- low_rise: 1-3 stories (houses, small shops)
- mid_rise: 4-8 stories (apartment blocks, small offices)
- high_rise: 9-20 stories (prominent tall buildings)
- skyscraper: 20+ stories or visually dominant tower

Describe the image briefly and list objects/phenomena you see.
"""

PROMPT_TEMPLATE_END = """

Respond with JSON matching this schema:
{schema}

Return ONLY the JSON object, no additional text."""


def build_schema(distances: bool = True, features: bool = True) -> dict:
	"""Build response schema from components."""
	properties = {}
	required = []
	if distances:
		properties.update(SCHEMA_DISTANCES["properties"])
		required.extend(["farthest_object", "closest_object"])
	if features:
		properties.update(SCHEMA_FEATURES["properties"])
		required.extend(list(SCHEMA_FEATURES["properties"].keys()))
	return {"type": "object", "properties": properties, "required": required}


def build_prompt_template(distances: bool = True, features: bool = True) -> str:
	"""Build prompt template from components."""
	parts = [PROMPT_TEMPLATE_START]
	if distances:
		parts.append(PROMPT_TEMPLATE_DISTANCES)
	if features:
		parts.append(PROMPT_TEMPLATE_FEATURES)
	parts.append(PROMPT_TEMPLATE_END)
	return "".join(parts)


def compute_distance_for_height(focal_length_mm: float, subject_height_m: float, sensor_height_mm: float = 24) -> float:
	"""Compute the distance at which a subject of given height fills the frame."""
	f = focal_length_mm / 1000
	S = sensor_height_mm / 1000
	return (subject_height_m * f) / S


def generate_focal_length_context(focal_length_mm: float, include_hints: bool = True, include_table: bool = True) -> str:
	"""Generate a helpful context string for distance estimation based on building heights."""
	if not include_hints and not include_table:
		return ""

	# Round large focal lengths for cleaner display
	if focal_length_mm >= 100:
		display_focal_length = round(focal_length_mm / 10) * 10
	elif focal_length_mm >= 50:
		display_focal_length = round(focal_length_mm / 5) * 5
	else:
		display_focal_length = round(focal_length_mm)

	sensor_height_mm = 24
	meters_per_story = 3
	reference_stories = 10
	reference_height = reference_stories * meters_per_story
	normal_focal_length = 50  # "normal" lens approximating human eye

	magnification = focal_length_mm / normal_focal_length
	fractions = [1, 0.5, 0.25, 0.1, 0.05]

	lines = []

	if include_hints:
		lines.append(f"The photo is taken at {display_focal_length}mm focal length (35mm equiv).")
		if magnification > 1:
			lines.append(f"Objects appear {magnification:.1f}x larger than naked eye (50mm). ")
		elif magnification < 1:
			lines.append(f"Objects appear {1/magnification:.1f}x smaller than naked eye (50mm). ")
		lines.append("")

	if include_table:
		lines.append(f"Distance estimation guide using a {reference_stories}-story building ({reference_height}m):")
		for frac in fractions:
			effective_height = reference_height / frac
			distance = compute_distance_for_height(focal_length_mm, effective_height, sensor_height_mm)
			pct = int(frac * 100)
			if distance < 1000:
				distance_text = f"{distance:.0f}m away"
			else:
				distance_text = f"{distance/1000:.1f}km away"
			lines.append(f" If a {reference_stories}-story building ({reference_height}m) takes {pct:>3}% of frame height, it means it is {distance_text}")

		lines.append("")
		lines.append("Scale accordingly for other things (e.g., 5-story building = half these distances, 300-meter hill = 10x these distances).")

	return "\n".join(lines)


def prepare_image_url(image_url: str, fetch_images: bool) -> tuple[str, str | None]:
	"""
	Prepare image URL for OpenRouter API.

	Args:
		image_url: URL to the image
		fetch_images: If True, fetch image and convert to data URL

	Returns:
		(final_url, image_hash) - image_hash is only set if image was fetched
	"""
	if not fetch_images:
		return image_url, None

	# Fetch and encode as base64
	response = httpx.get(image_url, timeout=60.0)
	response.raise_for_status()
	image_bytes = response.content

	# Determine mime type from URL or content-type
	content_type = response.headers.get("content-type", "image/jpeg")
	if "webp" in image_url or "webp" in content_type:
		mime_type = "image/webp"
	elif "png" in image_url or "png" in content_type:
		mime_type = "image/png"
	else:
		mime_type = "image/jpeg"

	image_hash = hashlib.sha256(image_bytes).hexdigest()
	data_url = f"data:{mime_type};base64,{base64.b64encode(image_bytes).decode()}"

	return data_url, image_hash


def get_api_key() -> str:
	"""Read API key from file specified by OPENROUTER_API_KEY_FILE env var."""
	key_file_path = os.environ.get("OPENROUTER_API_KEY_FILE")
	if not key_file_path:
		raise RuntimeError("OPENROUTER_API_KEY_FILE environment variable not set")

	key_file = Path(key_file_path)
	if not key_file.exists():
		raise RuntimeError(f"API key file not found: {key_file}")

	return key_file.read_text().strip()


def call_openrouter_api(
	payload: dict,
	verbose: bool = False
) -> tuple[dict, str]:
	"""
	Call OpenRouter API with the given payload.
	Returns (api_result, content) where content is the response text.
	Handles retries for 502 errors.
	"""
	if verbose:
		payload_size = len(json.dumps(payload))
		print(f"Total payload size: {payload_size / 1024:.1f} KB")

	api_key = get_api_key()
	headers = {
		"Authorization": f"Bearer {api_key}",
		"Content-Type": "application/json",
		"HTTP-Referer": "https://hillview.app",
		"X-Title": "Hillview Photo Analyzer"
	}

	with httpx.Client(timeout=250.0) as client:
		while True:
			response = client.post(OPENROUTER_API_URL, json=payload, headers=headers)

			if response.status_code == 502:
				print(f"[{datetime.now().isoformat()}] Got HTTP 502, retrying in 15s...")
				time.sleep(15)
				continue
			response.raise_for_status()

			try:
				api_result = response.json()
			except json.JSONDecodeError:
				raise RuntimeError(f"API response is not valid JSON: {response.text}")

			if "error" in api_result and api_result["error"].get("code") == 502:
				print(f"[{datetime.now().isoformat()}] Got 502 in response body, retrying in 15s...")
				time.sleep(15)
				continue

			try:
				content = api_result["choices"][0]["message"]["content"]
				return api_result, content
			except (KeyError, IndexError):
				raise RuntimeError(f"Unexpected API response format: {json.dumps(api_result, indent=2)}")


def parse_json_response(content: str | None) -> tuple[dict | None, bool]:
	"""
	Parse JSON from API response, handling markdown code blocks.
	Returns (parsed_dict, parse_error).
	"""
	if content is None:
		return None, True
	try:
		# Handle potential markdown code blocks
		if "```json" in content:
			content = content.split("```json")[1].split("```")[0]
		elif "```" in content:
			content = content.split("```")[1].split("```")[0]
		return json.loads(content.strip()), False
	except json.JSONDecodeError:
		return None, True


def run_analysis(
	model: str,
	image_url: str,
	final_image_url: str,
	image_hash: str | None,
	prompt_text: str,
	verbose: bool
) -> dict:
	"""
	Run analysis on a photo and return the session result.

	Args:
		model: Model identifier
		image_url: Original URL to the image (for metadata)
		final_image_url: URL to use in API call (data URL or original)
		image_hash: SHA256 hash of fetched image, or None if not fetched
		prompt_text: The full prompt text (built by caller)
		verbose: Print debug info

	Returns:
		Session dict with metadata, result, and analysis
	"""
	start_time = datetime.now(timezone.utc)

	# Build the actual payload
	payload = {
		"model": model,
		"messages": [
			{
				"role": "user",
				"content": [
					{"type": "text", "text": prompt_text},
					{"type": "image_url", "image_url": {"url": final_image_url}}
				]
			}
		],
		"max_tokens": MAX_TOKENS,
		"temperature": TEMPERATURE,
		"response_format": {"type": "json_object"},
		"provider": {"sort": "price"}
	}

	# Deep copy and replace image data with hash for storage
	request_for_output = copy.deepcopy(payload)
	request_for_output["messages"][0]["content"][1]["image_url"]["url"] = f"<sha256:{image_hash}>" if image_hash else f"<url:{image_url}>"

	if verbose:
		#print(json.dumps(request_for_output, indent=2))
		pass

	# Build session metadata
	session = {
		"metadata": {
			"model": model,
			"timestamp": start_time.isoformat(),
			"image_url": image_url,
			"image_hash": image_hash,
		},
		"request": request_for_output,
	}

	# Call API
	api_result, content = call_openrouter_api(payload, verbose)
	end_time = datetime.now(timezone.utc)

	# Parse response
	analysis, parse_error = parse_json_response(content)
	if parse_error:
		print(f"Parse error: <Raw response>{content}</Raw response>\n")
		session["raw_response"] = content

	# Extract usage info
	usage = api_result.get("usage", {})
	session["result"] = {
		"duration_ms": int((end_time - start_time).total_seconds() * 1000),
		"prompt_tokens": usage.get("prompt_tokens"),
		"completion_tokens": usage.get("completion_tokens"),
		"total_tokens": usage.get("total_tokens"),
		"parse_error": parse_error
	}

	if analysis is not None:
		session["analysis"] = analysis

	return session
