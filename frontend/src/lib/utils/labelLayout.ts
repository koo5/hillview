/**
 * Pure geometry functions for positioning annotation labels along canvas edges.
 * No DOM/canvas/OSD dependencies — fully unit-testable.
 */

export type Edge = 'left' | 'right' | 'top' | 'bottom';

export interface LabelDrawCmd {
	label: string;
	cx: number; cy: number;     // annotation centroid (screen px)
	lx: number; ly: number;     // label anchor point (on edge)
	edge: Edge;
	pillW: number; pillH: number;
	tx: number; ty: number;     // pill top-left corner
	id?: string;                // annotation identifier (carried from input)
}

export const LABEL_PAD = 6;
export const LABEL_PILL_H = 20;
export const LABEL_GAP = 3; // minimum gap between pills

/** Determine which canvas edge is nearest to a point. */
export function assignEdge(
	cx: number, cy: number, W: number, H: number, margin: number
): { lx: number; ly: number; edge: Edge } {
	const dLeft = cx;
	const dRight = W - cx;
	const dTop = cy;
	const dBottom = H - cy;
	const nearest = Math.min(dLeft, dRight, dTop, dBottom);

	let lx = cx;
	let ly = cy;
	let edge: Edge;
	if (nearest === dLeft)       { lx = margin; edge = 'left'; }
	else if (nearest === dRight) { lx = W - margin; edge = 'right'; }
	else if (nearest === dTop)   { ly = margin; edge = 'top'; }
	else                         { ly = H - margin; edge = 'bottom'; }

	return { lx, ly, edge };
}

/** Compute pill top-left corner from the edge anchor point. */
export function computePillRect(
	lx: number, ly: number, pillW: number, W: number, H: number
): { tx: number; ty: number } {
	const tx = lx > W / 2 ? lx - pillW : lx;
	const ty = ly > H / 2 ? ly - LABEL_PILL_H : ly;
	return { tx, ty };
}

export interface LabelInput {
	label: string;
	cx: number;
	cy: number;
	pillW: number;
	id?: string;
}

/**
 * Build layout commands from screen-space label inputs.
 * `measureText` is injected so this stays pure (no canvas dependency).
 * Returns commands and a fingerprint for change detection.
 */
export function buildLabelCommands(
	inputs: LabelInput[],
	W: number, H: number,
	margin: number,
): { cmds: LabelDrawCmd[]; fingerprint: string } {
	const cmds: LabelDrawCmd[] = [];
	const fpParts: string[] = [];

	for (const { label, cx, cy, pillW, id } of inputs) {
		if (cx < 0 || cx > W || cy < 0 || cy > H) continue;

		const { lx, ly, edge } = assignEdge(cx, cy, W, H, margin);
		const { tx, ty } = computePillRect(lx, ly, pillW, W, H);

		cmds.push({ label, cx, cy, lx, ly, edge, pillW, pillH: LABEL_PILL_H, tx, ty, id });
		fpParts.push(`${cx},${cy}`);
	}

	return { cmds, fingerprint: fpParts.join('|') };
}

/**
 * Resolve overlapping label pills along shared edges (mutates cmds in-place).
 * Left/right edges: stack vertically. Top/bottom edges: stack horizontally.
 * If pills overflow the canvas, compress them back inward.
 */
export function resolveOverlaps(cmds: LabelDrawCmd[], W: number, H: number): void {
	const groups: Record<Edge, LabelDrawCmd[]> = { left: [], right: [], top: [], bottom: [] };
	for (const cmd of cmds) groups[cmd.edge].push(cmd);

	for (const edge of ['left', 'right', 'top', 'bottom'] as const) {
		const group = groups[edge];
		if (group.length < 2) continue;

		if (edge === 'left' || edge === 'right') {
			// Vertical stacking — sort by ty, push apart
			group.sort((a, b) => a.ty - b.ty);
			for (let i = 1; i < group.length; i++) {
				const prev = group[i - 1];
				const minY = prev.ty + prev.pillH + LABEL_GAP;
				if (group[i].ty < minY) {
					group[i].ty = minY;
					group[i].ly = group[i].ty + LABEL_PILL_H / 2;
				}
			}
			// If last pill overflows bottom, compress upward
			const last = group[group.length - 1];
			if (last.ty + last.pillH > H - 2) {
				const shift = last.ty + last.pillH - (H - 2);
				for (let i = group.length - 1; i >= 0; i--) {
					group[i].ty -= shift;
					group[i].ly = group[i].ty + LABEL_PILL_H / 2;
					if (i > 0) {
						const maxY = group[i].ty - LABEL_GAP - group[i - 1].pillH;
						if (group[i - 1].ty <= maxY) break;
					}
				}
			}
		} else {
			// Horizontal stacking — sort by tx, push apart
			group.sort((a, b) => a.tx - b.tx);
			for (let i = 1; i < group.length; i++) {
				const prev = group[i - 1];
				const minX = prev.tx + prev.pillW + LABEL_GAP;
				if (group[i].tx < minX) {
					group[i].tx = minX;
					group[i].lx = group[i].tx + group[i].pillW / 2;
				}
			}
			// If last pill overflows right, compress leftward
			const last = group[group.length - 1];
			if (last.tx + last.pillW > W - 2) {
				const shift = last.tx + last.pillW - (W - 2);
				for (let i = group.length - 1; i >= 0; i--) {
					group[i].tx -= shift;
					group[i].lx = group[i].tx + group[i].pillW / 2;
					if (i > 0) {
						const maxX = group[i].tx - LABEL_GAP - group[i - 1].pillW;
						if (group[i - 1].tx <= maxX) break;
					}
				}
			}
		}
	}
}
