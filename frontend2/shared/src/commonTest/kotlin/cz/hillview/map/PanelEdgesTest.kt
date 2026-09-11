package cz.hillview.map

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue

/**
 * Where the map panel actually meets the screen. Getting this wrong spends
 * the middle of the map on a gutter against nothing.
 */
class PanelEdgesTest {

    @Test
    fun inPortraitOnlyTheTopIsTheApp() {
        val edges = PanelEdges.mapPanel(portrait = true)
        assertFalse(edges.top, "the divider is above the map panel in portrait")
        assertTrue(edges.start)
        assertTrue(edges.end)
        assertTrue(edges.bottom)
    }

    @Test
    fun inLandscapeOnlyTheStartIsTheApp() {
        val edges = PanelEdges.mapPanel(portrait = false)
        assertTrue(edges.top, "the status bar is above the map panel in landscape")
        assertFalse(edges.start, "the divider is beside the map panel in landscape")
        assertTrue(edges.end)
        assertTrue(edges.bottom)
    }

    /** Exactly one edge is ever the app's: the split has one divider. */
    @Test
    fun oneEdgeIsTheDividerAndTheRestAreTheScreen() {
        for (portrait in listOf(true, false)) {
            val e = PanelEdges.mapPanel(portrait)
            assertEquals(
                1,
                listOf(e.top, e.start, e.end, e.bottom).count { !it },
                "portrait=$portrait",
            )
        }
    }

    @Test
    fun aPanelThatOwnsTheWindowHasNoDivider() {
        val e = PanelEdges.AllScreen
        assertTrue(e.top && e.start && e.end && e.bottom)
    }
}
