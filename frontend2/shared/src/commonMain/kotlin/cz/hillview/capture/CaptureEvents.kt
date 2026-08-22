package cz.hillview.capture

import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.SharedFlow
import kotlinx.coroutines.flow.asSharedFlow

/**
 * "A photo was captured and is now in the database."
 *
 * The map's markers are refetched on viewport change, so without this a photo
 * you just took does not appear until you happen to pan — and neither does it
 * enter the viewer's ring, since the ring is culled from those same markers.
 *
 * The Tauri app solves the same visible problem with PLACEHOLDER MARKERS
 * (placeholderInjector.ts): an optimistic photo with the id the real one will
 * get, injected into photosInArea/photosInRange at the shutter, re-embedded
 * into every subsequent update, and removed when the real row finally
 * arrives. It needs all that because a capture there crosses the JS/native
 * boundary: the file is written by native code, the row appears later, and
 * the worker's photosUpdate later still, so there is a long window with
 * nothing to draw.
 *
 * Here the row is written synchronously in the capture path, so the window is
 * the shutter itself. What is missing is not an optimistic marker but the
 * news that the database changed — which is all this carries. If we ever want
 * a marker DURING the shutter, placeholders become the answer again.
 *
 * REVISIT WHEN OPTIMISING FOR BATTERY. Each event costs a marker refresh, and
 * in interval mode that is one per photo — a database query every couple of
 * seconds, plus the recomposition it causes, for the whole of a shoot. The
 * placeholder approach the original takes is cheaper precisely because it
 * INJECTS rather than asks: no query, no refetch, no round trip. Options when
 * that day comes, roughly in order of cost: refresh only the device source
 * rather than the composite; conflate events so a burst costs one refresh;
 * or adopt placeholders after all and let the periodic refetch reconcile.
 */
class CaptureEvents {
    private val _captured = MutableSharedFlow<String>(extraBufferCapacity = 8)

    /** Photo ids, as their rows land. */
    val captured: SharedFlow<String> = _captured.asSharedFlow()

    /** Called once the row exists — not when the shutter fires. */
    fun photoStored(photoId: String) {
        _captured.tryEmit(photoId)
    }
}
