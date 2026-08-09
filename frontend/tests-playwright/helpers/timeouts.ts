/**
 * Global timeout multiplier for the Playwright suite.
 *
 * The base timeout values throughout the suite are already sane Playwright
 * defaults (e.g. 10s for element waits, 3min per test). `T()` scales them
 * uniformly by a single env-configurable knob. Bump it via PW_TIMEOUT_MULT when
 * the machine is under load / contention; keep it low for fast local feedback.
 *
 *   PW_TIMEOUT_MULT=6 bun run test    # widen every timeout 6x under load
 *
 * Default 3 keeps generous headroom while failing genuine hangs far faster than
 * the previous blanket 11x (which turned a stuck navigation into a ~33min hang).
 */
export const TIMEOUT_MULT = Number(process.env.PW_TIMEOUT_MULT ?? '3') || 3;

/** Scale a base millisecond timeout by the env-configurable multiplier. */
export const T = (ms: number): number => Math.round(ms * TIMEOUT_MULT);
