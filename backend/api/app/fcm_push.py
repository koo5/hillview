"""Google FCM (Firebase Cloud Messaging) integration for Hillview push notifications."""

import asyncio
import logging
import os
from typing import Optional, Dict, Any, List

import firebase_admin
from firebase_admin import credentials, messaging

logger = logging.getLogger(__name__)

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


async def send_fcm_push(fcm_token: str, title: str, body: str, route: Optional[str] = None) -> bool:
    """Send FCM notification to device token."""
    if not is_fcm_configured():
        logger.error("FCM not configured")
        return False

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
            return True
        else:
            error = batch_response.responses[0].exception
            logger.error(f"FCM failed: {error}")
            return False

    except Exception as e:
        logger.error(f"FCM error: {e}")
        return False


async def send_fcm_batch(
    fcm_tokens: List[str],
    title: str,
    body: str,
    route: Optional[str] = None
) -> Dict[str, int]:
    """Send FCM notification to multiple device tokens in batch.

    FCM supports up to 500 messages per batch. This function handles
    splitting larger lists into multiple batches.

    Returns dict with counts: {'success': int, 'failure': int}
    """
    if not is_fcm_configured():
        logger.error("FCM not configured")
        return {'success': 0, 'failure': len(fcm_tokens)}

    if not fcm_tokens:
        return {'success': 0, 'failure': 0}

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

    # Send in batches of FCM_BATCH_SIZE
    for i in range(0, len(messages), FCM_BATCH_SIZE):
        batch = messages[i:i + FCM_BATCH_SIZE]
        try:
            batch_response = await messaging.send_each_async(batch)
            total_success += batch_response.success_count
            total_failure += batch_response.failure_count

            # Log any failures
            for idx, response in enumerate(batch_response.responses):
                if not response.success:
                    logger.warning(f"FCM batch item {i + idx} failed: {response.exception}")

        except Exception as e:
            logger.error(f"FCM batch error: {e}")
            total_failure += len(batch)

    logger.info(f"FCM batch sent: {total_success} success, {total_failure} failure")
    return {'success': total_success, 'failure': total_failure}

