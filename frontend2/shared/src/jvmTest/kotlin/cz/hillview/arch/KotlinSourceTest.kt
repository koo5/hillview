package cz.hillview.arch

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue

class KotlinSourceTest {

    @Test
    fun proseIsNotCode() {
        val src = """
            // never register an OrientationEventListener here
            /* nor here: OrientationEventListener */
            /** and not in KDoc either: OrientationEventListener */
            val x = 1
        """.trimIndent()
        assertFalse(kotlinCodeOnly(src).contains("OrientationEventListener"))
        assertTrue(kotlinCodeOnly(src).contains("val x = 1"))
    }

    @Test
    fun realCodeSurvives() {
        val src = "class A : OrientationEventListener(context) // a real one"
        assertTrue(kotlinCodeOnly(src).contains("OrientationEventListener(context)"))
    }

    @Test
    fun aUrlInAStringDoesNotEatTheRestOfTheLine() {
        val src = """val u = "https://x/y"; val z = GeoEngine.get(c)"""
        assertTrue(kotlinCodeOnly(src).contains("GeoEngine.get("))
    }

    @Test
    fun stringContentsAreBlanked() {
        val src = """Log.d(TAG, "OrientationEventListener re-armed")"""
        assertFalse(kotlinCodeOnly(src).contains("OrientationEventListener"))
        assertTrue(kotlinCodeOnly(src).contains("Log.d(TAG, \"\")"))
    }

    @Test
    fun rawStringsAndNestedBlockCommentsClose() {
        val src = """
            val q = ${'"'}${'"'}${'"'} /* not a comment */ ${'"'}${'"'}${'"'}
            /* outer /* inner */ still comment: GeoEngine.get( */
            val after = GeoEngine.get(c)
        """.trimIndent()
        val code = kotlinCodeOnly(src)
        assertTrue(code.contains("val after = GeoEngine.get(c)"))
        assertEquals(1, Regex("GeoEngine\\.get\\(").findAll(code).count())
    }
}
