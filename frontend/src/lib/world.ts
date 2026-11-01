/**
 * The 3D world activity (recon ea05): the shared viewer from hillview_common ($world) over the
 * earth service, pointed at via VITE_EARTH_URL. The mode button only appears when it is set.
 */
export const earthUrl: string | null = import.meta.env.VITE_EARTH_URL || null;
export const worldModeAvailable = !!earthUrl;
/** a published atlas (atlas.hillview.cz) drawn in the 3D world; unset = terrain and orthophoto only */
export const atlasUrl: string | null = import.meta.env.VITE_ATLAS_URL || null;
export const atlasChannel: string = import.meta.env.VITE_ATLAS_CHANNEL || 'prod';
