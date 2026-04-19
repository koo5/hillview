// Homepage uses url.searchParams in its server load, which is incompatible with
// prerendering. prerender=false in both builds; the web build's +page.ts.web
// adds ssr=true so adapter-node runs SSR at request time.
export const prerender = false;
