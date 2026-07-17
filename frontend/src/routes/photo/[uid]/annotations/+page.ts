// Client-only, moderator-gated per-photo annotation history. Never prerender:
// it depends on runtime auth/role and the [uid] param, same as the parent
// photo route and the /admin pages.
export const prerender = false;
