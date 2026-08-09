import { describe, it, expect } from 'vitest';
import {
	displayTitle,
	buildHeadTitle,
	buildHeadDescription,
	buildAnnotationSummary,
	firstAnnotationText,
	annotationKeywords,
	dedupeCaseInsensitive,
	parseUtcTimestamp,
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

	// An untitled photo takes its public title from the annotations, so a leading
	// coordinate segment must not become the <h1>/og:title.
	it('skips a bare coordinate segment when borrowing a title from annotations', () => {
		expect(displayTitle(photo({ original_filename: 'x.jpg' }), [ann('49.9561603N, 15.2874025E|Izomat')]))
			.toBe('Izomat');
		expect(displayTitle(photo({ original_filename: 'x.jpg' }), [ann('49.9561603N, 15.2874025E')]))
			.toBe('x.jpg');
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
	it('tops up a short description with the annotation aggregate', () => {
		expect(
			buildHeadDescription(
				photo({
					description: 'Panorama Prahy z Havránky.',
					place_name: 'Praha-Troja, Praha',
					latitude: 50.1197,
					longitude: 14.4219
				}),
				[ann('Petřín')]
			)
		).toBe('Panorama Prahy z Havránky. • Petřín');
	});

	it('leaves a snippet-filling description alone', () => {
		const long = 'Výhled na celé Polabí od Bezdězu po Sněžku, focené za ideální dohlednosti '
			+ 'krátce po přechodu studené fronty, kdy vzduch vyčistil severák.';
		expect(buildHeadDescription(photo({ description: long }), [ann('Petřín')])).toBe(long);
	});

	it('falls back to the place name before coordinates', () => {
		expect(buildHeadDescription(photo({ place_name: 'Říčany', latitude: 49.9844, longitude: 14.6662 })))
			.toBe('Říčany');
	});

	it('joins place name and annotation summary when there is no description', () => {
		expect(
			buildHeadDescription(photo({ place_name: 'Kaňk, Kutná Hora', latitude: 49.97, longitude: 15.28 }), [
				ann('Chrám svaté Barbory|https://cs.wikipedia.org/wiki/X'),
				ann('Kaufland')
			])
		).toBe('Kaňk, Kutná Hora — Chrám svaté Barbory, Kaufland');
	});

	it('uses the annotation summary alone when there is no place name', () => {
		expect(buildHeadDescription(photo({}), [ann('Petřín')])).toBe('Petřín');
	});

	it('uses coordinates only as a last resort', () => {
		expect(buildHeadDescription(photo({ latitude: 50.1607, longitude: 14.5274 }))).toBe('50.1607, 14.5274');
	});

	it('has a generic fallback when nothing is known', () => {
		expect(buildHeadDescription(photo({}))).toBe('Photo on Hillview');
	});
});

describe('buildAnnotationSummary', () => {
	it('leads with labels whose annotation carries a reference link', () => {
		expect(
			buildAnnotationSummary([
				ann('Kaufland'),
				ann('Chrám svaté Barbory|https://cs.wikipedia.org/wiki/X'),
				ann('Izomat')
			])
		).toBe('Chrám svaté Barbory, Kaufland, Izomat');
	});

	it('packs into the budget and counts the rest as +N', () => {
		expect(buildAnnotationSummary([ann('Petřín'), ann('Vyšehrad'), ann('Žižkov')], 18)).toBe(
			'Petřín, Vyšehrad +1'
		);
	});

	it('always takes at least one label, even over budget', () => {
		expect(buildAnnotationSummary([ann('Kostel Nanebevzetí Panny Marie')], 10)).toBe(
			'Kostel Nanebevzetí Panny Marie'
		);
	});

	it('skips placeholders and coordinate-only bodies, dedupes case-insensitively', () => {
		expect(
			buildAnnotationSummary([
				ann('?'),
				ann('49.9561603N, 15.2874025E'),
				ann('Petřín'),
				ann('petřín')
			])
		).toBe('Petřín');
	});

	it('strips an embedded position from the name slot', () => {
		expect(buildAnnotationSummary([ann('Kostel svatého Štěpána (Malín) 49.966892, 15.305111')])).toBe(
			'Kostel svatého Štěpána (Malín)'
		);
	});

	it('is empty for no usable labels', () => {
		expect(buildAnnotationSummary([])).toBe('');
		expect(buildAnnotationSummary([ann(null), ann('?')])).toBe('');
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

	// Annotators pin a landmark's position as its own segment, in whichever format
	// the picker handed them. Those say nothing about what is in the frame — on a
	// densely annotated pano they were ~half of the emitted keywords.
	it('drops bare coordinate segments but keeps the label beside them', () => {
		expect(annotationKeywords([ann('Vhs|49.95406134617877, 15.290764675932335')])).toEqual(['Vhs']);
		expect(annotationKeywords([ann('vodojem (Jakub)|49.9541936N, 15.3444286E')])).toEqual(['vodojem (Jakub)']);
		expect(annotationKeywords([ann('TJ Sokol Malín|49.9714 15.3035')])).toEqual(['TJ Sokol Malín']);
		expect(annotationKeywords([ann('49.9561603N, 15.2874025E')])).toEqual([]);
	});
});

describe('parseUtcTimestamp', () => {
	it('treats an offset-less string as UTC, not viewer-local', () => {
		expect(parseUtcTimestamp('2026-06-21T13:29:13').getTime()).toBe(
			Date.UTC(2026, 5, 21, 13, 29, 13)
		);
	});

	it('leaves an explicit Z or offset alone', () => {
		expect(parseUtcTimestamp('2026-06-21T13:29:13.000000Z').getTime()).toBe(
			Date.UTC(2026, 5, 21, 13, 29, 13)
		);
		expect(parseUtcTimestamp('2026-06-21T13:29:13+02:00').getTime()).toBe(
			Date.UTC(2026, 5, 21, 11, 29, 13)
		);
	});
});

describe('dedupeCaseInsensitive', () => {
	it('keeps first casing and order, drops empties and case-dupes', () => {
		expect(dedupeCaseInsensitive(['Praha', 'praha', 'B', '', '  ', 'b'])).toEqual(['Praha', 'B']);
	});
});
