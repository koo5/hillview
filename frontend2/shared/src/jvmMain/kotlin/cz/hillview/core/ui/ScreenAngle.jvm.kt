package cz.hillview.core.ui

import androidx.compose.runtime.Composable

/** A desktop window does not rotate. */
@Composable
actual fun rememberScreenAngleDeg(): Int = 0
