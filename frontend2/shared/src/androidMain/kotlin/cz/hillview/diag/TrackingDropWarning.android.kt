package cz.hillview.diag

import cz.hillview.plugin.GeoTrackingManager
import kotlinx.coroutines.flow.StateFlow

actual fun trackingDroppedRows(): StateFlow<Long> = GeoTrackingManager.droppedRows
