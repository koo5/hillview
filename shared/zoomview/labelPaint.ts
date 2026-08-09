/**
 * Canvas painting for edge labels — extracted verbatim from
 * OpenSeadragonViewer.svelte's drawLabelsNow so the workbench can reuse it.
 * Pure in the "only touches the ctx you hand it" sense: no DOM lookups, no
 * OSD, no component state. Layout (where pills go) is labelLayout.ts; this
 * module only paints the commands.
 */
import type { LabelDrawCmd } from './labelLayout';

export interface LabelPaintStyle {
	labelFont: string;
	labelPad: number;
	leaderWidth: number;
	leaderDash: number;
	pillRadius: number;
	textBaselineOffset: number;
}

export function paintLabels(
	ctx: CanvasRenderingContext2D,
	W: number,
	H: number,
	cmds: LabelDrawCmd[],
	style: LabelPaintStyle
): void {
	const { labelFont, labelPad, leaderWidth, leaderDash, pillRadius, textBaselineOffset } = style;

	ctx.clearRect(0, 0, W, H);

	// Pass 1: leader lines for every label, drawn first so that all label
	// pills (pass 2) sit on top of them — otherwise a later annotation's
	// yellow-black line would draw over an earlier annotation's pill.
	for (const { cx, cy, edge, tx, ty, pillW, pillH } of cmds) {
		const pillCx = tx + pillW / 2;
		const pillCy = ty + pillH / 2;
		const toX = edge === 'left' || edge === 'right' ? tx + (edge === 'left' ? 0 : pillW) : pillCx;
		const toY = edge === 'top' || edge === 'bottom' ? ty + (edge === 'top' ? 0 : pillH) : pillCy;

		ctx.beginPath();
		ctx.moveTo(cx, cy);
		ctx.strokeStyle = 'rgba(255,255,55,1)';
		ctx.lineWidth = leaderWidth;
		ctx.lineTo(toX, toY);
		ctx.stroke();

		ctx.beginPath();
		ctx.moveTo(cx, cy);
		ctx.setLineDash([leaderDash, leaderDash]);
		ctx.lineTo(toX, toY);
		ctx.strokeStyle = 'rgba(0,0,0,0.85)';
		ctx.lineWidth = leaderWidth;
		ctx.stroke();
		ctx.setLineDash([]);
	}

	// Pass 2: label pills, drawn on top of all leader lines.
	ctx.font = labelFont;
	for (const { label, tx, ty, pillW, pillH } of cmds) {
		ctx.fillStyle = 'rgba(0,0,0,0.75)';
		ctx.beginPath();
		// eslint-disable-next-line @typescript-eslint/no-explicit-any
		if (typeof (ctx as any).roundRect === 'function') {
			// eslint-disable-next-line @typescript-eslint/no-explicit-any
			(ctx as any).roundRect(tx, ty, pillW, pillH, pillRadius);
		} else {
			ctx.rect(tx, ty, pillW, pillH);
		}
		ctx.fill();
		ctx.fillStyle = '#fff';
		ctx.fillText(label, tx + labelPad, ty + pillH - textBaselineOffset);
	}
}
