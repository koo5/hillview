package cz.hillview.settings

import android.content.Context
import android.content.Intent
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.rememberUpdatedState
import androidx.compose.ui.platform.LocalContext
import cz.hillview.plugin.GeoTrackingManager
import org.koin.core.context.GlobalContext

private fun prefs() = GlobalContext.get().get<Context>()
    .getSharedPreferences("hillview_tracking_prefs", Context.MODE_PRIVATE)

actual fun geoAutoExportEnabled(): Boolean = prefs().getBoolean("auto_export", false)

actual fun setGeoAutoExport(enabled: Boolean) {
    prefs().edit().putBoolean("auto_export", enabled).apply()
}

actual fun exportGeoTrackingNow() {
    val context = GlobalContext.get().get<Context>()
    cz.hillview.plugin.GeoTrackingManager.get(context).dumpAndClear(forceDump = true)
}

actual fun trackingExportFolderLabel(): String? =
    prefs().getString(GeoTrackingManager.EXPORT_TREE_URI_PREF, null)
        ?.let { GeoTrackingManager.exportFolderDisplayName(it) }

actual fun clearTrackingExportFolder() {
    val context = GlobalContext.get().get<Context>()
    prefs().getString(GeoTrackingManager.EXPORT_TREE_URI_PREF, null)?.let { uri ->
        try {
            // Return the grant too — holding permissions to a folder we will
            // never write again is untidy, and the system caps persisted
            // grants per app.
            context.contentResolver.releasePersistableUriPermission(
                android.net.Uri.parse(uri),
                Intent.FLAG_GRANT_READ_URI_PERMISSION or Intent.FLAG_GRANT_WRITE_URI_PERMISSION,
            )
        } catch (e: SecurityException) {
            // Already gone (folder deleted, reinstall) — the pref is the
            // part that matters.
        }
    }
    prefs().edit().remove(GeoTrackingManager.EXPORT_TREE_URI_PREF).apply()
    cz.hillview.plugin.EventLog.record("export", "export folder reset to app-private")
}

@Composable
actual fun rememberTrackingFolderPicker(onChosen: () -> Unit): (() -> Unit)? {
    val context = LocalContext.current.applicationContext
    val currentOnChosen by rememberUpdatedState(onChosen)
    val launcher = rememberLauncherForActivityResult(
        ActivityResultContracts.OpenDocumentTree(),
    ) { uri ->
        if (uri == null) return@rememberLauncherForActivityResult // cancelled
        // Persist the grant BEFORE the pref: a pref pointing at a folder we
        // hold no grant to would make every dump fail once, loudly, and then
        // clear itself — needless noise for a plain ordering mistake.
        context.contentResolver.takePersistableUriPermission(
            uri,
            Intent.FLAG_GRANT_READ_URI_PERMISSION or Intent.FLAG_GRANT_WRITE_URI_PERMISSION,
        )
        prefs().edit()
            .putString(GeoTrackingManager.EXPORT_TREE_URI_PREF, uri.toString())
            .apply()
        cz.hillview.plugin.EventLog.record(
            "export",
            "export folder -> " + GeoTrackingManager.exportFolderDisplayName(uri.toString()),
        )
        currentOnChosen()
    }
    return { launcher.launch(null) }
}
