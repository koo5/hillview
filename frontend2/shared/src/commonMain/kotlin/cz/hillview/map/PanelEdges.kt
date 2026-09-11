package cz.hillview.map

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
    }
}
