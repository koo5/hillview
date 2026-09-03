// Theil-Sen robust line fit — mirror of api/app/calibrate.py (server is authority
// on accept; this powers the live toggle-and-refit display).

export interface FitSummary {
	/** absent = linear (back-compat) */
	model?: 'linear' | 'rectilinear' | 'piecewise';
	intercept: number;
	slope: number;
	fov: number;
	centre_bias: number;
	centre_bearing: number | null;
	rms: number;
	n: number;
	/** how many Δ were unwrapped by ±360° before fitting (wide pano, compass off-centre) */
	unwrapped?: number;
	/** rectilinear only: projection centre (principal point x) and tan scale */
	x0?: number;
	k?: number;
	/** piecewise only: the stitch model on top of the linear law — seams as
	 * width fractions incl. 0 and 1, and per-panel shift (deg) / scale
	 * (about the panel centre); the overlay bench's knots/hwarp/hscale */
	knots?: number[];
	hwarp?: number[];
	hscale?: number[];
	panel_n?: number[];
}

/** angle difference folded to −180…180 */
export function angNorm(d: number): number {
	return ((((d + 180) % 360) + 360) % 360) - 180;
}

/** mirror of calibrate.unwrap_deltas: Δ is stored folded to ±180; on a pano
 * wider than 180° with the compass off-centre it crosses ±180 INSIDE the
 * image and a straight line sees a 360° jump. Predict each point from the one
 * nearest x = 0.5 with the aspect-ratio FOV prior (9.6° per unit of aspect,
 * clamped 60…360) and add ±360 where the stored Δ is >180° from that.
 * Mutates the points; returns how many were unwrapped (0 = nothing changed). */
export function unwrapDeltas(
	points: { x: number; delta: number }[],
	width: number | null,
	height: number | null,
	priorFov: number | null = null
): number {
	if (points.length < 2) return 0;
	if (!priorFov) {
		if (!width || !height) return 0;
		priorFov = Math.min(360, Math.max(60, (width / height) * 9.6)); // crude: 31:1 measured 166°, 38:1 360°
	}
	const ref = points.reduce((b, p) => (Math.abs(p.x - 0.5) < Math.abs(b.x - 0.5) ? p : b));
	let n = 0;
	for (const p of points) {
		const pred = ref.delta + priorFov * (p.x - ref.x);
		const k = Math.round((pred - p.delta) / 360);
		if (k) {
			p.delta += 360 * k;
			n++;
		}
	}
	return n;
}

/** model-aware prediction: Δ at rect-x under the fit */
export function predict(fit: FitSummary, x: number): number {
	if (fit.model === 'rectilinear')
		return fit.intercept + (Math.atan(fit.k! * (x - fit.x0!)) * 180) / Math.PI;
	if (fit.model === 'piecewise' && fit.knots && fit.hwarp && fit.hscale) {
		const kn = fit.knots;
		let k = 0;
		while (k < kn.length - 2 && x >= kn[k + 1]) k++;
		const c = (kn[k] + kn[k + 1]) / 2;
		// true(x) = ideal(c) + (ideal(x) − ideal(c))/scale + shift
		return fit.intercept + fit.slope * c + (fit.slope * (x - c)) / fit.hscale[k] + fit.hwarp[k];
	}
	return fit.intercept + fit.slope * x;
}

export function theilSen(xs: number[], ys: number[]): [number, number] | null {
	const n = xs.length;
	if (n < 2) return null;
	const slopes: number[] = [];
	for (let i = 0; i < n; i++)
		for (let j = i + 1; j < n; j++) if (xs[j] !== xs[i]) slopes.push((ys[j] - ys[i]) / (xs[j] - xs[i]));
	if (!slopes.length) return null;
	slopes.sort((a, b) => a - b);
	const b = slopes[Math.floor(slopes.length / 2)];
	const residuals = xs.map((x, i) => ys[i] - b * x).sort((p, q) => p - q);
	const a = residuals[Math.floor(residuals.length / 2)];
	return [a, b];
}

export function fitSummary(
	points: { x: number; delta: number }[],
	compass: number | null
): FitSummary | null {
	if (points.length < 2) return null;
	const fit = theilSen(
		points.map((p) => p.x),
		points.map((p) => p.delta)
	);
	if (!fit) return null;
	const [a, b] = fit;
	const rms = Math.sqrt(
		points.reduce((s, p) => s + angNorm(p.delta - (a + b * p.x)) ** 2, 0) / points.length
	);
	const centre_bias = a + b * 0.5;
	return {
		intercept: a,
		slope: b,
		fov: Math.abs(b),
		centre_bias,
		centre_bearing: compass != null ? (((compass + centre_bias) % 360) + 360) % 360 : null,
		rms,
		n: points.length
	};
}

export function residual(p: { x: number; delta: number }, fit: FitSummary): number {
	return angNorm(p.delta - predict(fit, p.x));
}

/** Rectilinear (f0) model: Δ(x) = c + atan(k·(x − x0)), degrees — for panos
 * whose stitch OUTPUT projection is rectilinear; a straight line bows on
 * those (ends one sign, middle the other). Mirror of api fit_rectilinear:
 * coarse (x0, k) grid + local refinement, median offset c (the robust
 * counterpart of the Theil-Sen intercept). Reported fov = azimuth span
 * across the full width, keeping the pie semantics. */
export function fitRectilinear(
	points: { x: number; delta: number }[],
	compass: number | null
): FitSummary | null {
	if (points.length < 4) return null;
	const xs = points.map((p) => p.x);
	const ys = points.map((p) => p.delta);
	const deg = 180 / Math.PI;

	const evalAt = (x0: number, k: number): { c: number; s: number } => {
		const at = xs.map((x) => Math.atan(k * (x - x0)) * deg);
		const r = ys.map((y, i) => y - at[i]).sort((a, b) => a - b);
		const c = r[Math.floor(r.length / 2)];
		let s = 0;
		for (let i = 0; i < xs.length; i++) s += (ys[i] - c - at[i]) ** 2;
		return { c, s };
	};

	let best = { s: Infinity, x0: 0.5, k: 2, c: 0 };
	const consider = (x0: number, k: number) => {
		if (k <= 0.05) return;
		const { c, s } = evalAt(x0, k);
		if (s < best.s) best = { s, x0, k, c };
	};
	for (let i = -25; i <= 75; i++)
		for (let j = 2; j <= 80; j++) consider(i * 0.02, j * 0.1);
	let dx = 0.02,
		dk = 0.1;
	for (let pass = 0; pass < 3; pass++) {
		const { x0, k } = best;
		for (let i = -5; i <= 5; i++)
			for (let j = -5; j <= 5; j++) consider(x0 + (i * dx) / 5, k + (j * dk) / 5);
		dx /= 5;
		dk /= 5;
	}

	const { x0, k, c, s } = best;
	const rms = Math.sqrt(s / points.length);
	const fov = (Math.atan(k * (1 - x0)) - Math.atan(k * (0 - x0))) * deg;
	const centre_bias = c + Math.atan(k * (0.5 - x0)) * deg;
	return {
		model: 'rectilinear',
		intercept: c,
		slope: k * deg, // d(Δ)/dx at x0, °/x
		fov,
		centre_bias,
		centre_bearing: compass != null ? (((compass + centre_bias) % 360) + 360) % 360 : null,
		rms,
		n: points.length,
		x0,
		k
	};
}

/** Stitched-pano model (mirror of api fit_piecewise): the linear law PLUS a
 * per-PANEL shift and scale, panels being the pieces between `seams` (width
 * fractions in (0, 1)). A frame stitched at the wrong focal length leaves
 * exactly this behind: within its region the azimuth runs at a different
 * rate (scale) and is displaced (shift). Per panel the residual against the
 * global line is Theil-Sen-fitted as r = shift + d·(x − centre) (one point →
 * shift only; none → neutral); hscale = b/(b + d), hwarp = shift, knots =
 * [0, …seams, 1] — the overlay bench's handle model, verbatim. */
export function fitPiecewise(
	points: { x: number; delta: number }[],
	compass: number | null,
	seams: number[]
): FitSummary | null {
	if (points.length < 2) return null;
	const base = theilSen(points.map((p) => p.x), points.map((p) => p.delta));
	if (!base) return null;
	const [a, b] = base;
	if (Math.abs(b) < 1e-9) return null;
	const knots = [0, ...[...seams].filter((v) => v > 0 && v < 1).sort((p, q) => p - q), 1];
	const n = knots.length;
	const hwarp = new Array(n).fill(0);
	const hscale = new Array(n).fill(1);
	const panel_n = new Array(n - 1).fill(0);
	for (let k = 0; k < n - 1; k++) {
		const lo = knots[k], hi = knots[k + 1], last = k === n - 2;
		const pk = points.filter((p) => (lo <= p.x && p.x < hi) || (last && p.x === hi));
		panel_n[k] = pk.length;
		if (!pk.length) continue;
		const c = (lo + hi) / 2;
		const rs = pk.map((p) => p.delta - (a + b * p.x));
		let shift = 0, d = 0;
		if (pk.length >= 2 && new Set(pk.map((p) => p.x)).size >= 2) {
			const ts = theilSen(pk.map((p) => p.x - c), rs);
			if (ts) [shift, d] = ts;
			else shift = [...rs].sort((p, q) => p - q)[Math.floor(rs.length / 2)];
		} else shift = rs[0];
		hwarp[k] = +shift.toFixed(3);
		hscale[k] = +Math.min(2, Math.max(0.5, b + d !== 0 ? b / (b + d) : 1)).toFixed(5);
	}
	const fit: FitSummary = {
		model: 'piecewise',
		intercept: a,
		slope: b,
		fov: Math.abs(b),
		centre_bias: a + b * 0.5,
		centre_bearing: compass != null ? (((compass + a + b * 0.5) % 360) + 360) % 360 : null,
		rms: 0,
		n: points.length,
		knots,
		hwarp,
		hscale,
		panel_n
	};
	fit.rms = Math.sqrt(points.reduce((s, p) => s + angNorm(p.delta - predict(fit, p.x)) ** 2, 0) / points.length);
	return fit;
}
