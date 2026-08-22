package cz.hillview.pip

import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow

/**
 * Float mode: the map floats in a picture-in-picture window over whatever
 * else is on screen — in practice the phone's own camera app, while the
 * external-camera activity records position and heading for stamping those
 * photos afterwards.
 *
 * Why PiP rather than an overlay: a PiP window counts as a VISIBLE activity,
 * so the process keeps every capability a foreground app has — GPS and
 * sensors included — with no foreground service required (researched
 * 2026-08-06, frontend2-capture-backlog.md). It is also the only float that
 * needs no special permission.
 *
 * The hard constraint that shapes the entry point: whoever is TOP evicts
 * lower camera clients, so hillview MUST release its own camera before the
 * phone's camera app can open. Entering float mode therefore switches to the
 * external-camera activity first — the activity that has no camera stream —
 * which makes "release the camera" a consequence of the design rather than a
 * step that can be forgotten.
 */
object PipState {
    private val _inPip = MutableStateFlow(false)

    /** True while the app is rendering into the PiP window. */
    val inPip: StateFlow<Boolean> = _inPip.asStateFlow()

    /** Platform-only: set from the activity's PiP-mode callback. */
    fun setInPip(value: Boolean) {
        _inPip.value = value
    }
}

/** False on devices (and desktop) that cannot float a window. */
expect fun pipSupported(): Boolean

/**
 * Ask the platform to shrink into a PiP window. No-op where unsupported, so
 * callers need no platform branch.
 */
expect fun enterPipMode()

/** Bring the phone's own camera app up, for shooting while the map floats. */
expect fun launchSystemCamera()
