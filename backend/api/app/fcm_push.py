"""Google FCM (Firebase Cloud Messaging) integration for Hillview push notifications."""

import logging
import os
from typing import Optional, Dict, List

import firebase_admin
from firebase_admin import exceptions as firebase_exceptions
from firebase_admin import messaging

import push_toggle

logger = logging.getLogger(__name__)


def _is_stale_token_error(exc: Exception) -> bool:
    """True if an FCM per-message exception indicates the token should be
    deleted from our store.

    Drop the token on:
    - UnregisteredError: app uninstalled / cleared / token explicitly
      deleted. Permanently dead.
    - SenderIdMismatchError: token was issued to a different Firebase
      project; ours can't ever use it.
    - InvalidArgumentError with a token-shape complaint (e.g., "The
      registration token is not a valid FCM registration token").
      The same class covers many unrelated 400-level issues, so we
      additionally match on the message text to avoid deleting tokens
      over transient/logic bugs.
    - NotFoundError ("Requested entity was not found"): some older SDK
      versions and HTTP-API failure modes surface stale tokens this way.

    Keep the token (transient / retriable) on:
    - QuotaExceededError
    - UnavailableError
    - ThirdPartyAuthError (auth to APNs/WebPush, not our problem)
    - everything else
    """
    if isinstance(exc, (messaging.UnregisteredError, messaging.SenderIdMismatchError)):
        return True
    if isinstance(exc, firebase_exceptions.NotFoundError):
        return True
    if isinstance(exc, firebase_exceptions.InvalidArgumentError):
        msg = str(exc).lower() if exc else ""
        # InvalidArgumentError covers many 400-level issues unrelated to
        # the token itself (e.g., bad payload). Only delete on messages
        # that specifically say the token is no good.
        if "not a valid fcm registration token" in msg or "registration token is not valid" in msg:
            return True
    return False

# FCM batch limit
FCM_BATCH_SIZE = 500

# Firebase app instance
firebase_app = None


class FCMError(Exception):
    """Custom exception for FCM-related errors."""
    pass


def init():
    """Initialize Firebase app with automatic credential detection."""
    global firebase_app

    if firebase_app is not None:
        return

    project_id = os.getenv('FIREBASE_PROJECT_ID')
    if not project_id:
        logger.warning("FIREBASE_PROJECT_ID not set - FCM disabled")
        return

    try:
        # Firebase Admin SDK automatically picks up GOOGLE_APPLICATION_CREDENTIALS
        firebase_app = firebase_admin.initialize_app()
        logger.info(f"Firebase initialized successfully for project: {project_id}")
    except Exception as e:
        logger.error(f"Failed to initialize Firebase: {e}")
        firebase_app = None


def is_fcm_configured() -> bool:
    """Check if FCM is properly configured."""
    return firebase_app is not None


async def send_fcm_push(fcm_token: str, title: str, body: str, route: Optional[str] = None) -> Dict[str, object]:
    """Send FCM notification to a single device token.

    Returns {
        'success': bool,
        'stale': bool,   # True if the token should be unregistered
    }
    """
    if not push_toggle.is_enabled():
        logger.info("FCM send skipped: outgoing push disabled (push_toggle)")
        return {'success': False, 'stale': False}
    if not is_fcm_configured():
        logger.error("FCM not configured")
        return {'success': False, 'stale': False}

    # Remove 'fcm:' prefix if present
    token = fcm_token.replace('fcm:', '') if fcm_token.startswith('fcm:') else fcm_token

    try:
        # Build data payload with route for click handling
        data = {}
        if route:
            data['click_action'] = route

        message = messaging.Message(
            notification=messaging.Notification(
                title=title,
                body=body
            ),
            data=data,
            android=messaging.AndroidConfig(
                notification=messaging.AndroidNotification(
                    channel_id='hillview_activity_notifications',
                    color='#8BC3FA',
                    tag='activity',
                    sound="",
                    priority='default',
                    visibility='public',
                    notification_count=7
                ),
            ),
            token=token
        )

        #logger.info(f"Sending FCM to {token[:20]}...")

        # Use send_each_async with a single message list
        batch_response = await messaging.send_each_async([message])

        if batch_response.success_count > 0:
            logger.info(f"FCM sent successfully: {batch_response.responses[0].message_id}")
            return {'success': True, 'stale': False}

        error = batch_response.responses[0].exception
        stale = _is_stale_token_error(error)
        logger.error(f"FCM failed: {error}" + (" (stale token)" if stale else ""))
        return {'success': False, 'stale': stale}

    except Exception as e:
        logger.error(f"FCM error: {e}")
        return {'success': False, 'stale': False}


async def send_fcm_batch(
    fcm_tokens: List[str],
    title: str,
    body: str,
    route: Optional[str] = None
) -> Dict[str, object]:
    """Send FCM notification to multiple device tokens in batch.

    FCM supports up to 500 messages per batch. This function handles
    splitting larger lists into multiple batches.

    Returns {
        'success': int,
        'failure': int,
        'stale_tokens': List[str],   # original fcm:<...> strings the
                                     # caller should remove from storage
    }
    """
    if not push_toggle.is_enabled():
        logger.info(f"FCM batch skipped: outgoing push disabled (push_toggle); would have sent {len(fcm_tokens)}")
        return {'success': 0, 'failure': 0, 'stale_tokens': []}
    if not is_fcm_configured():
        logger.error("FCM not configured")
        return {'success': 0, 'failure': len(fcm_tokens), 'stale_tokens': []}

    if not fcm_tokens:
        return {'success': 0, 'failure': 0, 'stale_tokens': []}

    # Build data payload
    data = {}
    if route:
        data['click_action'] = route

    # Build messages for all tokens
    messages = []
    for fcm_token in fcm_tokens:
        token = fcm_token.replace('fcm:', '') if fcm_token.startswith('fcm:') else fcm_token
        messages.append(messaging.Message(
            notification=messaging.Notification(
                title=title,
                body=body
            ),
            data=data,
            android=messaging.AndroidConfig(
                notification=messaging.AndroidNotification(
                    channel_id='hillview_activity_notifications',
                    color='#8BC3FA',
                    tag='activity',
                    sound="",
                    priority='default',
                    visibility='public',
                ),
            ),
            token=token
        ))

    total_success = 0
    total_failure = 0
    stale_tokens: List[str] = []  # original "fcm:<token>" strings to be unregistered

    # Send in batches of FCM_BATCH_SIZE
    for i in range(0, len(messages), FCM_BATCH_SIZE):
        batch = messages[i:i + FCM_BATCH_SIZE]
        try:
            batch_response = await messaging.send_each_async(batch)
            total_success += batch_response.success_count
            total_failure += batch_response.failure_count

            for idx, response in enumerate(batch_response.responses):
                if not response.success:
                    exc = response.exception
                    logger.warning(f"FCM batch item {i + idx} failed: {exc}")
                    if _is_stale_token_error(exc):
                        stale_tokens.append(fcm_tokens[i + idx])

        except Exception as e:
            logger.error(f"FCM batch error: {e}")
            total_failure += len(batch)

    logger.info(
        f"FCM batch sent: {total_success} success, {total_failure} failure"
        + (f", {len(stale_tokens)} stale (to be unregistered)" if stale_tokens else "")
    )
    return {'success': total_success, 'failure': total_failure, 'stale_tokens': stale_tokens}

