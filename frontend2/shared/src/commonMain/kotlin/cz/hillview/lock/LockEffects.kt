package cz.hillview.lock

import androidx.compose.runtime.Composable

/**
 * What locking does to the WINDOW, which is the platform's business.
 *
 * Keeping the screen awake is unconditional and not a setting: without it
 * the display sleeps, the activity stops, CameraX unbinds and the run this
 * protects is over. Everything in [options] is the user's to choose.
 *
 * Every effect is undone when [active] goes false or the composable leaves,
 * including on the way out through a crash-free process death — a phone left
 * pinned and dimmed by an app that is no longer running would be a genuinely
 * unpleasant thing to hand someone.
 */
@Composable
expect fun ApplyControlsLock(active: Boolean, options: LockOptions)
