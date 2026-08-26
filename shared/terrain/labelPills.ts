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
	/** leader stroke width at scale 1 (default 1); paper wants more */
	leaderWidth?: number;
	palette?: SkyPillPalette;
}

/** Colours of the slats. Default = the on-screen look; a host printing on
 *  paper passes SKY_PILL_PALETTE_PRINT (black on white). The anchor dots keep
 *  their class tint either way. */
export interface SkyPillPalette {
	leader: string;
	pillPlace: string;
	pillTerrain: string;
	pillStroke: string;
	text: string;
}

export const SKY_PILL_PALETTE_SCREEN: SkyPillPalette = {
	leader: 'rgba(255,255,255,0.55)',
	pillPlace: 'rgba(20,44,74,0.68)',
	pillTerrain: 'rgba(0,0,0,0.62)',
	pillStroke: 'rgba(255,255,255,0.35)',
	text: '#fff'
};

export const SKY_PILL_PALETTE_PRINT: SkyPillPalette = {
	leader: 'rgba(0,0,0,0.65)',
	// settlements keep a faint blue cast so the two classes stay apart on paper
	pillPlace: 'rgba(232,240,250,0.94)',
	pillTerrain: 'rgba(255,255,255,0.92)',
	pillStroke: 'rgba(0,0,0,0.45)',
	text: '#111'
};

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
	const palette = style.palette ?? SKY_PILL_PALETTE_SCREEN;
	const leaderWidth = style.leaderWidth ?? 1;
	ctx.textBaseline = 'middle';
	// Two passes — every leader and anchor dot first, then every slat — so
	// no slat has a later label's leader drawn across it.
	for (const l of pills) {
		const isPlace = !!l.kind && PLACE_KINDS.has(l.kind);
		const dim = l.cls === 'direction';
		ctx.globalAlpha = dim ? 0.55 : 1;
		// leader: from just above the anchor to the pill origin (a direction
		// leader stops well clear of the ridge — the anchor is what hides the
		// place, and the line must not touch it)
		ctx.strokeStyle = palette.leader;
		ctx.lineWidth = leaderWidth * k;
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
	}
	for (const l of pills) {
		const isPlace = !!l.kind && PLACE_KINDS.has(l.kind);
		const dim = l.cls === 'direction';
		ctx.globalAlpha = dim ? 0.55 : 1;
		// the slat: pill + text along its axis, up-right at the layout angle
		ctx.save();
		ctx.translate(l.ox, l.oy);
		ctx.rotate(-l.angle);
		ctx.beginPath();
		ctx.roundRect(0, -l.pillH, l.pillW, l.pillH, 4 * k);
		ctx.fillStyle = isPlace ? palette.pillPlace : palette.pillTerrain;
		ctx.fill();
		ctx.strokeStyle = palette.pillStroke;
		ctx.stroke();
		ctx.fillStyle = palette.text;
		ctx.fillText(l.label, 6 * k, -l.pillH / 2 + 0.5);
		ctx.restore();
	}
	ctx.globalAlpha = 1;
}
