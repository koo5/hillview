package cz.hillview.settings

import android.content.Context
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
