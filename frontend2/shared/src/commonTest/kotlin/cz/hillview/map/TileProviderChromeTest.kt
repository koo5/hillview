package cz.hillview.map

import kotlin.test.Test
import kotlin.test.assertEquals

/**
 * What the map's floating controls have to wear over each basemap.
 *
 * The classification is data rather than a runtime guess, so this is where it
 * is checked. The rule it encodes: chrome contrast is against the TILES, so it
 * follows the provider — never the app's light/dark setting, which is the
 * coupling that produced black-on-black.
 */
class TileProviderChromeTest {

    private fun chromeOf(key: String) =
        TILE_PROVIDERS.first { it.key == key }.chrome

    @Test
    fun ordinaryCartographyIsLight() {
        // The default, and it must stay the default: a provider added without
        // thinking about chrome should get the treatment that suits the pale
        // paper nearly all of them serve.
        assertEquals(MapChrome.OnLight, chromeOf("OpenStreetMap.Mapnik"))
        assertEquals(MapChrome.OnLight, chromeOf("OpenTopoMap"))
        assertEquals(MapChrome.OnLight, chromeOf("tiles.ueueeu.eu"))
        assertEquals(MapChrome.OnLight, TileProvider("x", "x", "u", "a", 19).chrome)
    }

    @Test
    fun theDarkBasemapAsksForDarkChrome() {
        assertEquals(MapChrome.OnDark, chromeOf("CartoDB.DarkMatter"))
    }

    @Test
    fun aerialImageryIsNeitherAndSaysSo() {
        // Snow and forest in one screen: no tone is safe, so the panels go
        // opaque instead of picking a side.
        assertEquals(MapChrome.OnMixed, chromeOf("oi.jj.internal"))
    }
}
