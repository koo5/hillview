/**
 * Coordinate-format parser — TypeScript twin of the coordinate handling in
 * the Python annotation-body parser: enrich/api/app/parser.py (COORD_RE +
 * _coords_from_match; lineage: scripts/enrich/resolve_anchors.py). Keep the
 * pattern and semantics in sync both ways — parser.py's COORD_RE comment
 * points back at this file.
 *
 * Accepted formats (lat first, lon second, matching the source convention
 * "50.73N, 15.00E"):
 *   50.732N, 15.008E         hemisphere letters optional; S/W negate
 *   50.732, 15.008           comma- or whitespace-separated
 *   50.732 15.008
 *   50,0620061, 14,8864855   Czech decimal comma
 * Each number needs 3+ decimal places, so prose numbers ("1938, 1500 m")
 * don't false-positive.
 */

const COORD_SRC = '(\\d{1,2}[.,]\\d{3,})\\s*([NnSs])?[,\\s]+(\\d{1,2}[.,]\\d{3,})\\s*([EeWw])?';

const COORD_RE = new RegExp(COORD_SRC);
const COORD_RE_GLOBAL = new RegExp(COORD_SRC, 'g');
const COORD_RE_FULL = new RegExp(`^(?:${COORD_SRC})$`);

export interface CoordMatch {
	lat: number;
	lon: number;
	/** The exact matched substring, e.g. "50.732N, 15.008E". */
	text: string;
	/** Offset of `text` within the input — for wrapping the span in a link. */
	index: number;
}

/** _coord_float in parser.py: decimal comma → dot. */
function coordFloat(s: string): number {
	return parseFloat(s.replace(',', '.'));
}

/** _coords_from_match in parser.py: S/W hemisphere letters negate. */
function toCoordMatch(m: RegExpMatchArray): CoordMatch {
	return {
		lat: coordFloat(m[1]) * (m[2]?.toUpperCase() === 'S' ? -1 : 1),
		lon: coordFloat(m[3]) * (m[4]?.toUpperCase() === 'W' ? -1 : 1),
		text: m[0],
		index: m.index ?? 0,
	};
}

/** First coordinate pair in `text`, or null. (COORD_RE.search in parser.py.) */
export function firstCoords(text: string): CoordMatch | null {
	const m = text.match(COORD_RE);
	return m ? toCoordMatch(m) : null;
}

/** All coordinate pairs in `text`, with offsets. (COORD_RE.finditer.) */
export function findCoords(text: string): CoordMatch[] {
	return [...text.matchAll(COORD_RE_GLOBAL)].map(toCoordMatch);
}

/**
 * Whether `text` is nothing but one coordinate pair. (COORD_RE.fullmatch —
 * parser.py's _segment_role uses this for the name-slot rule: segment 0 only
 * counts as coords when it is a bare pair.)
 */
export function isCoordsOnly(text: string): boolean {
	return COORD_RE_FULL.test(text);
}
