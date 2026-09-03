import type { Candidate } from './types';

const WIKI_RE = /^https?:\/\/[a-z]{2,3}(?:\.m)?\.wikipedia\.org\/wiki\/(.+)$/;

/** Human name of an anchor candidate. OSM candidates carry a displayName;
 *  wiki candidates' identity IS the page URL (often percent-encoded:
 *  Baba_(z%C5%99%C3%ADcenina)) — show the decoded title; geo: pins and
 *  anything else fall back to the bare URI. */
export function candidateLabel(c: Pick<Candidate, 'candidate' | 'displayName'>): string {
	if (c.displayName) return c.displayName;
	// a geo: point reads as its coordinates, not as a URI scheme
	const g = /^geo:(-?\d+(?:\.\d+)?),(-?\d+(?:\.\d+)?)/.exec(c.candidate);
	if (g) return `${g[1]}, ${g[2]}`;
	const w = WIKI_RE.exec(c.candidate);
	const raw = w ? w[1].replace(/_/g, ' ') : c.candidate.replace(/^https?:\/\//, '');
	try {
		return decodeURIComponent(raw);
	} catch {
		return raw;
	}
}

/** Short kind tag for the table's type column: OSM type, 'pin' (geo: URI), 'wiki';
 *  a location borrowed from a namesake annotation reads 'namesake'. */
export function candidateKind(
	c: Pick<Candidate, 'candidate' | 'osmType'> & { seeded_from?: unknown[]; own?: boolean }
): string {
	if (c.seeded_from?.length && !c.own && !c.osmType) return 'namesake';
	return c.osmType ?? (c.candidate.startsWith('geo:') ? 'pin' : WIKI_RE.test(c.candidate) ? 'wiki' : '');
}
