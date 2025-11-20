"""Google FCM (Firebase Cloud Messaging) integration for Hillview push notifications."""

import asyncio
import logging
import os
from typing import Optional, Dict, Any

import firebase_admin
from firebase_admin import credentials, messaging

logger = logging.getLogger(__name__)

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


async def send_fcm_push(fcm_token: str, title: str, body: str, data: Optional[Dict[str, str]] = None) -> bool:
    """Send FCM notification to device token."""
    if not is_fcm_configured():
        logger.error("FCM not configured")
        return False

    # Remove 'fcm:' prefix if present
    token = fcm_token.replace('fcm:', '') if fcm_token.startswith('fcm:') else fcm_token

    try:
        # Build FCM message with proper deep link
        message = messaging.Message(
            notification=messaging.Notification(
                title=title,
                body=body
            ),
			data={
				'click_action': '/activity'
			},
		#data=data or {},
            android=messaging.AndroidConfig(
                notification=messaging.AndroidNotification(
                    channel_id='hillview_activity_notifications',
					color='#8BC3FA',
					tag='activity',
					#click_action='act=android.intent.action.VIEW',
					sound="",
					priority='default',
					visibility='public',
					notification_count=7
                ),
                # Add deep link data that FCM will use for intent
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

