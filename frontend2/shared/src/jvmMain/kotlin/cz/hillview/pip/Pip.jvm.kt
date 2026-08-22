package cz.hillview.pip

/** Desktop has no picture-in-picture and no camera app to float over. */
actual fun pipSupported(): Boolean = false

actual fun enterPipMode() {}

actual fun launchSystemCamera() {}
