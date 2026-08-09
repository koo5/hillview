// Client-only, admin-gated dashboard. Never prerender it (same as / and
// photo/[uid]): it depends on the runtime auth/profile state, and the web build's
// +page.ts.web shadow would opt into SSR separately if that were ever wanted.
export const prerender = false;
