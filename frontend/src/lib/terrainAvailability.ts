// Whether this build has terrain mode, kept free of imports so a module that
// only needs the answer (data.svelte.ts) does not pull in the terrain viewer.
export const terrainApiBase: string | null = import.meta.env.VITE_TERRAIN_API || null;
export const terrainModeAvailable = !!terrainApiBase;
