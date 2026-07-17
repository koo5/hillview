export interface SyncTableState {
	table_name: string;
	watermark: string | null;
	last_append_at: string | null;
	last_reconcile_at: string | null;
	stats: Record<string, unknown> | null;
}

export interface RunRow {
	id: string;
	kind: string;
	status: string;
	started_at: string;
	finished_at: string | null;
	graph_iri?: string | null;
	stats: Record<string, unknown> | null;
	error: string | null;
	note?: string | null;
}

export interface SyncStatus {
	running: boolean;
	state: SyncTableState[];
	counts: Record<string, { total: number; missing: number }>;
	last_runs: RunRow[];
}

export interface Fact {
	fact: string;
	subject?: string;
	predicate: string;
	value: string;
	value_type: 'uri' | 'literal';
	datatype: string | null;
	status: 'proposed' | 'approved' | 'rejected';
}

export interface AnnotationRow {
	id: string;
	photo_id: string;
	body: string | null;
	is_current: boolean;
	created_at: string | null;
	sizes: Record<string, { url?: string }> | null;
	width: number | null;
	height: number | null;
	compass_angle: number | null;
	photo_title: string | null;
	photo_description: string | null;
	place_name: string | null;
	lon: number | null;
	lat: number | null;
	facts: Fact[];
	web_url: string;
	// detail only:
	target?: unknown;
	history?: { id: string; body: string | null; created_at: string | null; event_type: string; depth: number }[];
}

export interface AnnotationList {
	total: number;
	items: AnnotationRow[];
}

export interface Candidate {
	candidate: string;
	fact: string;
	status: 'proposed' | 'approved' | 'rejected';
	lat?: number;
	lon?: number;
	displayName?: string;
	osmType?: string;
	km?: number;
	bearing_offset?: number;
	// the photo's own view pie (matching bench) — drawn when selected/hovered
	pie?: { bearing: number; half: number; radius_m: number };
}

/** Sight-ray wedge (ray-mode matching): the pano's calibration turns rect-x
 *  into an azimuth; the unknown lies in this sector. */
export interface Wedge {
	lat: number;
	lon: number;
	azimuth: number;
	half: number;
	near_m: number;
	far_m: number;
}

export interface CandidatePhoto {
	lat: number | null;
	lon: number | null;
	bearing: number | null;
	// the origin photo's own view pie (calibrated FOV when available)
	pie?: { bearing: number; half: number; radius_m: number; calibrated?: boolean } | null;
}

export interface CandidatesResponse {
	photo: CandidatePhoto;
	// the annotation's exact rect slice (sight ray on the anchor map)
	annotation_pie?: { bearing: number; half: number; radius_m: number; calibrated?: boolean } | null;
	candidates: Candidate[];
}

export interface Health {
	ok: boolean;
	checks: { dep: string; ok: boolean; ms: number; error?: string }[];
}
