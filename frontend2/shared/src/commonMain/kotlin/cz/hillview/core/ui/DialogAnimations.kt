package cz.hillview.core.ui

import androidx.compose.runtime.Composable

/**
 * Call at the top of a dialog's content to strip the platform
 * window-appearance animation — the stock Android dialog zoom/fade reads
 * as lag on every open (phone-in-hand feedback). Compose dialogs ignore
 * the activity theme's dialog styles, so this reaches into the dialog's
 * own window; on desktop there is no window animation to strip.
 */
@Composable
expect fun InstantDialogWindow()
