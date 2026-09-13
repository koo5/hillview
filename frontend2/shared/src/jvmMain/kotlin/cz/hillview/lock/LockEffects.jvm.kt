package cz.hillview.lock

import androidx.compose.runtime.Composable

/** A desktop window has no backlight to dim and no gestures to lock out. */
@Composable
actual fun ApplyControlsLock(active: Boolean, options: LockOptions) = Unit
