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
    onBack: () -> Unit,
    settings: MapSettingsRepository,
    markerSource: PhotoMarkerSource,
    stateStore: MapStateStore,
)
