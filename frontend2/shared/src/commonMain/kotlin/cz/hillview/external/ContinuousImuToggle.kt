package cz.hillview.external

import androidx.compose.runtime.Composable

/**
 * The continuous-inertial-logging switch for the external-camera pane.
 *
 * An expect/actual rather than plain state in the screen, for the same reason
 * `pipSupported()` is one: the setting lives in Android `SharedPreferences` and
 * is read by a foreground SERVICE as well as this pane, neither of which
 * commonMain can see. See `ExternalImuSettings` (androidMain) for why both
 * readers have to agree.
 *
 * Renders nothing on platforms with no such logging, which is every platform but
 * Android — the same convention `pipSupported()` uses to stay out of the way.
 */
@Composable
expect fun ContinuousImuToggle()
