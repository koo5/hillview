package cz.hillview.map

import androidx.compose.ui.unit.dp

/**
 * Which edges of a panel are the SCREEN's, and which are the app's own split
 * divider.
 *
 * The distinction is the whole point (user-raised, 2026-09-11: "in portrait
 * mode, it's unnecessary to make the same provision for the app's panel
 * divider, because the divider can be grabbed elsewhere"). A control kept
 * clear of a screen edge is kept clear of a mis-swipe that leaves the app or
 * fires a system gesture, and that is worth the space. A control kept clear
 * of the divider is kept clear of nothing: the divider is the app's own, it
 * runs the full width or height of the split, and it can be taken hold of
 * anywhere along it.
 *
 * Getting this wrong costs the middle of the map, which is the part the user
 * came for.
 */
data class PanelEdges(
    val top: Boolean = true,
    val start: Boolean = true,
    val end: Boolean = true,
    val bottom: Boolean = true,
) {
    companion object {
        /** A panel that owns the window: every edge is the screen's. */
        val AllScreen = PanelEdges()

        /**
         * The map panel of the Main split: the bottom half in portrait, the
         * right half in landscape (MainScreen). So the divider is above it
         * in portrait and beside it in landscape, and every other edge is
         * the screen's.
         */
        fun mapPanel(portrait: Boolean): PanelEdges =
            if (portrait) PanelEdges(top = false) else PanelEdges(start = false)

        /**
         * The photo panel of the same split — the mirror image: the top half
         * in portrait, the left half in landscape. So exactly one of the two
         * panels touches the window's top-right corner at a time, and which
         * one it is flips with the orientation.
         */
        fun photoPanel(portrait: Boolean): PanelEdges =
            if (portrait) PanelEdges(bottom = false) else PanelEdges(end = false)
    }

    /**
     * Whether the WINDOW's top-right corner falls inside this panel.
     *
     * That corner is spoken for: the lock button sits in it, above both
     * panels, because it locks the whole app rather than either panel
     * (user, 2026-09-11: "lets maybe just shift the lock button into the
     * top right corner, away from the activity buttons"). A panel that owns
     * the corner has to keep its own controls out of it by
     * [WINDOW_CORNER_RESERVE]; a panel that does not must not waste the
     * space, which is the rule this whole type exists to state.
     */
    val ownsWindowTopEnd: Boolean get() = top && end
}

/**
 * How much of a panel's top-right corner the window's lock button covers.
 *
 * The button is a [androidx.compose.material3.TextButton] in a circle, so
 * its footprint is the Material minimum (58 x 40 dp) plus the 4 dp the
 * floating controls all carry — rounded up, once, here, rather than guessed
 * at in each panel.
 */
val WINDOW_CORNER_RESERVE = 68.dp
