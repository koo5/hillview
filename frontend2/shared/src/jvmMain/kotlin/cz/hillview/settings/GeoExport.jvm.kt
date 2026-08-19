package cz.hillview.settings

actual fun geoAutoExportEnabled(): Boolean = false

actual fun setGeoAutoExport(enabled: Boolean) {}

actual fun exportGeoTrackingNow() {}

actual fun trackingExportFolderLabel(): String? = null

actual fun clearTrackingExportFolder() {}

@androidx.compose.runtime.Composable
actual fun rememberTrackingFolderPicker(onChosen: () -> Unit): (() -> Unit)? = null
