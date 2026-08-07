package cz.hillview.map

/**
 * Raster tile sources, ported from the Tauri app's tileProviders.ts (same
 * keys, same display names, same default) so a user's choice means the same
 * thing in both apps.
 *
 * [urlTemplate] uses {z}/{x}/{y}, and {s} where the provider wants a
 * subdomain from [subdomains]. [maxNativeZoom] is the deepest zoom the
 * provider actually serves; the map may zoom past it by upscaling tiles.
 */
data class TileProvider(
    val key: String,
    val displayName: String,
    val urlTemplate: String,
    val attribution: String,
    val maxNativeZoom: Int,
    val subdomains: List<String> = emptyList(),
    val tileSize: Int = 256,
    /** Hidden from the picker outside dev builds, like VITE_DEV_MODE gates it there. */
    val devOnly: Boolean = false,
)

private const val OSM_ATTRIBUTION = "© OpenStreetMap contributors"

// Frontend tile keys are industry-standard practice and referrer-restricted
// at the provider's console; same key the Tauri app ships.
private const val TRACESTRACK_KEY = "262a38b16c187cfca361f1776efb9421"

val TILE_PROVIDERS: List<TileProvider> = listOf(
    TileProvider(
        key = "tiles.ueueeu.eu",
        displayName = "Hillview (CZ)",
        urlTemplate = "https://tiles.ueueeu.eu/tile/{z}/{x}/{y}.png",
        attribution = OSM_ATTRIBUTION,
        maxNativeZoom = 20,
    ),
    TileProvider(
        key = "tiles4.ueueeu.eu",
        displayName = "Hillview (world)",
        urlTemplate = "https://tiles4.ueueeu.eu/tile/{z}/{x}/{y}.png",
        attribution = OSM_ATTRIBUTION,
        maxNativeZoom = 20,
    ),
    TileProvider(
        key = "OpenStreetMap.Mapnik",
        displayName = "OpenStreetMap",
        urlTemplate = "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
        attribution = OSM_ATTRIBUTION,
        maxNativeZoom = 19,
    ),
    TileProvider(
        key = "OpenTopoMap",
        displayName = "OpenTopoMap",
        urlTemplate = "https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png",
        attribution = "© OpenTopoMap (CC-BY-SA), $OSM_ATTRIBUTION",
        maxNativeZoom = 17,
        subdomains = listOf("a", "b", "c"),
    ),
    TileProvider(
        key = "CyclOSM",
        displayName = "CyclOSM (Cycling)",
        urlTemplate = "https://{s}.tile-cyclosm.openstreetmap.fr/cyclosm/{z}/{x}/{y}.png",
        attribution = "CyclOSM, $OSM_ATTRIBUTION",
        maxNativeZoom = 19,
        subdomains = listOf("a", "b", "c"),
    ),
    TileProvider(
        key = "CartoDB.DarkMatter",
        displayName = "CartoDB Dark",
        urlTemplate = "https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png",
        attribution = "© CARTO, $OSM_ATTRIBUTION",
        maxNativeZoom = 20,
        subdomains = listOf("a", "b", "c", "d"),
    ),
    TileProvider(
        key = "TracesTrack.Topo",
        displayName = "TracesTrack Topographic",
        urlTemplate = "https://tile.tracestrack.com/_/{z}/{x}/{y}.webp?key=$TRACESTRACK_KEY",
        attribution = "© TracesTrack, $OSM_ATTRIBUTION",
        maxNativeZoom = 19,
    ),
    TileProvider(
        key = "oi.jj.internal",
        displayName = "Ortofoto ČR (DEV)",
        urlTemplate = "http://oi.jj.internal:8080/wmts/oi/webmercator/{z}/{x}/{y}.png",
        attribution = "Ortofoto ČR © ČÚZK, CC BY 4.0",
        maxNativeZoom = 20,
        devOnly = true,
    ),
)

/** Same default as the Tauri app. */
const val DEFAULT_TILE_PROVIDER = "tiles4.ueueeu.eu"

fun tileProvider(key: String?): TileProvider =
    TILE_PROVIDERS.firstOrNull { it.key == key }
        ?: TILE_PROVIDERS.first { it.key == DEFAULT_TILE_PROVIDER }
