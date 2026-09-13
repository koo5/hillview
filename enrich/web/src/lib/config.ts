// Relative default = same-origin: works behind the caddy front AND on the direct dev
// server (vite proxies /api → :8070). It follows SvelteKit's configured base path, so
// serving the whole workbench under an unguessable prefix needs no second variable —
// set BASE_PATH at build time and the API calls move with the pages. Override with
// VITE_ENRICH_API when the API lives somewhere else entirely.
import { base } from '$app/paths';

export const apiBase = import.meta.env.VITE_ENRICH_API || `${base}/api`;
