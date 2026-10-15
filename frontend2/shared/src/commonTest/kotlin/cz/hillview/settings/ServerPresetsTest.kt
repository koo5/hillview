package cz.hillview.settings

import kotlin.test.Test
import kotlin.test.assertEquals

/**
 * The LAN presets cross a language wall: scripts/host_profiles.py prints
 * them, Gradle carries the text into BuildConfig untouched, and this decodes
 * it. The fixtures are that script's output verbatim.
 */
class ServerPresetsTest {

    @Test
    fun decodesWhatHostProfilesPrints() {
        assertEquals(
            listOf(ServerPreset("jj-raw", "http://10.0.0.24:8055/api")),
            parseServerPresets("""[{"label": "jj-raw", "apiUrl": "http://10.0.0.24:8055/api"}]"""),
        )
    }

    @Test
    fun noHostsTomlMeansNoLanPresets() {
        assertEquals(emptyList(), parseServerPresets("[]"))
    }
}
