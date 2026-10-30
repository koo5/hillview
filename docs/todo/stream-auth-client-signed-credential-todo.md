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

Two loaders, not one. On the web the stream loader is `StreamSourceLoader.ts`
in the web worker (`new.worker.ts`), whose `getValidToken` asks the main thread.
On Android — the Tauri app AND frontend2 — streams never touch the web worker:
`simplePhotoWorker` picks `KotlinPhotoWorker`, whose `photo_worker_process`
command runs `PhotoWorkerService` → `PhotoOperations` → shared-kt
`StreamPhotoLoader` (OkHttp); frontend2's `StreamMarkerSource` drives that same
loader. (The TAURI branch inside the worker's `getValidToken` predates the
Kotlin worker; the loader never runs there on Android.) So the wiring is:

- **Web worker bridge** (`webworkers/new.worker.ts`): a `getStreamAuth()`
  alongside `getValidToken()` that asks the main thread (which calls
  `clientCrypto.signStreamAuth()`) via a request-id-correlated message, like
  `pendingTokenRequests`.
- **StreamSourceLoader.ts**: replace `url.searchParams.set('token', authToken)`
  with the three `stream_*` params from `getStreamAuth()`; re-sign on retry.
- **Android, in Kotlin only**: `StreamPhotoLoader.buildStreamUrl` takes a signed
  credential instead of the token. The provider it is handed — PhotoOperations'
  `authTokenProvider` in the Tauri plugin, `freshToken` in frontend2's
  `StreamMarkerSource` — becomes a credential provider calling
  `ClientCryptoManager.signStreamAuth(exp)` (sibling of `signUploadData`, same
  `signData` assembly so the canonical bytes match). No new plugin command.
- Later cleanup (breaking, gate it): drop the legacy `?token=` branch once old
  clients age out.

## Client key registration and error visibility (2026-10-30)

Found while making web login survive a stalled `register-client-key`
(docs/todo/load-resilience.md). The credential is signed with the device's
client key, so it only verifies once that key is registered under the user.

What the backend does today, in `get_current_user` (auth.py): if any
`stream_*` param is present, the credential must verify; otherwise 401. An
unregistered key, an expired `exp` and a bad signature all produce the same
401 with the generic detail. Nothing is served anonymously — an earlier note
claiming the stream silently fell back to anonymous was wrong.

Why that is awkward for the client: the loader is an `EventSource`. On a
non-2xx response it fires `error` with no status and no body, so the client
cannot tell "key not registered" (re-register, then retry) from "credential
expired" (re-sign, then retry) from "token gone" (log out). Today it would
have to guess, and the two heals are different.

Ways out. Reading the SSE body with `fetch` (Authorization header, no token
in the URL, no credential at all) was weighed hard in July 2026 before this
plan was chosen, and lost to a web-side constraint; Android was never the
constraint (its loader is OkHttp and can set any header). The reason itself
was not written down at the time, so it is not restated here; re-establish it
before re-opening that option.

- **Deliver auth failures in-band.** The one thing an EventSource can read is
  an event. The stream endpoints answer an unverifiable credential — and,
  usefully, an expired legacy `?token=` too — with 200 and a single
  `event: auth_error` / `data: {"error_code": "stream_key_not_registered" | "stream_credential_expired" | "unauthorized"}`,
  then close. The client acts on the code and closes the source so the
  browser does not reconnect blind. Unconventional (a 200 for an auth
  failure), but it is the only channel the transport offers, and additive:
  the 401 stays for requests that carry no credential at all. Scope: a
  non-raising variant of the stream auth dependency returning user-or-reason,
  one event at the top of the two stream generators (hillview_routes,
  mapillary_routes), and a handler in the web and Kotlin loaders. The
  preferred option.
- **Make the ambiguity not matter.** Await `ensureClientKeyRegistered()`
  (frontend/src/lib/clientKeyRegistration.ts) before signing, re-sign with a
  fresh `exp` on every connect, and on an immediate error do a single blind
  heal (re-register the key, re-sign, reconnect once) before treating the
  session as gone. Cheapest, still a guess; the loader already does a blind
  forced token refresh on retry today.

A probe `fetch` of the same URL to read the status was considered and dropped:
it opens a second stream per failed connect just to read a header.

On Android the key is registered by AuthenticationManager.storeAuthToken, best
effort, and healed by PhotoUploadLogic; the stream has no heal of its own
there yet. Whichever option is taken lands in both loaders, StreamSourceLoader.ts
and shared-kt StreamPhotoLoader.

Compatibility of the in-band event with clients already built: both shipped
loaders parse `data: {"type": "error", "message": ...}` today. The Kotlin one
turns it into a stream error, retries once when the message contains "auth"
or "401", then fails — the same visible behaviour as today's 401 (and its
retry reuses the same token string, so it is as blind now as it would be
then). The web one reports the error and closes the EventSource, so no
reconnect loop. Keep that exact shape and add `error_code` beside `message`;
a new `event:` type would also degrade safely but gains nothing. And emit it
on the credential path only until clients that act on the code are out: no
shipped client sends `stream_*` params, so nothing built today can see it.

Not done: none of the above is implemented; the client wiring itself is still
the pending item at the top of this file.

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
