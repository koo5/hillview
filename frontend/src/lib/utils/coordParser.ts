/**
 * Coordinate-format parser — TypeScript twin of the coordinate handling in
 * the Python annotation-body parser: enrich/api/app/parser.py (COORD_RE +
 * _coords_from_match; lineage: scripts/enrich/resolve_anchors.py). Keep the
 * pattern and semantics in sync both ways — parser.py's COORD_RE comment
 * points back at this file.
 *
 * Accepted formats (lat first, lon second, matching the source convention
 * "50.73N, 15.00E"):
 *   50.732N, 15.008E         hemisphere letters optional
 *   50.732, 15.008           comma- or whitespace-separated
 *   50.732 15.008
 *   50,0620061, 14,8864855   Czech decimal comma
 *   -33.8568, 151.2153       southern/western may use a minus or an S/W letter
 * Each number needs 3+ decimal places, so prose numbers ("1938, 1500 m")
 * don't false-positive.
 *
 * DMS/DDM (parser v9): 50°10'29.869"N, 14°38'52.907"E and 50°10.4978'N —
 * hemisphere letters REQUIRED (the guard against prose like "12°C, 1500 m");
 * unicode primes (′ ″) accepted alongside ' and ".
 */

const COORD_SRC =
	'(-?\\d{1,2}[.,]\\d{3,})\\s*([NnSs])?[,\\s]+(-?\\d{1,3}[.,]\\d{3,})\\s*([EeWw])?';

const COORD_RE = new RegExp(COORD_SRC);
const COORD_RE_GLOBAL = new RegExp(COORD_SRC, 'g');
const COORD_RE_FULL = new RegExp(`^(?:${COORD_SRC})$`);

// DMS_RE in parser.py — group layout: deg, min, sec?, letter × 2
const DMS_SRC =
	"(\\d{1,2})[°º]\\s*(\\d{1,2}(?:[.,]\\d+)?)[′']\\s*(?:(\\d{1,2}(?:[.,]\\d+)?)\\s*(?:[″\"]|''))?\\s*([NnSs])" +
	"[,;\\s]+(\\d{1,3})[°º]\\s*(\\d{1,2}(?:[.,]\\d+)?)[′']\\s*(?:(\\d{1,2}(?:[.,]\\d+)?)\\s*(?:[″\"]|''))?\\s*([EeWw])";

const DMS_RE = new RegExp(DMS_SRC);
const DMS_RE_GLOBAL = new RegExp(DMS_SRC, 'g');
const DMS_RE_FULL = new RegExp(`^(?:${DMS_SRC})$`);

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

/**
 * _hemisphere in parser.py: a leading minus already signed the value; an S/W
 * letter forces the southern/western hemisphere.
 */
function hemisphere(value: number, letter: string | undefined, negative: string): number {
	return letter?.toUpperCase() === negative ? -Math.abs(value) : value;
}

/** _coords_from_match in parser.py. */
function toCoordMatch(m: RegExpMatchArray): CoordMatch {
	return {
		lat: hemisphere(coordFloat(m[1]), m[2], 'S'),
		lon: hemisphere(coordFloat(m[3]), m[4], 'W'),
		text: m[0],
		index: m.index ?? 0,
	};
}

/** _dms_from_match in parser.py. */
function toDmsMatch(m: RegExpMatchArray): CoordMatch {
	const val = (deg: string, min: string, sec: string | undefined, letter: string, neg: string) => {
		const v = parseFloat(deg) + coordFloat(min) / 60 + (sec ? coordFloat(sec) / 3600 : 0);
		return Number(hemisphere(v, letter, neg).toFixed(7));
	};
	return {
		lat: val(m[1], m[2], m[3], m[4], 'S'),
		lon: val(m[5], m[6], m[7], m[8], 'W'),
		text: m[0],
		index: m.index ?? 0,
	};
}

/** First coordinate pair in `text` (decimal preferred, like parser.py), or null. */
export function firstCoords(text: string): CoordMatch | null {
	const m = text.match(COORD_RE);
	if (m) return toCoordMatch(m);
	const dm = text.match(DMS_RE);
	return dm ? toDmsMatch(dm) : null;
}

/** All coordinate pairs in `text` (decimal + DMS), with offsets, in order. */
export function findCoords(text: string): CoordMatch[] {
	const dec = [...text.matchAll(COORD_RE_GLOBAL)].map(toCoordMatch);
	const dms = [...text.matchAll(DMS_RE_GLOBAL)].map(toDmsMatch);
	// the two patterns cannot overlap (DMS needs °; COORD_RE tolerates none),
	// so a plain merge-by-offset keeps runs well-formed
	return [...dec, ...dms].sort((a, b) => a.index - b.index);
}

/**
 * Whether `text` is nothing but one coordinate pair. (COORD_RE.fullmatch —
 * parser.py's _segment_role uses this for the name-slot rule: segment 0 only
 * counts as coords when it is a bare pair.)
 */
export function isCoordsOnly(text: string): boolean {
	return COORD_RE_FULL.test(text) || DMS_RE_FULL.test(text);
}

export type CoordRun =
	| { type: 'text'; value: string }
	| ({ type: 'coords' } & CoordMatch);

/**
 * Split `text` into alternating plain-text and coordinate runs, so a body can
 * be rendered with only the coordinate spans made clickable. Concatenating
 * every run's text reproduces the input exactly. No Python counterpart — the
 * backend consumes coordinates, it never re-renders the prose around them.
 */
export function splitOnCoords(text: string): CoordRun[] {
	const runs: CoordRun[] = [];
	let at = 0;
	for (const c of findCoords(text)) {
		if (c.index > at) runs.push({ type: 'text', value: text.slice(at, c.index) });
		runs.push({ type: 'coords', ...c });
		at = c.index + c.text.length;
	}
	if (at < text.length) runs.push({ type: 'text', value: text.slice(at) });
	return runs;
}
