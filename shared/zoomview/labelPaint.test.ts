import { describe, it, expect } from 'vitest';
import { paintLabels, type LabelPaintStyle } from './labelPaint';
import type { LabelDrawCmd } from './labelLayout';

// Behavior-pinning tests for the extraction from OpenSeadragonViewer.svelte:
// a recording ctx captures the exact op sequence the old inline code produced.

const STYLE: LabelPaintStyle = {
	labelFont: 'bold 12px system-ui,sans-serif',
	labelPad: 6,
	leaderWidth: 1.5,
	leaderDash: 15,
	pillRadius: 4,
	textBaselineOffset: 5,
};

function cmd(over: Partial<LabelDrawCmd>): LabelDrawCmd {
	return {
		label: 'Ještěd',
		cx: 100, cy: 100, lx: 0, ly: 0,
		edge: 'left',
		pillW: 60, pillH: 20,
		tx: 10, ty: 90,
		...over,
	};
}

interface Op { op: string; args: unknown[] }

function recordingCtx(withRoundRect = true) {
	const ops: Op[] = [];
	const record = (op: string) => (...args: unknown[]) => { ops.push({ op, args }); };
	const ctx: Record<string, unknown> = {
		clearRect: record('clearRect'),
		beginPath: record('beginPath'),
		moveTo: record('moveTo'),
		lineTo: record('lineTo'),
		stroke: record('stroke'),
		fill: record('fill'),
		rect: record('rect'),
		setLineDash: record('setLineDash'),
		fillText: record('fillText'),
	};
	if (withRoundRect) ctx.roundRect = record('roundRect');
	// record style-property writes too
	for (const prop of ['strokeStyle', 'fillStyle', 'lineWidth', 'font']) {
		let v: unknown;
		Object.defineProperty(ctx, prop, {
			get: () => v,
			set: (nv) => { v = nv; ops.push({ op: `set:${prop}`, args: [nv] }); },
		});
	}
	return { ctx: ctx as unknown as CanvasRenderingContext2D, ops };
}

describe('paintLabels', () => {
	it('clears the canvas first', () => {
		const { ctx, ops } = recordingCtx();
		paintLabels(ctx, 800, 600, [cmd({})], STYLE);
		expect(ops[0]).toEqual({ op: 'clearRect', args: [0, 0, 800, 600] });
	});

	it('draws ALL leader lines before ANY pill (two passes)', () => {
		const { ctx, ops } = recordingCtx();
		paintLabels(ctx, 800, 600, [cmd({}), cmd({ label: 'B', ty: 120 })], STYLE);
		const lastStroke = ops.map((o) => o.op).lastIndexOf('stroke');
		const firstFill = ops.map((o) => o.op).indexOf('fill');
		expect(lastStroke).toBeLessThan(firstFill);
	});

	it('leader = solid yellow stroke then dashed black stroke, dash reset after', () => {
		const { ctx, ops } = recordingCtx();
		paintLabels(ctx, 800, 600, [cmd({})], STYLE);
		const strokes = ops.filter((o) => o.op === 'set:strokeStyle').map((o) => o.args[0]);
		expect(strokes).toEqual(['rgba(255,255,55,1)', 'rgba(0,0,0,0.85)']);
		const dashes = ops.filter((o) => o.op === 'setLineDash').map((o) => o.args[0]);
		expect(dashes).toEqual([[15, 15], []]);
	});

	it('left-edge leader targets the pill left edge midpoint-x', () => {
		const { ctx, ops } = recordingCtx();
		paintLabels(ctx, 800, 600, [cmd({ edge: 'left', tx: 10, ty: 90 })], STYLE);
		const lineTos = ops.filter((o) => o.op === 'lineTo');
		// toX = tx (left edge), toY = pill centre y = ty + pillH/2
		expect(lineTos[0].args).toEqual([10, 100]);
	});

	it('pill uses roundRect when available, rect otherwise; text at pad/baseline offsets', () => {
		const a = recordingCtx(true);
		paintLabels(a.ctx, 800, 600, [cmd({})], STYLE);
		expect(a.ops.some((o) => o.op === 'roundRect')).toBe(true);
		expect(a.ops.some((o) => o.op === 'rect')).toBe(false);
		expect(a.ops.find((o) => o.op === 'fillText')?.args).toEqual(['Ještěd', 16, 105]);

		const b = recordingCtx(false);
		paintLabels(b.ctx, 800, 600, [cmd({})], STYLE);
		expect(b.ops.some((o) => o.op === 'rect')).toBe(true);
	});

	it('no commands → just a clear', () => {
		const { ctx, ops } = recordingCtx();
		paintLabels(ctx, 800, 600, [], STYLE);
		expect(ops.filter((o) => !o.op.startsWith('set:')).map((o) => o.op)).toEqual(['clearRect']);
	});
});
