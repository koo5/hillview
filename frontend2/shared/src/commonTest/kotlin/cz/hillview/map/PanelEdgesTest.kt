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
    fun thePhotoPanelIsTheMirrorImage() {
        val portrait = PanelEdges.photoPanel(portrait = true)
        assertFalse(portrait.bottom, "the divider is below the photo panel in portrait")
        assertTrue(portrait.top && portrait.start && portrait.end)

        val landscape = PanelEdges.photoPanel(portrait = false)
        assertFalse(landscape.end, "the divider is beside the photo panel in landscape")
        assertTrue(landscape.top && landscape.start && landscape.bottom)
    }

    /**
     * The window's top-right corner is the lock button's, so exactly one
     * panel has to yield it — and it flips with the orientation. Two would
     * mean a hole in the wrong pane; none would mean the button sits on top
     * of a control.
     */
    @Test
    fun exactlyOnePanelOwnsTheWindowsTopRightCorner() {
        for (portrait in listOf(true, false)) {
            val owners = listOf(
                PanelEdges.mapPanel(portrait),
                PanelEdges.photoPanel(portrait),
            ).count { it.ownsWindowTopEnd }
            assertEquals(1, owners, "portrait=$portrait")
        }
    }

    @Test
    fun inPortraitTheCornerIsThePhotoPanelsAndInLandscapeTheMaps() {
        assertTrue(PanelEdges.photoPanel(portrait = true).ownsWindowTopEnd)
        assertFalse(PanelEdges.mapPanel(portrait = true).ownsWindowTopEnd)
        assertTrue(PanelEdges.mapPanel(portrait = false).ownsWindowTopEnd)
        assertFalse(PanelEdges.photoPanel(portrait = false).ownsWindowTopEnd)
    }

    @Test
    fun aPanelThatOwnsTheWindowHasNoDivider() {
        val e = PanelEdges.AllScreen
        assertTrue(e.top && e.start && e.end && e.bottom)
        assertTrue(e.ownsWindowTopEnd, "and it is under the lock button too")
    }
}
