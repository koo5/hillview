import { describe, it, expect } from 'vitest';
import {
	assignEdge,
	computePillRect,
	buildLabelCommands,
	resolveOverlaps,
	LABEL_PAD,
	LABEL_PILL_H,
	LABEL_GAP,
	type LabelDrawCmd,
	type LabelInput,
} from './labelLayout';

const W = 800;
const H = 600;
const MARGIN = 14;

describe('assignEdge', () => {
	it('assigns left edge when point is nearest to left', () => {
		const result = assignEdge(10, 300, W, H, MARGIN);
		expect(result.edge).toBe('left');
		expect(result.lx).toBe(MARGIN);
		expect(result.ly).toBe(300);
	});

	it('assigns right edge when point is nearest to right', () => {
		const result = assignEdge(790, 300, W, H, MARGIN);
		expect(result.edge).toBe('right');
		expect(result.lx).toBe(W - MARGIN);
		expect(result.ly).toBe(300);
	});

	it('assigns top edge when point is nearest to top', () => {
		const result = assignEdge(400, 5, W, H, MARGIN);
		expect(result.edge).toBe('top');
		expect(result.lx).toBe(400);
		expect(result.ly).toBe(MARGIN);
	});

	it('assigns bottom edge when point is nearest to bottom', () => {
		const result = assignEdge(400, 595, W, H, MARGIN);
		expect(result.edge).toBe('bottom');
		expect(result.lx).toBe(400);
		expect(result.ly).toBe(H - MARGIN);
	});

	it('disambiguates corner — left wins over top when equidistant due to check order', () => {
		// At (50, 50), dLeft=50, dTop=50, dRight=750, dBottom=550
		// Math.min picks 50, and dLeft===50 is checked first
		const result = assignEdge(50, 50, W, H, MARGIN);
		expect(result.edge).toBe('left');
	});
});

describe('computePillRect', () => {
	it('anchors pill at left side when anchor is in left half', () => {
		const { tx, ty } = computePillRect(MARGIN, 300, 60, W, H);
		expect(tx).toBe(MARGIN); // pill starts at anchor
		expect(ty).toBe(300);    // top half, so ty = ly
	});

	it('anchors pill at right side when anchor is in right half', () => {
		const lx = W - MARGIN;
		const pillW = 60;
		const { tx } = computePillRect(lx, 300, pillW, W, H);
		expect(tx).toBe(lx - pillW); // pill ends at anchor
	});

	it('places pill above anchor when in bottom half', () => {
		const { ty } = computePillRect(MARGIN, 500, 60, W, H);
		expect(ty).toBe(500 - LABEL_PILL_H);
	});
});

describe('buildLabelCommands', () => {
	it('filters out off-screen annotations', () => {
		const inputs: LabelInput[] = [
			{ label: 'A', cx: -10, cy: 300, pillW: 30 },
			{ label: 'B', cx: 400, cy: 300, pillW: 30 },
			{ label: 'C', cx: 900, cy: 300, pillW: 30 },
		];
		const { cmds } = buildLabelCommands(inputs, W, H, MARGIN);
		expect(cmds).toHaveLength(1);
		expect(cmds[0].label).toBe('B');
	});

	it('builds fingerprint from centroids', () => {
		const inputs: LabelInput[] = [
			{ label: 'A', cx: 100, cy: 200, pillW: 30 },
			{ label: 'B', cx: 300, cy: 400, pillW: 30 },
		];
		const { fingerprint } = buildLabelCommands(inputs, W, H, MARGIN);
		expect(fingerprint).toBe('100,200|300,400');
	});

	it('returns empty for no inputs', () => {
		const { cmds, fingerprint } = buildLabelCommands([], W, H, MARGIN);
		expect(cmds).toHaveLength(0);
		expect(fingerprint).toBe('');
	});

	it('assigns correct pill dimensions', () => {
		const inputs: LabelInput[] = [
			{ label: 'Hello', cx: 10, cy: 300, pillW: 50 },
		];
		const { cmds } = buildLabelCommands(inputs, W, H, MARGIN);
		expect(cmds[0].pillW).toBe(50);
		expect(cmds[0].pillH).toBe(LABEL_PILL_H);
	});
});

describe('resolveOverlaps', () => {
	function makeCmd(overrides: Partial<LabelDrawCmd>): LabelDrawCmd {
		return {
			label: 'X', cx: 100, cy: 100,
			lx: MARGIN, ly: 100,
			edge: 'left',
			pillW: 40, pillH: LABEL_PILL_H,
			tx: MARGIN, ty: 100,
			...overrides,
		};
	}

	it('does nothing when pills on same edge do not overlap', () => {
		const cmds = [
			makeCmd({ ty: 10, ly: 10 }),
			makeCmd({ ty: 100, ly: 100 }),
		];
		const origTy0 = cmds[0].ty;
		const origTy1 = cmds[1].ty;
		resolveOverlaps(cmds, W, H);
		expect(cmds[0].ty).toBe(origTy0);
		expect(cmds[1].ty).toBe(origTy1);
	});

	it('pushes second pill down when two overlap on left edge', () => {
		const cmds = [
			makeCmd({ ty: 100, ly: 100 }),
			makeCmd({ ty: 105, ly: 105 }), // overlaps — within pillH of first
		];
		resolveOverlaps(cmds, W, H);
		const gap = cmds[1].ty - (cmds[0].ty + cmds[0].pillH);
		expect(gap).toBeGreaterThanOrEqual(LABEL_GAP);
	});

	it('pushes second pill right when two overlap on top edge', () => {
		const cmds = [
			makeCmd({ edge: 'top', tx: 100, lx: 120, ly: MARGIN }),
			makeCmd({ edge: 'top', tx: 110, lx: 130, ly: MARGIN, pillW: 40 }), // overlaps
		];
		resolveOverlaps(cmds, W, H);
		const gap = cmds[1].tx - (cmds[0].tx + cmds[0].pillW);
		expect(gap).toBeGreaterThanOrEqual(LABEL_GAP);
	});

	it('does not affect pills on different edges', () => {
		const cmds = [
			makeCmd({ edge: 'left', ty: 100 }),
			makeCmd({ edge: 'right', ty: 100, lx: W - MARGIN, tx: W - MARGIN - 40 }),
		];
		const origTy0 = cmds[0].ty;
		const origTy1 = cmds[1].ty;
		resolveOverlaps(cmds, W, H);
		expect(cmds[0].ty).toBe(origTy0);
		expect(cmds[1].ty).toBe(origTy1);
	});

	it('compresses upward when pills overflow bottom', () => {
		const cmds = [
			makeCmd({ ty: H - 50, ly: H - 50 }),
			makeCmd({ ty: H - 45, ly: H - 45 }),
			makeCmd({ ty: H - 40, ly: H - 40 }),
		];
		resolveOverlaps(cmds, W, H);
		// Last pill should end before H - 2
		const last = cmds[cmds.length - 1];
		expect(last.ty + last.pillH).toBeLessThanOrEqual(H - 2);
	});

	it('compresses leftward when pills overflow right on top edge', () => {
		const cmds = [
			makeCmd({ edge: 'top', tx: W - 100, lx: W - 80, ly: MARGIN, pillW: 50 }),
			makeCmd({ edge: 'top', tx: W - 90, lx: W - 70, ly: MARGIN, pillW: 50 }),
		];
		resolveOverlaps(cmds, W, H);
		const last = cmds[cmds.length - 1];
		expect(last.tx + last.pillW).toBeLessThanOrEqual(W - 2);
	});

	it('handles three overlapping pills on left edge', () => {
		const cmds = [
			makeCmd({ ty: 200, ly: 200 }),
			makeCmd({ ty: 200, ly: 200 }),
			makeCmd({ ty: 200, ly: 200 }),
		];
		resolveOverlaps(cmds, W, H);
		// All three should be non-overlapping
		for (let i = 1; i < cmds.length; i++) {
			const gap = cmds[i].ty - (cmds[i - 1].ty + cmds[i - 1].pillH);
			expect(gap).toBeGreaterThanOrEqual(LABEL_GAP);
		}
	});
});
