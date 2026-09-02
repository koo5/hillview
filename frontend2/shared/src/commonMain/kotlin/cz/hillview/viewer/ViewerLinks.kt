package cz.hillview.viewer

import cz.hillview.map.PhotoMarker

/**
 * The web app's deep link to a photo — the original's `constructMapUrl`
 * (urlUtils.ts:82-96) exactly: the map at the photo's position, the photo
 * in front by its `<source>-<id>` uid. The share button and the QR code
 * produce this same URL, so it is the one form every reader recognises.
 *
 * This is the way OUT of the viewer to everything the pane deliberately
 * does not do — the zoom view above all (user-decided: inline zoom here,
 * the full thing in the web app).
 *
 * Only server photos have a page: a device photo that has not gone out
 * has nowhere to link to, and the other sources have their own sites.
 */
fun photoWebUrl(webUrl: String, photo: PhotoMarker, mapZoom: Double): String? {
    if (photo.source != "hillview") return null
    val base = webUrl.trimEnd('/')
    return buildString {
        append(base)
        append("/?lat=").append(photo.latitude)
        append("&lon=").append(photo.longitude)
        append("&zoom=").append(mapZoom)
        photo.bearingDeg?.let { append("&bearing=").append(it) }
        append("&photo=").append(encodeUriComponent("hillview-${photo.id}"))
    }
}

/** encodeURIComponent, for the one character set a uid can contain. */
private fun encodeUriComponent(s: String): String = buildString {
    for (ch in s) {
        if (ch.isLetterOrDigit() || ch in "-_.!~*'()") append(ch)
        else for (b in ch.toString().encodeToByteArray()) {
            append('%').append(((b.toInt() and 0xFF) or 0x100).toString(16).substring(1).uppercase())
        }
    }
}
