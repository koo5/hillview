# Stream auth: replace `?token=<access_token>` with a client-signed credential — TODO

Status: **backend DONE (2026-07-08); client wiring PENDING.** Auth-review finding #5.

## Done (backend, verifiable + shipped behind legacy compat)

- `auth.verify_stream_credential(key_id, exp, sig, db)` — looks up the active
  `UserPublicKey` by `key_id`, checks `exp` (must be future and within
  `STREAM_CREDENTIAL_MAX_TTL_SECONDS` = 15 min), verifies the signature over the
  canonical `[key_id, "stream", exp]` list via the existing `verify_ecdsa_signature`
  (handles web P1363 + Android DER), returns the owning active user.
- `get_current_user_optional_with_query` gained a stream-credential branch:
  header token → **signed stream credential** (`stream_key_id`/`stream_exp`/
  `stream_sig`) → **legacy `?token=`** → anonymous. Present-but-invalid stream cred =
  401 (client retries with a fresh one). Legacy `?token=` still accepted, so old
  web/Android clients are unaffected — **additive, no flag**.
- Test surface `GET /api/debug/whoami-query` (`@debug_only`) reflects the resolved
  user for the optional-auth dependency.
- Tests: `backend/tests/integration/test_stream_auth.py` (valid / expired / far-future /
  forged / tampered-exp / unknown-key / legacy-token / header-token).
- Web primitive in place but **not yet wired**: `clientCrypto.signStreamAuth(ttl)`
  returns `{keyId, exp, signature}` signing the same canonical list.

## Client wiring PENDING (unverifiable in this env — needs live map + device)

The stream loader runs in a **web worker**, on both web AND Android (the worker's
auth calls have a TAURI branch hitting the `plugin:hillview|...` commands). So wiring
spans a worker bridge + Kotlin:

1. **Worker bridge** (`webworkers/new.worker.ts`): add a `getStreamAuth()` alongside
   `getValidToken()`. Web branch → ask main thread (which calls
   `clientCrypto.signStreamAuth()`) via a new request-id-correlated message
   (mirror `pendingTokenRequests`). TAURI branch → `invoke('plugin:hillview|sign_stream_auth')`.
2. **StreamSourceLoader.ts:225-231**: replace `url.searchParams.set('token', authToken)`
   with the three `stream_*` params from `getStreamAuth()`; re-sign on retry.
3. **Android**: new plugin command `sign_stream_auth` in `ExamplePlugin.kt` →
   `ClientCryptoManager.signStreamAuth(exp)` (sibling of `signUploadData`, using the
   existing `signData` assembly so the canonical bytes match).
4. Later cleanup (breaking, gate it): drop the legacy `?token=` branch once old
   clients age out.

--------------------------------------------------------------------------------
Original plan notes below (kept for reference).

## Problem

`type: 'stream'` sources (Hillview's own photos AND Mapillary — same generic loader)
open a **Server-Sent Events** stream. `EventSource` (web) / the Android
`StreamPhotoLoader` can't set an `Authorization` header, so the client appends the
full **100-minute access token** to the URL:

- web: `StreamSourceLoader.ts:230` → `url.searchParams.set('token', authToken)`
- android: `StreamPhotoLoader.kt:334` → `addQueryParameter("token", ...)`
- server: `get_current_user_optional_with_query` reads `?token=` (`auth.py`)

The token then lands in API + Caddy access logs and browser history. Hillview is NOT
special-cased — it's `type:'stream'` too (`data.svelte.ts`), so it has the identical
leak. Panoramax (`type:'panoramax'`) is header-authed and unaffected.

The other ~7 endpoints that *accept* `?token=` (activity, bestof, ratings, mapillary
stats, detections, public photo, users) are never actually called with a URL token —
they use header auth. So they're latent surface, narrow-able to header-only as a
separate verifiable step.

## Fix: client-signed, short-TTL, stream-scoped credential

Reuse the existing client ECDSA keypair (registered via `/auth/register-client-key`,
stored in `UserPublicKey`). The client signs a small assertion locally — **no server
round-trip to mint** — and puts *that* in the URL instead of the access token.

**Credential:** client signs the list `[key_id, "stream", exp]` with its private key.
- `exp` = now + **10 minutes** (unix seconds). Generous window that also absorbs
  clock skew and covers a pan session's reconnects without re-signing constantly.
- URL carries `?stream_key_id=…&stream_exp=…&stream_sig=…` (no access token).

**Server verify:** look up `UserPublicKey` by `key_id` (active) → reconstruct the
exact list from the URL params → `verify_ecdsa_signature(...)` → check `exp` not
passed → `current_user` = that key's owner.

Properties:
- The `"stream"` literal binds purpose — a stream sig can't be replayed as upload
  auth (different payload shape), and vice versa.
- A leaked stream URL is low-value: expired in 10 min, only opens a stream, never
  exposes the long-lived access token.
- Anonymous streams carry no credential (works as today, `current_user=None`).
- Replay within the 10-min window is possible but low-risk (only re-opens a stream
  the user could open anyway). True one-time would need server-side nonce state,
  which we're deliberately avoiding.

## Why it's a small delta (primitives already exist)

- Server `verify_ecdsa_signature()` (`common/security_utils.py:352`) already verifies
  client sigs and **auto-detects web P1363 (64-byte) vs Android DER** — one function,
  both platforms, unchanged.
- `UserPublicKey` maps `key_id → {public_key_pem, user_id, is_active}` — resolves the
  user with no extra state.
- Web `clientCrypto.signUploadData()` and Android
  `ClientCryptoManager.signUploadData/​signPushRegistration` are the exact pattern; add
  a sibling `signStreamAuth(exp)` on each.

## Changes

Backend:
1. `verify_stream_credential(key_id, exp, sig, db) -> Optional[User]` in `auth.py`.
2. New dep `get_current_user_optional_stream`: resolves header → signed triple →
   **legacy `?token=` (kept for old clients)** → None.
3. Point stream endpoints at it: Mapillary stream (`mapillary_routes.py:287`) + the
   Hillview stream endpoint(s) in `hillview_routes.py`.
4. (Separate step) narrow the other ~7 query-token endpoints to header-only.

Web: `StreamSourceLoader.ts:225-231` — replace the `token` param with the three
signed params; sign at stream open and on each retry/reconnect (re-signs locally).

Android: `StreamPhotoLoader.kt:334` — replace `token` with the three signed params via
a new `signStreamAuth`.

## Backward-compat — additive, NO flag needed

The server keeps accepting legacy `?token=` alongside the new triple, so old web + old
Android keep working unchanged; only new clients stop leaking. Nothing is *removed*, so
nothing breaks. Dropping the legacy `?token=` branch later (once old clients age out)
WOULD be a breaking change worth gating — future cleanup, not now. (Contrast: the
`STRICT_REFRESH_ROTATION` / `OAUTH_STRICT_STATE` flags gate *removals* of old behavior.)

## Tests

- Backend integration `test_stream_auth.py` (drive real ECDSA signing from Python via
  `cryptography`): valid cred → user resolved; expired `exp` → rejected; forged sig →
  rejected; sig bound to a different `key_id` → rejected; legacy `?token=` still works;
  no cred → anonymous.
- Client edits (web `EventSource`, Android `StreamPhotoLoader`) can't be fully
  exercised locally — need live map + Mapillary + device. Typecheck web; flag Android
  for the async build run (same as the refresh-serialization work).

## Open decision (defaulted)

Could also bind bbox/client_id into the signed payload so a leaked cred can't be
reused for a different area. Default: **don't** — keep `[key_id,"stream",exp]` so one
signature covers a pan session's reconnects. Revisit only if the 10-min window feels
too loose.

Related: [[auth-token-review-findings]], [[auth-followups-todo]].
