#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""
Generate an HTML report from photo analysis JSON files.
Usage: uv run generate_report.py --datadir ./results --output report.html
"""

import argparse
import base64
from dataclasses import asdict
import html
import json
import sys
from pathlib import Path
import urllib.request
from urllib.parse import urlparse
from uuid import UUID

from distill import (
	TRUSTED_MODELS, is_model_session, parse_object_distance_details, session_fingerprint,
)

# Unicode icons for features
FEATURE_ICONS = {
	# Nature
	"hill": "⛰️",
	"mountain": "🏔️",
	"river": "🏞️",
	"stream": "💧",
	"water_body": "🌊",
	"landscape": "🌄",
	"rock_outcrop": "🪨",
	"tree_lined_path": "🌳🛤️",
	"nature": "🌿",
	"outdoors_nature": "🏕️",

	# Urban
	"street": "🛣️",
	"building": "🏢",
	"cityscape": "🌆",
	"high_rise_building": "🏙️",
	"church": "⛪",
	"playground": "🛝",
	"bench": "🪑",

	# Structures
	"bridge": "🌉",
	"historic_tower": "🏰",
	"observation_tower": "🗼",
	"water_tower": "🚰🗼",
	"cooling_tower": "🏭",
	"crane": "🏗️",
	"curved_structure": "〰️",

	# Infrastructure
	"lamp_post": "🪔",
	"powerline_pole": "⚡🪵",
	"utility_pole": "🔌🪵",
	"mast": "📡",
	"high_mast_lighting": "💡🗼",
	"ev_charger": "🔋⚡",
	"row_of_streetlights": "💡💡💡",

	# Activity
	"construction": "🚧",
	"roadworks": "🚜🛣️",
	"ski_slope": "⛷️",
	"accident": "⚠️🚗",

	# Animals
	"cat": "🐱",
	"dog": "🐕",

	# Other
	"art": "🎨",
	"signage": "🪧",
	"path": "🛤️",
}


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
	<meta charset="UTF-8">
	<meta name="viewport" content="width=device-width, initial-scale=1.0">
	<title>Photo Analysis Report</title>
	<style>
		* {{
			box-sizing: border-box;
		}}
		body {{
			font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
			margin: 0;
			padding: 20px;
			padding-top: 70px;
			background: #f5f5f5;
		}}
		.controls {{
			position: fixed;
			top: 0;
			left: 0;
			right: 0;
			background: #333;
			padding: 10px 20px;
			z-index: 1000;
			display: flex;
			gap: 10px;
			flex-wrap: wrap;
		}}
		.controls button {{
			padding: 8px 16px;
			border: none;
			border-radius: 4px;
			cursor: pointer;
			font-size: 14px;
			background: #555;
			color: white;
		}}
		.controls button:hover {{
			background: #666;
		}}
		.controls button.active {{
			background: #4CAF50;
		}}
		.photo-entry {{
			background: white;
			margin-bottom: 30px;
			padding: 20px;
			border-radius: 8px;
			box-shadow: 0 2px 4px rgba(0,0,0,0.1);
		}}
		.photo-entry h2 {{
			margin-top: 0;
			font-size: 14px;
			word-break: break-all;
			color: #333;
		}}
		.photo-entry h2 a {{
			color: #0066cc;
			text-decoration: none;
		}}
		.photo-entry h2 a:hover {{
			text-decoration: underline;
		}}
		.photo-content {{
			display: flex;
			gap: 20px;
			align-items: flex-start;
		}}
		.photo-data {{
			flex: 1;
			min-width: 0;
		}}
		.photo-image {{
			flex: 0 0 400px;
			position: sticky;
			top: 70px;
			align-self: flex-start;
		}}
		.photo-image img {{
			max-width: 100%;
			max-height: 80vh;
			display: block;
			border-radius: 4px;
			object-fit: contain;
		}}
		@media (max-width: 900px) {{
			.photo-content {{
				flex-direction: column-reverse;
			}}
			.photo-image {{
				flex: none;
				position: static;
				width: 100%;
			}}
		}}
		.section {{
			margin: 15px 0;
		}}
		.section h3 {{
			margin: 0 0 10px 0;
			font-size: 14px;
			color: #666;
			cursor: pointer;
		}}
		.section h3:hover {{
			color: #333;
		}}
		.section pre {{
			background: #f8f8f8;
			padding: 15px;
			border-radius: 4px;
			overflow-x: auto;
			font-size: 12px;
			margin: 0;
			border: 1px solid #e0e0e0;
		}}
		.section.collapsed pre {{
			display: none;
		}}
		.section.collapsed h3::after {{
			content: " [+]";
			color: #999;
		}}
		.analysis-entry {{
			border-top: 1px solid #eee;
			padding-top: 15px;
			margin-top: 15px;
		}}
		.analysis-entry:first-child {{
			border-top: none;
			padding-top: 0;
			margin-top: 0;
		}}
		.analysis-meta {{
			font-size: 12px;
			color: #666;
			margin-bottom: 10px;
		}}
		.model-columns {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 16px; }}
		.model-column {{ min-width: 0; padding: 14px; background: #f7f9fb; }}
		.model-column h3 {{ overflow-wrap: anywhere; }}
		.comparison-scroll {{ overflow-x: auto; margin: 16px 0; }}
		.comparison {{ border-collapse: collapse; width: 100%; table-layout: fixed; min-width: 750px; }}
		.comparison th, .comparison td {{ border: 1px solid #cbd3db; padding: 10px; vertical-align: top; overflow-wrap: anywhere; }}
		.comparison th {{ background: #e7edf2; }}
		.comparison th:first-child {{ width: 160px; }}
		.comparison tbody tr:nth-child(even) {{ background: #f5f7fa; }}
		.model-history {{ margin: 14px 0; padding: 12px; border: 1px solid #cbd3db; }}
		.model-history > summary {{ cursor: pointer; overflow-wrap: anywhere; font-weight: bold; }}
		.assessment {{ padding: 16px; margin: 16px 0; background: #fff3d8; border: 1px solid #d3b56f; }}
		.badge {{ display: inline-block; padding: 2px 7px; border-radius: 4px; background: #e2e9ee; }}
		.distance {{ padding: 8px; margin: 8px 0; background: #eaf0f5; }}
		.photo-entry, .analysis-entry {{ scroll-margin-top: 85px; }}
		.photo-image {{ flex-basis: 330px; max-height: 80vh; overflow: auto; }}
		.photo-image a {{ display: block; margin: 8px 0 16px; }}
		.photo-image img {{ max-height: 55vh; }}
		.photo-image small {{ overflow-wrap: anywhere; display: block; }}
		.section pre {{ white-space: pre-wrap; overflow-wrap: anywhere; }}
		nav {{ margin: 12px 0; }}
		@media (max-width: 900px) {{
			.model-columns {{ grid-template-columns: 1fr; }}
			.photo-image {{ max-height: none; width: 100%; }}
		}}
	</style>
</head>
<body>
	<div class="controls">
		<button onclick="toggleAll('metadata')" id="btn-metadata" data-testid="report-toggle-metadata" class="active">Metadata</button>
		<button onclick="toggleAll('request')" id="btn-request" data-testid="report-toggle-request">Request</button>
		<button onclick="toggleAll('prompt_template')" id="btn-prompt_template" data-testid="report-toggle-prompt_template">Prompt</button>
		<button onclick="toggleAll('schema')" id="btn-schema" data-testid="report-toggle-schema">Schema</button>
		<button onclick="toggleAll('result')" id="btn-result" data-testid="report-toggle-result" class="active">Result</button>
		<button onclick="toggleAll('analysis')" id="btn-analysis" data-testid="report-toggle-analysis" class="active">Analysis</button>
		<button onclick="toggleAll('raw_response')" id="btn-raw_response" data-testid="report-toggle-raw_response">Raw response</button>
		<button onclick="toggleAll('record')" id="btn-record" data-testid="report-toggle-record">Full record</button>
	</div>

	{content}

	<script>
		// Initial state - some sections collapsed by default
		const defaultCollapsed = ['request', 'prompt_template', 'schema', 'raw_response', 'record', 'assessment'];

		document.addEventListener('DOMContentLoaded', function() {{
			defaultCollapsed.forEach(section => {{
				document.querySelectorAll('.section-' + section).forEach(el => {{
					el.classList.add('collapsed');
				}});
			}});
		}});

		function toggleAll(section) {{
			const elements = document.querySelectorAll('.section-' + section);
			const btn = document.getElementById('btn-' + section);
			const anyVisible = Array.from(elements).some(el => !el.classList.contains('collapsed'));

			elements.forEach(el => {{
				if (anyVisible) {{
					el.classList.add('collapsed');
				}} else {{
					el.classList.remove('collapsed');
				}}
			}});

			btn.classList.toggle('active', !anyVisible);
		}}

		function toggleSection(el) {{
			el.closest('.section').classList.toggle('collapsed');
		}}
		function revealHash() {{
			const target = document.getElementById(location.hash.slice(1));
			if (!target) return;
			let parent = target.parentElement;
			while (parent) {{
				if (parent.tagName === 'DETAILS') parent.open = true;
				parent = parent.parentElement;
			}}
			target.scrollIntoView();
		}}
		window.addEventListener('hashchange', revealHash);
		window.addEventListener('DOMContentLoaded', revealHash);
	</script>
</body>
</html>
"""


def transform_features(features: dict) -> dict:
	"""Replace True values with unicode icons in features dict."""
	result = {}
	for key, value in features.items():
		if value is True:
			result[key] = FEATURE_ICONS.get(key, "✓")
		elif value is False:
			continue  # Skip false values entirely
		else:
			result[key] = value
	return result


def transform_analysis(analysis: dict) -> dict:
	"""Transform analysis dict for display, replacing feature booleans with icons."""
	result = {}
	for key, value in analysis.items():
		if key == "features" and isinstance(value, dict):
			result[key] = transform_features(value)
		else:
			result[key] = value
	return result


def generate_section(name: str, data: dict | str | list, display_name: str | None = None, is_analysis: bool = False) -> str:
	"""Generate HTML for a collapsible section."""
	display = display_name or name.replace('_', ' ').title()

	if is_analysis and isinstance(data, dict):
		data = transform_analysis(data)

	json_str = json.dumps(data, indent=2, ensure_ascii=False) if not isinstance(data, str) else data
	escaped = html.escape(json_str)
	return f'''<div class="section section-{name}">
	<h3 onclick="toggleSection(this)">{html.escape(display)}</h3>
	<pre>{escaped}</pre>
</div>'''


def image_source(url: str, embed: bool, cache: dict) -> str:
	if not embed or url.startswith("data:image/"):
		return url
	if url in cache:
		data = Path(cache[url]).read_bytes()
	else:
		with urllib.request.urlopen(url, timeout=30) as response:
			data = response.read()
	if data.startswith(b"\xff\xd8"):
		mime = "image/jpeg"
	elif data.startswith(b"\x89PNG"):
		mime = "image/png"
	elif data[:4] == b"RIFF" and data[8:12] == b"WEBP":
		mime = "image/webp"
	else:
		raise ValueError(f"Unsupported image contents at {url}")
	return f"data:{mime};base64,{base64.b64encode(data).decode()}"


def record_photo_ids(record: dict) -> set[str]:
	"""Use explicit photo metadata, with the legacy image filename as a fallback."""
	meta = record.get("metadata", {})
	values = [meta.get("photo_id"), record.get("photo_id")]
	image_url = meta.get("image_url")
	if image_url:
		values.append(Path(urlparse(image_url).path).stem)
	ids = set()
	for value in values:
		try:
			ids.add(str(UUID(str(value))))
		except ValueError:
			pass
	return ids


def select_histories(datadir: Path, photo_ids: list[str], photo_map: dict) -> list[tuple[str, Path, list]]:
	"""Select exact IDs in requested order, never confuse the user's folder UUID with a photo."""
	wanted = list(dict.fromkeys(str(UUID(value)) for value in photo_ids))
	found = {}
	all_histories = []
	for path in sorted(datadir.glob("*.json")):
		with path.open() as handle:
			data = json.load(handle)
		history = data if isinstance(data, list) else [data]
		if not history:
			continue
		ids = set().union(*(record_photo_ids(record) for record in history))
		ids.update(str(UUID(key)) for key, value in photo_map.items() if value == path.stem)
		if not wanted:
			all_histories.append((next(iter(sorted(ids)), path.stem), path, history))
		for photo_id in ids.intersection(wanted):
			if photo_id in found and found[photo_id][1] != path:
				raise ValueError(f"Ambiguous photo ID {photo_id}; found in more than one history")
			found[photo_id] = (photo_id, path, history)
	missing = set(wanted) - set(found)
	if missing:
		raise ValueError("Photo IDs not found: " + ", ".join(sorted(missing))
			+ ". Supply --photo-map with a {photo_id: file_md5} JSON map for legacy filenames.")
	return [found[photo_id] for photo_id in wanted] if wanted else all_histories


def generate_assessment(record: dict, anchors: dict) -> str:
	meta = record.get("metadata", {})
	assessment = record.get("assessment", {})
	parts = [f'<aside class="assessment" data-testid="assessment-{html.escape(record["review_id"])}">',
		'<h3>Reviewer assessment</h3>',
		f'<p>{html.escape(str(meta.get("author", "unknown")))} · {html.escape(str(meta.get("timestamp", "")))}</p>',
		f'<p><strong>{html.escape(str(assessment.get("verdict", "")))}</strong></p>',
		f'<p>{html.escape(str(assessment.get("notes", "")))}</p>']
	for evidence in assessment.get("sessions_reviewed", []):
		fingerprint = evidence["session_sha256"]
		label = html.escape(f"{evidence['model']} — {evidence['pass']} @ {evidence['timestamp']}")
		if fingerprint in anchors:
			parts.append(f'<p><a href="#{anchors[fingerprint]}">{label}</a></p>')
		else:
			parts.append(f'<p>{label} (record unavailable)</p>')
	parts.append(generate_section("assessment", assessment, "Full assessment and parser findings"))
	parts.append(generate_section("record", record, "Full review record"))
	parts.append('</aside>')
	return '\n'.join(parts)


def configuration_label(record: dict) -> str:
	format_ = record.get("request", {}).get("response_format") or {"type": "json_object"}
	if format_.get("type") == "json_schema":
		name = format_.get("json_schema", {}).get("name", "")
		version = name.rsplit("_", 1)[-1] if name.startswith("hillview_") else ""
		return "JSON schema" + (" " + version if version else "")
	return "JSON object"


def comparison_table(groups: dict, photo_id: str) -> str:
	"""Align fields across configurations without hiding the raw attempt history."""
	columns = []
	for (model, configuration), entries in groups.items():
		features = None
		distances = None
		for _, session in sorted(entries, key=lambda item: item[1].get("metadata", {}).get("timestamp", ""), reverse=True):
			if session.get("result", {}).get("parse_error", True):
				continue
			answer = session.get("analysis")
			if not isinstance(answer, dict):
				continue
			if features is None and "features" in answer:
				features = answer
			if distances is None and any(key in answer for key in ("closest_object", "closest_structure", "farthest_object", "farthest_structure")):
				distances = answer
		if features is not None or distances is not None or configuration.startswith("JSON schema"):
			columns.append((model, configuration, features or {}, distances or {}))
	if not columns:
		return ''
	header = '<tr><th>Field</th>' + ''.join('<th>'+html.escape(model)+'<br>'+html.escape(configuration)+'</th>'
		for model, configuration, _, _ in columns)+'</tr>'
	def render_table(rows):
		return '<div class="comparison-scroll"><table class="comparison"><thead>'+header+'</thead><tbody>'+''.join(rows)+'</tbody></table></div>'
	def cell(value):
		if value is None:
			return '—'
		if isinstance(value, (dict, list)):
			return html.escape(json.dumps(value, ensure_ascii=False))
		return html.escape(str(value))
	def true_flags_cell(answer):
		value = answer.get("features")
		if isinstance(value, dict):
			flags = sorted(key for key, enabled in value.items() if enabled is True)
		elif isinstance(value, list):
			flags = sorted(value)
		else:
			return '—'
		return '<br>'.join(html.escape(flag) for flag in flags) if flags else 'None'
	rows = ['<tr data-testid="photo-'+html.escape(photo_id)+'-true-feature-flags"><th>True feature flags</th>'
		+ ''.join('<td>'+true_flags_cell(features)+'</td>' for _, _, features, _ in columns)+'</tr>']
	for field in ("description", "time_of_day", "location_type", "scenic_score", "visibility_distance",
		"has_horizon", "tallest_building", "buildings_on_horizon", "signs_or_writing", "objects"):
		rows.append('<tr><th>'+html.escape(field)+'</th>'+''.join('<td>'+cell(features.get(field))+'</td>'
			for _, _, features, _ in columns)+'</tr>')
	for key in ("closest_object", "farthest_object"):
		cells = []
		for _, _, _, answer in columns:
			obj = answer.get(key, answer.get(key.replace('_object', '_structure')))
			if not isinstance(obj, dict):
				cells.append('<td>—</td>')
				continue
			parsed = parse_object_distance_details(obj)
			value = cell(obj.get('description'))+'<br><strong>'+cell(obj.get('distance_estimate'))+'</strong><br>'+cell(obj.get('distance_category'))
			if parsed:
				value += '<br>Scalar: '+cell(parsed.estimate_m)+' m ('+cell(parsed.kind)+')'
			cells.append('<td>'+value+'</td>')
		rows.append('<tr><th>'+key+'</th>'+''.join(cells)+'</tr>')
	parts = [f'<div data-testid="photo-{html.escape(photo_id)}-comparison">',
		'<h3>Field comparison</h3><p>Latest usable field answers per configuration. A dash means missing, not false. Exact reviewed attempts are linked above.</p>',render_table(rows)]
	def flags_for(features):
		value = features.get('features')
		return value if isinstance(value, dict) else {}
	flags = sorted(set().union(*(flags_for(features).keys() for _, _, features, _ in columns)))
	rows = ['<tr><th>'+html.escape(flag)+'</th>'+''.join('<td>'+cell(flags_for(features).get(flag))+'</td>'
		for _, _, features, _ in columns)+'</tr>' for flag in flags]
	parts.append('<details><summary>Compare all feature flags</summary>'+render_table(rows)+'</details></div>')
	return '\n'.join(parts)


def generate_photo_entry(image_path: str, analyses: list[dict], *, photo_id: str | None = None,
		embed_images: bool = False, image_cache: dict | None = None) -> str:
	"""Generate HTML for a single photo with all its analyses."""
	anchor = photo_id or image_path.replace('/', '_').replace(' ', '_')
	anchors = {}
	for i, record in enumerate(analyses):
		if is_model_session(record):
			fingerprint = session_fingerprint(record)
			anchors.setdefault(fingerprint, f"session-{fingerprint}-{i}")
	groups = {}
	urls = {}
	for i, record in enumerate(analyses):
		if not is_model_session(record):
			continue
		meta = record.get("metadata", {})
		groups.setdefault((meta.get("model", "unknown"), configuration_label(record)), []).append((i, record))
		url = meta.get("image_url") or meta.get("image_path")
		if url:
			urls.setdefault(url, set()).add(meta.get("model", "unknown"))
	if not urls and image_path:
		urls[image_path] = set()

	parts = [
		f'<div class="photo-entry" id="{html.escape(anchor)}" data-testid="photo-{html.escape(anchor)}">',
		f'<h2><a href="#{html.escape(anchor)}">Photo {html.escape(anchor)}</a></h2>',
		f'<p>{sum(len(group) for group in groups.values())} model attempts; '
		f'{sum(record.get("kind") == "assessment" for record in analyses)} reviewer assessments.</p>',
		'<div class="photo-content">',
		'<div class="photo-data">',
	]

	for record in reversed(analyses):
		if record.get("kind") == "assessment":
			parts.append(generate_assessment(record, anchors))
		elif not is_model_session(record):
			parts.append(generate_section("record", record, "Other history record"))
	groups = dict(sorted(groups.items(), key=lambda pair: (
		pair[0][0] not in TRUSTED_MODELS,
		not any(not record.get("result", {}).get("parse_error", True) for _, record in pair[1]),
		pair[0],
	)))
	parts.append(comparison_table(groups, anchor))
	parts.append('<h3>All saved attempts</h3><div class="model-histories">')
	for (model, configuration), entries in groups.items():
		parts.append(f'<details class="model-history" data-testid="photo-{html.escape(anchor)}-model-{html.escape(model)}-{html.escape(configuration)}">'
			f'<summary>{html.escape(model)} · {html.escape(configuration)} ({len(entries)} attempts)</summary>'
			f'<span class="badge">{"Trusted for distillation" if model in TRUSTED_MODELS else "Candidate; excluded from distillation"}</span>')
		for i, analysis in entries:
			parts.append(generate_model_entry(i, analysis, anchors))
		parts.append('</details>')
	parts.append('</div>')
	parts.append('</div>')  # close photo-data
	parts.append('<div class="photo-image">')
	for i, (url, source_models) in enumerate(urls.items()):
		if urlparse(url).scheme not in ("", "http", "https", "data"):
			continue
		source = image_source(url, embed_images, image_cache or {})
		parts.append(f'<small>Image {i+1}: {html.escape(", ".join(sorted(source_models)))}</small>'
			f'<a href="{html.escape(url)}" target="_blank" rel="noopener">'
			f'<img src="{html.escape(source)}" alt="Photo {html.escape(anchor)}, image variant {i+1}" loading="lazy" '
			f'data-testid="photo-{html.escape(anchor)}-image-{i+1}"></a>')
	parts.append('</div>')  # close photo-image
	parts.append('</div>')  # close photo-content
	parts.append('</div>')  # close photo-entry
	return '\n'.join(parts)


def generate_model_entry(i: int, analysis: dict, anchors: dict) -> str:
	anchor = f"session-{session_fingerprint(analysis)}-{i}"
	parts = [f'<div class="analysis-entry" id="{anchor}" data-testid="model-attempt-{anchor}">']

	# Show timestamp and model as header
	meta = analysis.get('metadata', {})
	model = meta.get('model', 'unknown')
	timestamp = meta.get('timestamp', 'unknown')
	status = "Request, JSON or schema validation failed" if analysis.get('result', {}).get('parse_error', True) else "JSON parsed (see validation result for schema checks)"
	parts.append(f'<div class="analysis-meta">Attempt {i+1}: {html.escape(model)} @ {html.escape(timestamp)}<br>{status}</div>')
	answer = analysis.get('analysis', {})
	if isinstance(answer, dict):
		for key, legacy in (("closest_object", "closest_structure"), ("farthest_object", "farthest_structure")):
			obj = answer.get(key, answer.get(legacy))
			if not isinstance(obj, dict):
				continue
			parsed = parse_object_distance_details(obj)
			parts.append(f'<div class="distance"><strong>{html.escape(key)}</strong><br>'
				f'{html.escape(str(obj.get("description", "")))}<br>'
				f'Original: {html.escape(str(obj.get("distance_estimate", "(no estimate)")))}<br>'
				f'Category: {html.escape(str(obj.get("distance_category", "(missing)")))}')
			if parsed:
				if parsed.kind == "range":
					meaning = f"Range {parsed.lower_m:g}–{parsed.upper_m:g} m; midpoint {parsed.estimate_m:g} m"
				elif parsed.kind == "upper_bound":
					meaning = f"Upper bound {parsed.upper_m:g} m; scalar uses the stated limit"
				elif parsed.kind == "lower_bound":
					meaning = f"Lower bound {parsed.lower_m:g} m; scalar uses the stated limit"
				elif parsed.kind in ("heuristic", "category_default"):
					meaning = f"Fallback {parsed.estimate_m:g} m ({parsed.kind}); not a numeric model estimate"
				else:
					meaning = f"Parsed estimate {parsed.estimate_m:g} m"
				parts.append('<br>'+html.escape(meaning))
			parts.append('</div>')

	# Add sections for each major part
	for name in ('metadata', 'prompt_template', 'schema', 'request', 'result', 'analysis', 'raw_response'):
		if name in analysis:
			# Full answers retain false flags and missing fields; icons must not hide evidence.
			parts.append(generate_section(name, analysis[name]))
	parts.append(generate_section('record', analysis, 'Full model record'))
	parts.append('</div>')
	return '\n'.join(parts)


def main():
	parser = argparse.ArgumentParser(
		description="Generate HTML report from photo analysis JSON files"
	)
	parser.add_argument(
		"--datadir",
		type=Path,
		required=True,
		help="Directory containing analysis JSON files"
	)
	parser.add_argument(
		"--output", "-o",
		type=Path,
		default=Path("report.html"),
		help="Output HTML file (default: report.html)"
	)
	parser.add_argument("--photo-ids", nargs="+", action="extend", default=[],
		help="Exact photo UUIDs to report, in the requested order")
	parser.add_argument("--photo-ids-file", type=Path, help="Whitespace-separated photo UUIDs")
	parser.add_argument("--photo-map", type=Path,
		help="Optional JSON {photo_id: file_md5} map for legacy image filenames")
	parser.add_argument("--embed-images", action="store_true", help="Embed every image variant for offline review")
	parser.add_argument("--image-cache", type=Path, help="JSON {image_url: local_path} map for embedding without downloads")

	args = parser.parse_args()

	if not args.datadir.exists():
		print(f"Error: Directory not found: {args.datadir}", file=sys.stderr)
		sys.exit(1)

	try:
		photo_ids = args.photo_ids + (args.photo_ids_file.read_text().split() if args.photo_ids_file else [])
		photo_map = json.loads(args.photo_map.read_text()) if args.photo_map else {}
		image_cache = json.loads(args.image_cache.read_text()) if args.image_cache else {}
		histories = select_histories(args.datadir, photo_ids, photo_map)
		if not histories:
			raise ValueError("No photo histories found")
		print(f"Reporting {len(histories)} photos", file=sys.stderr)
		content_parts = ['<nav>' + ' · '.join(
			f'<a href="#{html.escape(photo_id)}">{i+1}: {html.escape(photo_id[:8])}</a>'
			for i, (photo_id, _, _) in enumerate(histories)) + '</nav>']
		for photo_id, path, history in histories:
			content_parts.append(generate_photo_entry(str(path), history, photo_id=photo_id,
				embed_images=args.embed_images, image_cache=image_cache))
	except (OSError, ValueError) as error:
		parser.exit(1, f"Report failed: {error}\n")

	# Generate final HTML
	html_content = HTML_TEMPLATE.format(content='\n'.join(content_parts))

	# Write output
	args.output.write_text(html_content)
	print(f"Report written to {args.output}", file=sys.stderr)


if __name__ == "__main__":
	main()
