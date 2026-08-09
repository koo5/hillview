package cz.hillview.core.permissions

import androidx.compose.runtime.Composable

/**
 * Requests notification permission where the platform has one (Android 13+
 * POST_NOTIFICATIONS — upload progress/auth-expired notifications); no-op
 * elsewhere. Invoke at the moment notifications become relevant, i.e. when
 * the user enables auto-upload.
 */
@Composable
expect fun rememberNotificationPermissionRequester(): () -> Unit
