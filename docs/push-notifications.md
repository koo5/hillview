# Push notifications

How push notifications flow through the system — what the backend sends,
how the Android client displays them, and the knobs that control all of it.

## High-level flow

1. Backend stores a `Notification` row (and/or sends an FCM / UnifiedPush
   message) via one of the push paths in `backend/api/app/push_notifications.py`.
2. Android receives the push:
   - FCM → `FcmDirectService.onMessageReceived` (firebase-messaging)
   - UnifiedPush → `PushServiceImpl.onMessage` (org.unifiedpush.android.connector)
3. Depending on state (foreground / backgrounded / freshly-spawned),
   either Android auto-displays the `notification` payload OR our code
   fetches from `/api/notifications/recent` and displays it via
   `NotificationManager.displayNotifications`.
4. Tap → Android fires the `contentIntent` → app launches → reads
   `click_action` intent extra → routes to the target page.

## Channels

`NotificationHelper.createNotificationChannels` registers three channels
at plugin init time. Channel ids are contractual between backend and
client; if a mismatch happens Android silently falls back to
`fcm_fallback_notification_channel` and all the per-channel settings
(importance, vibration, badge, visibility in app settings) are lost.

| Channel id                        | Importance | Description                                    |
| --------------------------------- | ---------- | ---------------------------------------------- |
| `auth_notifications`              | HIGH       | "Login Required" / session-expired prompts.    |
| `upload_notifications`            | DEFAULT    | Photo-upload status (legacy; today the WorkManager foreground uses its own channel `photo_upload_foreground`). |
| `hillview_activity_notifications` | DEFAULT    | Activity broadcasts from the backend over FCM — the id the server puts on every `AndroidNotification` in `fcm_push.py`. |

If you change a channel id on either side, change both.

## Dedup rule (FCM foreground vs. background)

FCM messages in this app carry both `notification` and `data` payloads.
That causes duplicate display if both paths run:

- **Foreground**: Android does NOT auto-display; `onMessageReceived`
  runs; our code posts from `NotificationManager`. One notification.
- **Background (process alive, activity stopped)**: Android
  auto-displays from the `notification` payload; `onMessageReceived` also
  fires. Without a dedup check, we'd post a second duplicate.
  `FcmDirectService.onMessageReceived` checks
  `ProcessLifecycleOwner.get().lifecycle.currentState.isAtLeast(STARTED)`
  and — when the message has a `notification` payload AND the app isn't
  foreground — returns early. One notification.
- **Swiped-from-recents (process killed, service cold-starts)**:
  Firebase cold-starts `FirebaseMessagingService`, calls
  `onMessageReceived`, and does NOT auto-display the notification
  payload (auto-display requires the app process to already be alive).
  Our code posts. One notification.
- **Force-stopped (`am force-stop`, Settings → Force stop)**: Android
  refuses to deliver any intent, including FCM. Firebase queues. User
  must re-launch the app to unblock. Don't test delivery in this state.

## Stale-token cleanup

FCM tokens die when the app is uninstalled, the user clears data, or
the token is issued to a different Firebase project. The
send-batch code (`fcm_push.py:send_fcm_batch`) inspects each per-message
response and returns the list of tokens Firebase flagged as dead;
`push_notifications.py:_unregister_stale_endpoints` deletes the matching
`push_registrations` rows so the next broadcast doesn't waste a send on
them. Criteria for "stale":

- `messaging.UnregisteredError`
- `messaging.SenderIdMismatchError`
- `exceptions.NotFoundError`
- `exceptions.InvalidArgumentError` where the message says the token
  isn't a valid FCM token (narrowed to avoid false positives — that
  exception class covers many unrelated 400-level problems)

Same logic runs from the single-send path (`send_push_to_client`).

## Outgoing-push toggle (`push_toggle`)

`backend/api/app/push_toggle.py` holds a single boolean that gates every
outbound FCM and UnifiedPush call:

- Default **OFF** in `DEV_MODE`, **ON** otherwise.
- `POST /api/internal/debug/push-enabled {enabled: true|false}` flips at
  runtime.
- `/api/debug/recreate-test-users` and `/api/debug/clear-database` reset
  to the `DEV_MODE`-driven default — so any test that opted in doesn't
  leak the setting into the next test run.

Purpose: ordinary dev / test workflows shouldn't hammer real Firebase or
UnifiedPush distributors just by exercising unrelated code paths. Tests
that genuinely need delivery flip the toggle on, fire, and rely on
`recreate-test-users` to reset.

## Server-side session invalidation (`force-logout-user`)

`POST /api/internal/debug/force-logout-user {username}` marks the user
as force-logged-out in process memory. `get_current_user` and
`/auth/refresh` both consult this flag and return 401 for the user's
tokens — identical to blacklist semantics without needing to know the
tokens. Next successful password login clears the flag automatically.

Use cases:
- Reproducing the "session expired" path in prod without waiting on
  token expiry.
- Driving the Android "Login Required" notification flow from tests
  (see `tests-appium/specs/relogin-notification.test.ts`).

## Channel / tag reference

Visible in `dumpsys notification --noredact` after a delivery:

```
key=0|cz.hillviedev|<id>|<tag>|<uid>
```

- `tag=activity` → Android's auto-display from the FCM `notification`
  payload (backend sets `tag='activity'` via `AndroidNotification`).
- `tag=null` (or empty) → our `NotificationManager` posted it; `id` is
  either a backend `Notification.id` (from `displayNotifications`) or
  a `System.currentTimeMillis().toInt()` (from `displaySingleNotification`).
- `channel=fcm_fallback_notification_channel` → the channel id the
  backend sent didn't exist on the device when the message arrived
  (bug to investigate, not a regular occurrence after the activity
  channel registration landed).
