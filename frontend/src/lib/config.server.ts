import { BACKEND_INTERNAL_URL } from '$env/static/private';

// Server-side URL for reaching the API from inside SSR. Baked in at build time from frontend/.env.
// In bridge-mode compose, set BACKEND_INTERNAL_URL=http://api:8055/api.
// In host-mode dev, localhost works (default below).
export const backendInternalUrl = BACKEND_INTERNAL_URL || 'http://localhost:8055/api';
