import { describe, it, expect } from 'vitest';
import { parseAnnotationBody, type BodyItem } from './annotationBody';

describe('parseAnnotationBody', () => {
	it('returns empty array for empty string', () => {
		expect(parseAnnotationBody('')).toEqual([]);
	});

	it('returns empty array for whitespace-only', () => {
		expect(parseAnnotationBody('   ')).toEqual([]);
	});

	it('parses a single text item', () => {
		const items = parseAnnotationBody('hello world');
		expect(items).toEqual([{ type: 'text', value: 'hello world' }]);
	});

	it('parses a single URL item', () => {
		const items = parseAnnotationBody('https://example.com');
		expect(items).toHaveLength(1);
		expect(items[0].type).toBe('url');
		expect((items[0] as Extract<BodyItem, { type: 'url' }>).value).toBe('https://example.com');
		expect((items[0] as Extract<BodyItem, { type: 'url' }>).display).toBe('example.com');
	});

	it('parses pipe-separated mixed items', () => {
		const items = parseAnnotationBody('foo | https://x.com | bar');
		expect(items).toHaveLength(3);
		expect(items[0]).toEqual({ type: 'text', value: 'foo' });
		expect(items[1].type).toBe('url');
		expect((items[1] as Extract<BodyItem, { type: 'url' }>).value).toBe('https://x.com');
		expect(items[2]).toEqual({ type: 'text', value: 'bar' });
	});

	it('trims whitespace around pipe separators', () => {
		const items = parseAnnotationBody('  foo  |  bar  ');
		expect(items).toEqual([
			{ type: 'text', value: 'foo' },
			{ type: 'text', value: 'bar' },
		]);
	});

	it('skips empty segments', () => {
		const items = parseAnnotationBody('foo | | bar');
		expect(items).toHaveLength(2);
		expect(items[0]).toEqual({ type: 'text', value: 'foo' });
		expect(items[1]).toEqual({ type: 'text', value: 'bar' });
	});

	it('handles http:// URLs', () => {
		const items = parseAnnotationBody('http://insecure.example.com/path');
		expect(items).toHaveLength(1);
		expect(items[0].type).toBe('url');
	});

	it('shows hostname + path hint for URLs with paths', () => {
		const items = parseAnnotationBody('https://github.com/user/repo');
		expect(items).toHaveLength(1);
		const url = items[0] as Extract<BodyItem, { type: 'url' }>;
		expect(url.display).toBe('github.com/\u2026/repo');
	});

	it('strips www. from URL display', () => {
		const items = parseAnnotationBody('https://www.example.com');
		expect(items).toHaveLength(1);
		const url = items[0] as Extract<BodyItem, { type: 'url' }>;
		expect(url.display).toBe('example.com');
	});

	it('handles trailing slashes in URL display', () => {
		const items = parseAnnotationBody('https://example.com/');
		expect(items).toHaveLength(1);
		const url = items[0] as Extract<BodyItem, { type: 'url' }>;
		expect(url.display).toBe('example.com');
	});

	it('does not treat non-URL text with http in it as URL', () => {
		const items = parseAnnotationBody('see http_config for details');
		expect(items).toHaveLength(1);
		expect(items[0].type).toBe('text');
	});

	it('handles multiple URLs', () => {
		const items = parseAnnotationBody('https://a.com | https://b.com');
		expect(items).toHaveLength(2);
		expect(items[0].type).toBe('url');
		expect(items[1].type).toBe('url');
	});
});
