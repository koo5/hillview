/**
 * Sky-pill painter shared by the overlay bench (enrich), the photo zoom view
 * (frontend) and the terrain pane: a slat rising from just above its anchor
 * at the layout angle (peakLabels.layoutSkyLabels), a leader up to it, an
 * anchor dot — styled by what the label CLAIMS (peakLabels.LabelClass):
 *   summit / mass  full opacity; settlements tinted blue, terrain yellow/black
 *   direction      dim, dashed leader ending a few px ABOVE the ridge line
 *                  (the anchor is the top edge of the terrain that hides the
 *                  POI, not the POI — the leader must not touch it), no
 *                  anchor dot
 * Layout is peakLabels.layoutSkyLabels; this only paints. Pure in the "only
 * touches the ctx you hand it" sense.
 */
import { PLACE_KINDS, type LabelClass, type SkyLabel } from './peakLabels';

/** how far above the ridge line a direction label's leader stops (px) */
export const DIRECTION_LEADER_LIFT_PX = 8;

/** Everything the pill draws, at scale 1. A host that scales its labels
 * (the zoom view's "Label scale" slider) passes a multiplier and every
 * length grows with it — the layouter's slat pitch already follows, since
 * it is derived from the pill height. */
export interface SkyPillStyle {
	scale?: number;
}

export interface SkyPillFacts {
	kind?: string;
	cls?: LabelClass;
}

export function paintSkyPills(
	ctx: CanvasRenderingContext2D,
	pills: (SkyLabel & SkyPillFacts)[],
	style: SkyPillStyle = {}
): void {
	const k = style.scale ?? 1;
	ctx.textBaseline = 'middle';
	for (const l of pills) {
		const isPlace = !!l.kind && PLACE_KINDS.has(l.kind);
		const dim = l.cls === 'direction';
		ctx.globalAlpha = dim ? 0.55 : 1;
		// leader: from just above the anchor to the pill origin (a direction
		// leader stops well clear of the ridge — the anchor is what hides the
		// place, and the line must not touch it)
		ctx.strokeStyle = 'rgba(255,255,255,0.55)';
		ctx.lineWidth = 1 * k;
		if (dim) ctx.setLineDash([3 * k, 3 * k]);
		ctx.beginPath();
		ctx.moveTo(l.cx, l.cy - (dim ? DIRECTION_LEADER_LIFT_PX : 3) * k);
		ctx.lineTo(l.ox, l.oy);
		ctx.stroke();
		ctx.setLineDash([]);
		if (!dim) {
			ctx.beginPath();
			ctx.arc(l.cx, l.cy, 2.2 * k, 0, Math.PI * 2);
			ctx.fillStyle = isPlace ? 'rgba(143,180,217,0.95)' : 'rgba(255,220,50,0.95)';
			ctx.fill();
		}
		// the slat: pill + text along its axis, up-right at the layout angle
		ctx.save();
		ctx.translate(l.ox, l.oy);
		ctx.rotate(-l.angle);
		ctx.beginPath();
		ctx.roundRect(0, -l.pillH, l.pillW, l.pillH, 4 * k);
		ctx.fillStyle = isPlace ? 'rgba(20,44,74,0.68)' : 'rgba(0,0,0,0.62)';
		ctx.fill();
		ctx.strokeStyle = 'rgba(255,255,255,0.35)';
		ctx.stroke();
		ctx.fillStyle = '#fff';
		ctx.fillText(l.label, 6 * k, -l.pillH / 2 + 0.5);
		ctx.restore();
	}
	ctx.globalAlpha = 1;
}
