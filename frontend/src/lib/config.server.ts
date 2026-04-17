import { env } from '$env/dynamic/private';

// Server-side URL for reaching the API from inside SSR.
// In bridge-mode compose, this points to the api service by DNS name (http://api:8055/api).
// In host-mode dev, localhost works.
export const backendInternalUrl = env.BACKEND_INTERNAL_URL || 'http://localhost:8055/api';
