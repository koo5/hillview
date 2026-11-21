/**
 * The 3D world activity (recon ea05): the shared viewer from hillview_common ($world) over the
 * earth service, pointed at via VITE_EARTH_URL. The mode button only appears when it is set.
 */
export const earthUrl: string | null = import.meta.env.VITE_EARTH_URL || null;
/** which of earth's channels the world draws (each names one release per layer) */
export const earthChannel: string = import.meta.env.VITE_EARTH_CHANNEL || 'prod';
export const worldModeAvailable = !!earthUrl;
/** a published atlas (atlas.hillview.cz) drawn in the 3D world; unset = terrain and orthophoto only */
export const atlasUrl: string | null = import.meta.env.VITE_ATLAS_URL || null;
/** the atlas versions a viewer may choose between (its channels, comma-separated), the default first */
export const atlasChannels: string[] = (import.meta.env.VITE_ATLAS_CHANNELS || 'prod').split(',').map((c: string) => c.trim()).filter(Boolean);
