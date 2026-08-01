// `bun test src/` — bun's runner, not vitest: it needs no installed deps, so
// these run against a bare checkout (the workbench otherwise only has
// playwright, whose specs live outside src/ and are not picked up here).
import { describe, expect, it } from 'bun:test';
import { readdirSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { escapeHtml, html } from './html';

describe('escapeHtml', () => {
	it('neutralises the characters that start markup', () => {
		expect(escapeHtml('<img src=x onerror="alert(1)">')).toBe(
			'&lt;img src=x onerror=&quot;alert(1)&quot;&gt;'
		);
	});

	it('escapes the ampersand first, so entities are not double-decodable', () => {
		expect(escapeHtml('&lt;script&gt;')).toBe('&amp;lt;script&amp;gt;');
	});

	it('renders nullish as empty and keeps 0', () => {
		expect(escapeHtml(null)).toBe('');
		expect(escapeHtml(undefined)).toBe('');
		expect(escapeHtml(0)).toBe('0');
	});
});

describe('html', () => {
	it('keeps literal markup and escapes every interpolation', () => {
		const name = 'Sněžka<img src=x onerror=alert(1)>';
		expect(html`${name}<br>${1.2} km`).toBe(
			'Sněžka&lt;img src=x onerror=alert(1)&gt;<br>1.2 km'
		);
	});

	it('escapes a trailing interpolation with no following literal', () => {
		expect(html`az ${'<b>'}`).toBe('az &lt;b&gt;');
	});
});

// Leaflet assigns a STRING tooltip/popup/divIcon body straight to innerHTML,
// so a raw template literal there is an XSS sink the moment someone
// interpolates server data into it (CVE-shaped: OSM display_name reached
// CandidateMap that way). Escaping at the five known sites only helps if the
// sixth one is caught too — hence this scan rather than a per-site test.
const RAW_SINKS = [
	{ what: 'bindTooltip/bindPopup', re: /\.bind(?:Tooltip|Popup)\(\s*`[^`]*\$\{/ },
	{ what: 'divIcon({ html })', re: /\bhtml:\s*`[^`]*\$\{/ }
];

function sourceFiles(dir: string): string[] {
	return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
		const path = join(dir, entry.name);
		if (entry.isDirectory()) return sourceFiles(path);
		return /\.(svelte|ts)$/.test(entry.name) && !entry.name.endsWith('.test.ts') ? [path] : [];
	});
}

describe('leaflet html sinks', () => {
	it('never receive a raw template literal', () => {
		const src = fileURLToPath(new URL('..', import.meta.url));
		const offenders = sourceFiles(src).flatMap((file) => {
			const text = readFileSync(file, 'utf8');
			return RAW_SINKS.filter(({ re }) => re.test(text)).map(
				({ what }) => `${file.slice(src.length)}: ${what} — use the html\`\` tag from $lib/html`
			);
		});
		expect(offenders).toEqual([]);
	});
});
