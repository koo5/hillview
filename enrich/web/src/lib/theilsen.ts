// Theil-Sen robust line fit — mirror of api/app/calibrate.py (server is authority
// on accept; this powers the live toggle-and-refit display).

export interface FitSummary {
	intercept: number;
	slope: number;
	fov: number;
	centre_bias: number;
	centre_bearing: number | null;
	rms: number;
	n: number;
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
	return p.delta - (fit.intercept + fit.slope * p.x);
}
