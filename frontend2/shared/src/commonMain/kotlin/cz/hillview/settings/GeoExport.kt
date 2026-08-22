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

/**
 * Where exported CSVs land. Null = the app-private GeoTrackingDumps/
 * default, which needs no permission but is DELETED ON UNINSTALL and (since
 * Android 11) unreachable to file managers. Non-null = the display name of a
 * user-picked folder (system folder picker), where exports survive the app —
 * the user's own durability/privacy call, never made for them: a location
 * history that outlives the app is not something to default into, and
 * unprompted files in Documents/ are not either.
 */
expect fun trackingExportFolderLabel(): String?

/** Back to the app-private default (drops the persisted folder grant). */
expect fun clearTrackingExportFolder()

/**
 * A launcher for the system folder picker, or null where none exists
 * (desktop). Calling the returned function opens the picker; a confirmed
 * choice is persisted (with a persistable URI grant) and [onChosen] runs —
 * a cancelled picker runs nothing.
 */
@androidx.compose.runtime.Composable
expect fun rememberTrackingFolderPicker(onChosen: () -> Unit): (() -> Unit)?
