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
import html
import json
import sys
from pathlib import Path

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
	</style>
</head>
<body>
	<div class="controls">
		<button onclick="toggleAll('metadata')" id="btn-metadata" class="active">Metadata</button>
		<button onclick="toggleAll('request')" id="btn-request">Request</button>
		<button onclick="toggleAll('prompt_template')" id="btn-prompt_template">Prompt</button>
		<button onclick="toggleAll('schema')" id="btn-schema">Schema</button>
		<button onclick="toggleAll('result')" id="btn-result" class="active">Result</button>
		<button onclick="toggleAll('analysis')" id="btn-analysis" class="active">Analysis</button>
	</div>

	{content}

	<script>
		// Initial state - some sections collapsed by default
		const defaultCollapsed = ['request', 'prompt_template', 'schema'];

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
	<h3 onclick="toggleSection(this)">{display}</h3>
	<pre>{escaped}</pre>
</div>'''


def generate_photo_entry(image_path: str, analyses: list[dict]) -> str:
	"""Generate HTML for a single photo with all its analyses."""
	anchor = image_path.replace('/', '_').replace(' ', '_')

	parts = [
		f'<div class="photo-entry" id="{html.escape(anchor)}">',
		f'<h2><a href="#{html.escape(anchor)}">{html.escape(image_path)}</a></h2>',
		'<div class="photo-content">',
		'<div class="photo-data">',
	]

	for i, analysis in enumerate(analyses):
		parts.append('<div class="analysis-entry">')

		# Show timestamp and model as header
		meta = analysis.get('metadata', {})
		model = meta.get('model', 'unknown')
		timestamp = meta.get('timestamp', 'unknown')
		parts.append(f'<div class="analysis-meta">Analysis {i+1}: {html.escape(model)} @ {html.escape(timestamp)}</div>')

		# Add sections for each major part
		if 'metadata' in analysis:
			parts.append(generate_section('metadata', analysis['metadata']))
		if 'prompt_template' in analysis:
			parts.append(generate_section('prompt_template', analysis['prompt_template'], 'Prompt Template'))
		if 'schema' in analysis:
			parts.append(generate_section('schema', analysis['schema']))
		if 'request' in analysis:
			parts.append(generate_section('request', analysis['request']))
		if 'result' in analysis:
			parts.append(generate_section('result', analysis['result']))
		if 'analysis' in analysis:
			parts.append(generate_section('analysis', analysis['analysis'], is_analysis=True))
		if 'raw_response' in analysis:
			parts.append(generate_section('raw_response', analysis['raw_response'], 'Raw Response'))

		parts.append('</div>')

	parts.append('</div>')  # close photo-data
	parts.append(f'<div class="photo-image"><a href="{html.escape(image_path)}" target="_blank"><img src="{html.escape(image_path)}" alt="Photo" loading="lazy"></a></div>')
	parts.append('</div>')  # close photo-content
	parts.append('</div>')  # close photo-entry
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

	args = parser.parse_args()

	if not args.datadir.exists():
		print(f"Error: Directory not found: {args.datadir}", file=sys.stderr)
		sys.exit(1)

	# Collect all JSON files
	json_files = sorted(args.datadir.glob("*.json"))

	if not json_files:
		print(f"Error: No JSON files found in {args.datadir}", file=sys.stderr)
		sys.exit(1)

	print(f"Found {len(json_files)} JSON files", file=sys.stderr)

	# Generate content for each photo
	content_parts = []

	for json_file in json_files:
		try:
			with open(json_file, "r") as f:
				data = json.load(f)

			# Handle both array format and single object
			if isinstance(data, list):
				analyses = data
			else:
				analyses = [data]

			if not analyses:
				continue

			# Get image path from first analysis
			image_path = analyses[0].get('metadata', {}).get('image_path', str(json_file))

			content_parts.append(generate_photo_entry(image_path, analyses))

		except json.JSONDecodeError as e:
			print(f"Warning: Failed to parse {json_file}: {e}", file=sys.stderr)
		except Exception as e:
			print(f"Warning: Error processing {json_file}: {e}", file=sys.stderr)

	# Generate final HTML
	html_content = HTML_TEMPLATE.format(content='\n'.join(content_parts))

	# Write output
	args.output.write_text(html_content)
	print(f"Report written to {args.output}", file=sys.stderr)


if __name__ == "__main__":
	main()
