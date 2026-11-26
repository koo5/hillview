package cz.hillview.capture

import androidx.compose.runtime.Composable

/** See [CaptureSoundPreview]; null where the platform has no capture. */
@Composable
expect fun rememberCaptureSoundPreview(): CaptureSoundPreview?
