package cz.hillview.settings

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNull
import kotlin.test.assertTrue

/**
 * The consent chain around auto-upload. These rules are the privacy story,
 * so they are pinned as data-level tests rather than left to the UI:
 * nothing leaves the device without an explicit licence choice AND an
 * explicit auto-upload opt-in, in that order.
 */
class UploadConsentTest {

    @Test
    fun aFreshInstallHasAcceptedNothing() {
        val defaults = defaultUploadSettings("https://example.test/api")
        // Null licence is "not accepted" — the shared upload stack refuses
        // to upload in that state, so this default is load-bearing, not
        // cosmetic. Defaulting to a licence would accept it on the user's
        // behalf.
        assertNull(defaults.license)
        assertFalse(defaults.autoUploadEnabled)
        // But the prompt may ask, until told never.
        assertTrue(defaults.autoUploadPromptEnabled)
    }

    @Test
    fun theLicenceVocabularyIsTheBackends() {
        // user_routes.ALLOWED_LICENSES — a licence string the backend does
        // not know is an upload rejection later.
        assertEquals(listOf("ccbysa4+osm", "full1"), ALLOWED_LICENSES)
    }
}
