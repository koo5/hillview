/**
 * Canvas painting for edge labels — extracted verbatim from
 * OpenSeadragonViewer.svelte's drawLabelsNow so the workbench can reuse it.
 * Pure in the "only touches the ctx you hand it" sense: no DOM lookups, no
 * OSD, no component state. Layout (where pills go) is labelLayout.ts; this
 * module only paints the commands.
 */
import type { LabelDrawCmd } from './labelLayout';

/** Colours of the pills and their leaders. The default is the on-screen
 *  look (white on translucent black); a host printing on paper flips it. */
export interface LabelPalette {
	/** solid under-line of the leader */
	leader: string;
	/** dashes painted over it */
	leaderDash: string;
	pill: string;
	/** pill outline; none when absent */
	pillStroke?: string;
	text: string;
}

export const LABEL_PALETTE_SCREEN: LabelPalette = {
	leader: 'rgba(255,255,55,1)',
	leaderDash: 'rgba(0,0,0,0.85)',
	pill: 'rgba(0,0,0,0.75)',
	text: '#fff'
};

/** Black on white for paper: the pill is a paper label; the leader keeps its
 *  yellow/black dashing so it stays visible over any photo (the host makes
 *  it thicker — a stationary hairline is easy to miss on a sheet). */
export const LABEL_PALETTE_PRINT: LabelPalette = {
	leader: 'rgba(255,255,55,1)',
	leaderDash: 'rgba(0,0,0,0.85)',
	pill: 'rgba(255,255,255,0.92)',
	pillStroke: 'rgba(0,0,0,0.45)',
	text: '#111'
};

export interface LabelPaintStyle {
	labelFont: string;
	labelPad: number;
	leaderWidth: number;
	leaderDash: number;
	pillRadius: number;
	textBaselineOffset: number;
	palette?: LabelPalette;
	/** Which pass(es) to paint on this ctx. A host that keeps leaders and
	 *  pills on separate canvases — so another layer (the terrain slats) can
	 *  sit between them — calls twice; default paints both. */
	pass?: 'all' | 'leaders' | 'pills';
}

export function paintLabels(
	ctx: CanvasRenderingContext2D,
	W: number,
	H: number,
	cmds: LabelDrawCmd[],
	style: LabelPaintStyle
): void {
	const { labelFont, labelPad, leaderWidth, leaderDash, pillRadius, textBaselineOffset } = style;
	const palette = style.palette ?? LABEL_PALETTE_SCREEN;
	const pass = style.pass ?? 'all';

	ctx.clearRect(0, 0, W, H);

	// Pass 1: leader lines for every label, drawn first so that all label
	// pills (pass 2) sit on top of them — otherwise a later annotation's
	// yellow-black line would draw over an earlier annotation's pill.
	if (pass !== 'pills') for (const { cx, cy, edge, tx, ty, pillW, pillH } of cmds) {
		const pillCx = tx + pillW / 2;
		const pillCy = ty + pillH / 2;
		const toX = edge === 'left' || edge === 'right' ? tx + (edge === 'left' ? 0 : pillW) : pillCx;
		const toY = edge === 'top' || edge === 'bottom' ? ty + (edge === 'top' ? 0 : pillH) : pillCy;

		ctx.beginPath();
		ctx.moveTo(cx, cy);
		ctx.strokeStyle = palette.leader;
		ctx.lineWidth = leaderWidth;
		ctx.lineTo(toX, toY);
		ctx.stroke();

		ctx.beginPath();
		ctx.moveTo(cx, cy);
		ctx.setLineDash([leaderDash, leaderDash]);
		ctx.lineTo(toX, toY);
		ctx.strokeStyle = palette.leaderDash;
		ctx.lineWidth = leaderWidth;
		ctx.stroke();
		ctx.setLineDash([]);
	}

	// Pass 2: label pills, drawn on top of all leader lines.
	ctx.font = labelFont;
	if (pass !== 'leaders') for (const { label, tx, ty, pillW, pillH } of cmds) {
		ctx.fillStyle = palette.pill;
		ctx.beginPath();
		// eslint-disable-next-line @typescript-eslint/no-explicit-any
		if (typeof (ctx as any).roundRect === 'function') {
			// eslint-disable-next-line @typescript-eslint/no-explicit-any
			(ctx as any).roundRect(tx, ty, pillW, pillH, pillRadius);
		} else {
			ctx.rect(tx, ty, pillW, pillH);
		}
		ctx.fill();
		if (palette.pillStroke) {
			ctx.strokeStyle = palette.pillStroke;
			ctx.lineWidth = 1;
			ctx.stroke();
		}
		ctx.fillStyle = palette.text;
		ctx.fillText(label, tx + labelPad, ty + pillH - textBaselineOffset);
	}
}
