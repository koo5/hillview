// Theil-Sen robust line fit — mirror of api/app/calibrate.py (server is authority
// on accept; this powers the live toggle-and-refit display).

export interface FitSummary {
	/** absent = linear (back-compat) */
	model?: 'linear' | 'rectilinear';
	intercept: number;
	slope: number;
	fov: number;
	centre_bias: number;
	centre_bearing: number | null;
	rms: number;
	n: number;
	/** rectilinear only: projection centre (principal point x) and tan scale */
	x0?: number;
	k?: number;
}

/** model-aware prediction: Δ at rect-x under the fit */
export function predict(fit: FitSummary, x: number): number {
	if (fit.model === 'rectilinear')
		return fit.intercept + (Math.atan(fit.k! * (x - fit.x0!)) * 180) / Math.PI;
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
		points.reduce((s, p) => s + (p.delta - (a + b * p.x)) ** 2, 0) / points.length
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
	return p.delta - predict(fit, p.x);
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
