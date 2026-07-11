# Auth state machine (Android / Tauri)

Who holds auth state, how the copies stay consistent, and the invariants any
auth change must preserve. Written after a class of bugs where the WebView kept
showing "authenticated" against a dead session; the structure below is designed
to make that unrepresentable. Web (non-Tauri) is simpler — `webTokenManager.ts`
owns tokens in JS directly, so truth and display live in one layer — and is not
covered here.

## The three copies of "is this session alive"

| Layer | State | Role |
|---|---|---|
| Backend | session row (`sid`), spent-refresh `jti` set | truth |
| Kotlin (`AuthenticationManager`) | SharedPreferences `hillview_auth`: access + refresh token, expiries, session-expired flag | local cache of truth; **sole owner of tokens on-device** |
| WebView JS (`auth` store) | `is_authenticated`, `user` | display cache of the Kotlin state — must never outlive it |

Several `AuthenticationManager` instances exist in one process (WebView plugin,
upload worker, push manager, notifications). They share the SharedPreferences
store; anything cross-instance therefore lives in the companion object: the
`refreshMutex` (serializes refreshes so a single-use refresh token is never
presented twice — strict rotation treats a replay as theft and revokes the
session) and the `onSessionExpired` callback.

## Session death — the single choke point

Every path that concludes "this session cannot continue" calls
`AuthenticationManager.sessionExpired(reason)`. Its four effects are atomic in
the sense that no caller can pick a subset:

- tokens cleared (native logged out)
- `session_expired_at` + reason persisted in SharedPreferences (survives
  process death)
- "Login Required" system notification shown (tapping it deep-links to
  `/login` via the `click_action` launch-intent extra)
- `onSessionExpired` fired → plugin queues a durable-ish `auth-expired`
  message for the WebView poller

Death triggers, exhaustively:

- refresh returns **401** (`performTokenRefresh`) — server rejected the
  refresh token: rotation-theft revocation, force-logout, backend redeploy
  that invalidated sessions, refresh-token expiry server-side
- access token rejected and **no refresh token** stored (`forceRefreshToken`)
- access token **expired** locally and no refresh token stored
  (`refreshLocked`; the proactive-renewal variant with a still-valid access
  token only warns — some login flows legitimately store no refresh token)

Not death: refresh 5xx / timeout / network error (transient — session kept;
see `native-*-keeps-session` specs), and voluntary logout (JS calls
`clear_auth_token` — the user chose this, nothing to surface).

The flag is cleared by exactly two things: re-login (`storeAuthToken`
supersedes the death) and consumption by the JS reconciler after it has
surfaced the expiry. Deliberately NOT by `clear_auth_token`: the lockstep
logout funnels through it, and clearing there would erase the evidence before
it's surfaced when the process dies mid-logout.

## Keeping the JS display cache honest

Two mechanisms, deliberately redundant:

**Edge-triggered (fast path)** — the `auth-expired` queue message, polled by
`KotlinMessageQueue` every ~100 ms. Delivers within a beat while the WebView is
alive and polling. But it lives in plugin-instance memory: process death, or a
backgrounded WebView with throttled timers, can lose it. It is a latency
optimization, not the correctness mechanism.

**Level-triggered (correctness)** — `AndroidTokenManager.reconcileSessionState`
asks native for a snapshot (`cmd: get_session_state` → tokens present?
persisted expired flag?) and corrects the JS store to match:

- native expired flag set → surface an in-app alert, log out if JS still
  thinks it's authenticated (logout navigates to `/login`), consume the flag
- JS authenticated but native holds no tokens at all → log out quietly

Runs at startup (after the auth store's initial check settles), on every
return to foreground (`visibilitychange`), and after a forced refresh comes
back empty (post-401). Throttled to one pass per 5 s.

Why the level trigger is necessary and not just belt-and-braces: after native
clears tokens, every WebView request goes out token-less, and `http.ts`
**deliberately** does not log out on 401 responses to token-less requests
(that would nuke sessions over unauthenticated endpoints). Most Hillview
browsing is unauthenticated map traffic anyway — so without reconciliation
there is no organic event that would ever correct a stale "authenticated" UI.

## Invariants

- JS shows authenticated ⇒ native holds tokens it still believes in. Enforced
  by the reconciler; bounded staleness: one reconcile trigger (startup, resume,
  post-401, queue message).
- Native session death ⇒ user-visible consequence (system notification
  immediately; in-app alert + `/login` at the next reconcile trigger) — never
  silent.
- Only one refresh in flight per process; a spent refresh token is never
  re-presented (static `refreshMutex` + rotation-aware fast path in
  `forceRefreshToken`).
- A transient refresh failure (5xx/timeout) never clears the session; only a
  401 does.
- A fresh login is never torn down by a stale failure: every logout initiated
  from an async path carries the auth generation snapshotted before its first
  await, and `logout()` ignores stale generations.

## Where the tests bite

- `native-expiry-weblogout.test.ts` — edge path: worker 401 → queue message →
  WebView on `/login`.
- `native-refresh-5xx-keeps-session.test.ts`,
  `native-transient-refresh-keeps-session.test.ts` — transient ≠ death.
- `relogin-notification.test.ts` — the system notification on death.
- `session-expiry-reconcile.test.ts` — level path: session dies, process is
  killed (queue message lost by construction), relaunch must land on `/login`
  from the persisted flag alone.
- `app-resilience.test.ts` — foreground 401 → forced refresh → death → login
  form.
