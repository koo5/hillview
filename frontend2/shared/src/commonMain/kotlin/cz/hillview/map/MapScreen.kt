package cz.hillview.map

import androidx.compose.runtime.Composable
import cz.hillview.settings.MapSettingsRepository

/**
 * The orientation map. Android backs it with osmdroid over our raster tile
 * palette (see TileProviders); other platforms get a placeholder until the
 * map-library evaluation happens (docs/frontend2-rewrite-plan.md, P6).
 */
@Composable
expect fun MapScreen(
    settings: MapSettingsRepository,
    markerSource: PhotoMarkerSource,
    /** The process-wide camera/bearing state (Koin) — shared with capture. */
    stateHolder: MapStateHolder,
    stateStore: MapStateStore,
    session: MapSession,
    /**
     * Draw the map's own controls (zoom, compass, hunter panels). False in
     * float mode: a PiP window is a few centimetres, where those controls
     * cover most of the map and are too small to hit anyway — see
     * cz.hillview.pip.
     */
    showControls: Boolean = true,
)
