package cz.hillview.settings

/**
 * The geo-tracking CSV export controls (GeoTrackingManager, shared-kt):
 * the auto_export preference lives in the SAME prefs file the manager
 * reads (hillview_tracking_prefs), and exportGeoTrackingNow() is the
 * Tauri app's force-dump command — CSVs land in GeoTrackingDumps/ next
 * to the clock videos they calibrate against.
 */
expect fun geoAutoExportEnabled(): Boolean

expect fun setGeoAutoExport(enabled: Boolean)

expect fun exportGeoTrackingNow()
