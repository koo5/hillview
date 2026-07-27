// svelte-language-tools (svelte-check, IDE plugins) walk UP from each .svelte
// file to find a config; without one here they fall back to their bundled
// svelte-preprocess, which fails to resolve 'typescript' from this
// node_modules-less tree. Svelte 5 strips lang="ts" natively, so an empty
// config is sufficient — the apps' own configs still govern their builds
// (vite-plugin-svelte uses the app config for every file it compiles,
// including these shared ones).
export default {};
