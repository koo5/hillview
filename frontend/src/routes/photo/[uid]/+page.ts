// prerender must be false for this dynamic route in both builds to prevent
// adapter-static / SvelteKit from trying to prerender [uid]. The web build's
// +page.ts.web shadow additionally sets ssr=true so adapter-node SSRs it.
export const prerender = false;
