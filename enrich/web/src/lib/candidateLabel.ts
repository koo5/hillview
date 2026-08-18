import type { Candidate } from './types';

const WIKI_RE = /^https?:\/\/[a-z]{2,3}(?:\.m)?\.wikipedia\.org\/wiki\/(.+)$/;

/** Human name of an anchor candidate. OSM candidates carry a displayName;
 *  wiki candidates' identity IS the page URL (often percent-encoded:
 *  Baba_(z%C5%99%C3%ADcenina)) — show the decoded title; geo: pins and
 *  anything else fall back to the bare URI. */
export function candidateLabel(c: Pick<Candidate, 'candidate' | 'displayName'>): string {
	if (c.displayName) return c.displayName;
	const w = WIKI_RE.exec(c.candidate);
	const raw = w ? w[1].replace(/_/g, ' ') : c.candidate.replace(/^https?:\/\//, '');
	try {
		return decodeURIComponent(raw);
	} catch {
		return raw;
	}
}

/** Short kind tag for the table's type column: OSM type, 'pin' (geo: URI), 'wiki'. */
export function candidateKind(c: Pick<Candidate, 'candidate' | 'osmType'>): string {
	return c.osmType ?? (c.candidate.startsWith('geo:') ? 'pin' : WIKI_RE.test(c.candidate) ? 'wiki' : '');
}
