// prerender must be false for this dynamic route in both builds to prevent
// adapter-static / SvelteKit from trying to prerender [slug]. The web build's
// +page.ts.web shadow (copied over this file by the Dockerfile) additionally
// sets ssr=true so adapter-node SSRs the redirect.
export const prerender = false;
