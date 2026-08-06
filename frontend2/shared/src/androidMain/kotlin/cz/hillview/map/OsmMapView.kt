package cz.hillview.map

import android.content.Context
import android.preference.PreferenceManager
import org.osmdroid.config.Configuration
import org.osmdroid.tileprovider.tilesource.OnlineTileSourceBase
import org.osmdroid.tileprovider.tilesource.TileSourcePolicy
import org.osmdroid.util.MapTileIndex
import org.osmdroid.views.MapView

/**
 * Turns one of our [TileProvider] entries into an osmdroid source. A template
 * source rather than XYTileSource because our palette includes URLs with a
 * query string (the TracesTrack key), which XYTileSource can't express.
 */
private class TemplateTileSource(
    private val provider: TileProvider,
) : OnlineTileSourceBase(
    provider.key,
    0,
    provider.maxNativeZoom,
    provider.tileSize,
    "",
    provider.subdomains.ifEmpty { listOf("") }.toTypedArray(),
    provider.attribution,
    TileSourcePolicy(
        2,
        TileSourcePolicy.FLAG_NO_BULK or
            TileSourcePolicy.FLAG_NO_PREVENTIVE or
            TileSourcePolicy.FLAG_USER_AGENT_MEANINGFUL,
    ),
) {
    override fun getTileURLString(pMapTileIndex: Long): String =
        provider.urlTemplate
            .replace("{s}", if (provider.subdomains.isEmpty()) "" else baseUrl)
            .replace("{z}", MapTileIndex.getZoom(pMapTileIndex).toString())
            .replace("{x}", MapTileIndex.getX(pMapTileIndex).toString())
            .replace("{y}", MapTileIndex.getY(pMapTileIndex).toString())
}

/**
 * osmdroid needs a one-time config; the user agent matters — tile servers
 * (OSM's especially) reject the library's default and hand back 403s.
 */
fun initOsmdroid(context: Context) {
    Configuration.getInstance().apply {
        load(context, PreferenceManager.getDefaultSharedPreferences(context))
        userAgentValue = context.packageName
        osmdroidBasePath = context.getExternalFilesDir(null) ?: context.filesDir
        osmdroidTileCache = osmdroidBasePath.resolve("tiles")
    }
}

fun MapView.applyProvider(provider: TileProvider) {
    setTileSource(TemplateTileSource(provider))
    // Past the provider's native depth osmdroid upscales rather than 404s,
    // matching the web app's maxZoom-above-maxNativeZoom behavior.
    maxZoomLevel = (provider.maxNativeZoom + 3).toDouble()
}
