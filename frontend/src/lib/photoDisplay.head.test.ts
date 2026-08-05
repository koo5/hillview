import { describe, it, expect } from 'vitest';
import {
	displayTitle,
	buildHeadTitle,
	buildHeadDescription,
	firstAnnotationText,
	annotationKeywords,
	dedupeCaseInsensitive,
	type PublicPhoto,
	type PhotoAnnotation
} from './photoDisplay';

// Minimal factories — only the fields the head/title helpers read.
const photo = (p: Partial<PublicPhoto>): PublicPhoto =>
	({
		title: null,
		description: null,
		original_filename: null,
		place_name: null,
		latitude: null,
		longitude: null,
		...p
	}) as unknown as PublicPhoto;

const ann = (body: string | null): PhotoAnnotation =>
	({ id: 'a', body, owner_username: 'kolman.jindrich', created_at: '2026-06-03T00:00:00Z' }) as PhotoAnnotation;

describe('displayTitle', () => {
	it('prefers an explicit title over everything', () => {
		expect(displayTitle(photo({ title: 'Havránka', description: 'd', original_filename: 'f.jpg' }), [ann('X')]))
			.toBe('Havránka');
	});

	it('uses the description when there is no title', () => {
		expect(displayTitle(photo({ description: 'Panorama Prahy z Havránky.' }))).toBe('Panorama Prahy z Havránky.');
	});

	it('prefers a landmark annotation over a raw camera filename', () => {
		expect(displayTitle(photo({ original_filename: '036A8750.webp' }), [ann('Prosek Point')]))
			.toBe('Prosek Point');
	});

	it('beats an emoji/garbage filename with the annotation', () => {
		expect(
			displayTitle(photo({ original_filename: '2025-08-10-20-31-37_↻🔸⟸🌤️.jpg' }), [
				ann('Partyzánská, elektrárna Holešovice')
			])
		).toBe('Partyzánská, elektrárna Holešovice');
	});

	it('skips placeholder annotations, then falls to the filename', () => {
		expect(displayTitle(photo({ original_filename: 'x.jpg' }), [ann('?'), ann('oops')])).toBe('x.jpg');
	});

	it('falls back to the first meaningful annotation past the placeholders', () => {
		expect(displayTitle(photo({ original_filename: 'x.jpg' }), [ann('?'), ann('Žižka')])).toBe('Žižka');
	});

	it('is backward-compatible for grid callers that pass no annotations', () => {
		expect(displayTitle(photo({ original_filename: 'x.jpg' }))).toBe('x.jpg');
		expect(displayTitle(photo({}))).toBe('Photo');
	});
});

describe('buildHeadTitle', () => {
	it('promotes an annotation into the head title and suffixes the site name', () => {
		expect(buildHeadTitle(photo({ original_filename: 'x.jpg' }), [ann('Prosek Point')]))
			.toBe('Prosek Point - Hillview');
	});
});

describe('buildHeadDescription', () => {
	it('uses the description alone — no annotation splice, no coordinate tail', () => {
		expect(
			buildHeadDescription(
				photo({
					description: 'Panorama Prahy z Havránky.',
					place_name: 'Praha-Troja, Praha',
					latitude: 50.1197,
					longitude: 14.4219
				})
			)
		).toBe('Panorama Prahy z Havránky.');
	});

	it('falls back to the place name before coordinates', () => {
		expect(buildHeadDescription(photo({ place_name: 'Říčany', latitude: 49.9844, longitude: 14.6662 })))
			.toBe('Říčany');
	});

	it('uses coordinates only as a last resort', () => {
		expect(buildHeadDescription(photo({ latitude: 50.1607, longitude: 14.5274 }))).toBe('50.1607, 14.5274');
	});

	it('has a generic fallback when nothing is known', () => {
		expect(buildHeadDescription(photo({}))).toBe('Photo on Hillview');
	});
});

describe('firstAnnotationText', () => {
	it('returns the first text segment, skipping a leading URL segment', () => {
		expect(firstAnnotationText([ann('https://cs.wikipedia.org/wiki/X|Husův sbor')])).toBe('Husův sbor');
	});
	it('returns empty string when there is nothing meaningful', () => {
		expect(firstAnnotationText([ann(null), ann('?'), ann('')])).toBe('');
	});
});

describe('annotationKeywords', () => {
	it('collects distinct labels, dropping placeholders and de-duplicating case-insensitively', () => {
		const labels = annotationKeywords([
			ann('Průmyslový palác'),
			ann('průmyslový palác'),
			ann('PRŮMYSLOVÝ PALÁC'),
			ann('?'),
			ann('oops'),
			ann('Žižka')
		]);
		expect(labels).toEqual(['Průmyslový palác', 'Žižka']);
	});

	it('keeps text segments of a piped body but drops the URL segment', () => {
		expect(annotationKeywords([ann('Praha Bubny|https://cs.wikipedia.org/wiki/Praha-Bubny')]))
			.toEqual(['Praha Bubny']);
		expect(annotationKeywords([ann('vysehrad|Grand Hotel Prague Towers')]))
			.toEqual(['vysehrad', 'Grand Hotel Prague Towers']);
	});

	it('ignores empty/null bodies', () => {
		expect(annotationKeywords([ann(null), ann('')])).toEqual([]);
		expect(annotationKeywords()).toEqual([]);
	});
});

describe('dedupeCaseInsensitive', () => {
	it('keeps first casing and order, drops empties and case-dupes', () => {
		expect(dedupeCaseInsensitive(['Praha', 'praha', 'B', '', '  ', 'b'])).toEqual(['Praha', 'B']);
	});
});
