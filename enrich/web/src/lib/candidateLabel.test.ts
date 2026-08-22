import { describe, expect, it } from 'bun:test';
import { candidateKind, candidateLabel } from './candidateLabel';

describe('candidateLabel', () => {
	it('prefers the OSM displayName', () => {
		expect(candidateLabel({ candidate: 'https://www.openstreetmap.org/node/1', displayName: 'Baba, Brno' })).toBe(
			'Baba, Brno'
		);
	});
	it('decodes a percent-encoded wikipedia title (the candidate URI is the page URL)', () => {
		expect(candidateLabel({ candidate: 'https://cs.wikipedia.org/wiki/Baba_(z%C5%99%C3%ADcenina)' })).toBe(
			'Baba (zřícenina)'
		);
		expect(candidateLabel({ candidate: 'https://cs.m.wikipedia.org/wiki/Bezd%C4%9Bz_(hrad)' })).toBe('Bezděz (hrad)');
	});
	it('falls back to the bare URI, surviving malformed escapes', () => {
		expect(candidateLabel({ candidate: 'geo:50.1,14.4' })).toBe('geo:50.1,14.4');
		expect(candidateLabel({ candidate: 'https://cs.wikipedia.org/wiki/Bad%E0' })).toBe('Bad%E0');
	});
});

describe('candidateKind', () => {
	it('osm type, pin, wiki, or nothing', () => {
		expect(candidateKind({ candidate: 'https://www.openstreetmap.org/node/1', osmType: 'natural/peak' })).toBe(
			'natural/peak'
		);
		expect(candidateKind({ candidate: 'geo:50.1,14.4' })).toBe('pin');
		expect(candidateKind({ candidate: 'https://cs.wikipedia.org/wiki/Baba' })).toBe('wiki');
		expect(candidateKind({ candidate: 'https://example.org/x' })).toBe('');
	});
});
