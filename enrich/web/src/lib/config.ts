// Relative default = same-origin: works behind the caddy front (:8765 / ygg) AND on
// the direct dev server (vite proxies /api → :8070). Override with VITE_ENRICH_API.
export const apiBase = import.meta.env.VITE_ENRICH_API || '/api';
