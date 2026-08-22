# Native Android auth — how it works and what we built

Written 2026-08-07, the day the feature landed (backend `117a703f`,
frontend2 `4652c32d`). A study companion: the concepts first, then a
guided tour of our implementation.

## 1. The landscape: what "native auth" is on Android

**Credential Manager** (`androidx.credentials`) is the modern, and only,
OS-level sign-in surface. One API call — `getCredential(request)` — makes
the OS show a bottom sheet; a *credential provider* (Google Password
Manager, Bitwarden, KeePassDX, …) fulfils it. Three credential types can
be requested, mixed freely in one request:

1. **Saved passwords** (`GetPasswordOption` / `CreatePasswordRequest`) —
   username+password pairs the provider stored *for your app*.
2. **Passkeys** (`GetPublicKeyCredentialOption`) — WebAuthn/FIDO2; the
   provider holds the private key, your server verifies assertions.
3. **Federated Google identity** (`GetGoogleIdOption`, from the separate
   `googleid` library) — returns a **Google ID token** right in the app.

Two common misconceptions worth killing:

- **There is no OS-level "sign in with any account on this device"
  chooser.** The accounts listed in Android Settings → Passwords &
  accounts are `AccountManager` registrations (Google, WhatsApp, …) and
  are *never* offered to third-party apps as sign-in options. Credential
  Manager's sheet is scoped to *your app's own* credentials plus Google
  federation if you ask for it. Facebook, Apple, etc. do not plug into
  it — which is why every app hand-rolls its "Continue with …" screen
  and wires each provider's own mechanism behind each button (native
  sheet for Google, app-switch for Facebook, browser for Apple).
- **`AccountManager` is not the API to use.** It's legacy plumbing for
  device-account authenticators, not app sign-in.

On Android 14+ this is AOSP API — third-party providers work without
Google. Below 14 the Jetpack library delegates to Play services, so a
degoogled older phone effectively has no provider (calls fail fast; the
user types).

## 2. The two OAuth shapes: authorization code vs ID token

Our pre-existing Google login (the Tauri app's) is the **authorization-
code flow**: browser → Google consent page → redirect with a `code` →
the *server* exchanges code+client_secret for tokens → server fetches
userinfo → server mints our JWTs → they travel back to the app via a
deep link (`cz.hillview://auth?...`) or the polling session. Many moving
parts; needs a browser; the redirect URI is attack surface (hence the
state-nonce CSRF machinery and redirect-URI validation in
`user_routes.py`).

The **native path** uses the **ID token** shape instead. Credential
Manager returns a *Google ID token* directly: a JWT **signed by Google**
whose claims assert "this Google account, verified by us, for this
audience". Nothing to exchange, no browser, no redirect. The app just
hands the token to our backend, which checks:

- **signature** — against Google's published JWKS (public keys at a
  well-known URL; `google-auth` fetches and caches them);
- **`iss`** — accounts.google.com;
- **`exp`** — not expired (we allow 10 s clock skew);
- **`aud`** — *the critical one*, see below;
- then reads **`sub`** (Google's stable user id), **`email`**,
  **`email_verified`**.

### Why `aud` must equal OUR client id

Any app on the phone can obtain a Google ID token for its own audience.
If we accepted any valid-signature token, EvilApp could take the token
Google minted *for EvilApp* and log into Hillview with it. The `aud`
claim binds a token to one relying party: we pass our client id as
`serverClientId` in `GetGoogleIdOption`, Google stamps it into `aud`,
and the backend refuses anything else. That's the whole cross-app
replay defence.

Note the id used is the **web client id** — the same `GOOGLE_CLIENT_ID`
the backend's browser flow already uses. Google's model: the *Android*
client id identifies the app package+signing cert to Google, but the
token's audience is the *server* that will consume it. So no new Google
Console setup was needed; the app just needs the same value at build
time (`HILLVIEW_GOOGLE_CLIENT_ID`).

### Why unverified emails are rejected

Our user matching (see §4) falls back to email. If Google reports
`email_verified: false`, someone may have created a Google account with
*your* address without proving ownership — accepting it would let them
capture the existing Hillview account that legitimately owns that email.
So the endpoint 400s on unverified addresses.

## 3. What stays the same: the backend is the only token authority

None of this touches the session machinery in `backend/api/app/auth.py`:
access + refresh JWTs minted together share a `sid` (session family);
refresh tokens are single-use (`jti` spend-tracking with reuse
detection, gated by `STRICT_REFRESH_ROTATION`); logout revokes the
family via the blacklist. Every login door — password form, browser
OAuth, native Google, someday passkeys — only changes *how the proof of
identity is acquired*. The proof is exchanged at one endpoint for the
same pair, and everything downstream (`TokenStore`, `SessionManager`,
`freshAccessToken()`, the WorkManager uploaders, shared-kt's
`AuthenticationManager`) neither knows nor cares which door minted it.

## 4. The backend endpoint

`POST /api/auth/google/native` with `{"id_token": "…"}` — in
`backend/api/app/user_routes.py`:

1. **Rate limit**: same budget as the OAuth callback (30/300 s per IP) —
   it's a login door.
2. **Config gate**: no `GOOGLE_CLIENT_ID` → 503 (feature off).
3. **Size bound**: >4096 chars → 400 before any crypto runs.
4. **Verification**: `verify_google_id_token(token)` — a module-level
   seam wrapping `google.oauth2.id_token.verify_oauth2_token` (from
   `google-auth`, which arrives transitively with `firebase-admin`;
   imported lazily). Run via `asyncio.to_thread` because the JWKS fetch
   is blocking. Unit tests monkeypatch this seam.
5. **Claim checks**: `sub` + `email` required; `email_verified: false`
   rejected (§2).
6. **The shared tail**: `oauth_user_to_tokens(db, "google", sub, email)`
   — extracted *verbatim* from the browser OAuth flow, so both doors
   behave identically:
   - find user by `oauth_id` OR `email`;
   - none → create (username = email local part, deduped with a numeric
     suffix; `is_verified=True`);
   - found but never OAuth-linked → link (`oauth_provider`/`oauth_id`);
   - mint `sid` + access + refresh, return the standard token dict.
7. **Audit**: `google_native_login_success` / `_failed` events, like the
   other doors.

Tests: `backend/api/app/tests/unit/test_google_native_login.py` — the
door's own logic with the seam and the tail patched (the tail is covered
by the existing OAuth integration tests). Gotcha recorded there: unit
test modules must set `USER_ACCOUNTS=true` *before* `import api`, or the
user router never mounts and everything 404s.

## 5. The app side

### The seam

`shared/src/commonMain/.../auth/CredentialGateway.kt` — the interface
the login flow talks to; `NoopCredentialGateway` for desktop/tests.
Android implementation in `auth/CredentialGateway.android.kt`:

- **`AndroidCredentialGateway`** wraps `CredentialManager`. Every method
  is best-effort: `GetCredentialException` / `CreateCredentialException`
  (no provider, nothing saved, user dismissed, no Play services) are
  swallowed into null/no-op — those are all answers, not errors.
- **`NativeAuthConfig`** — process-wide config set by
  `HillviewApplication` from `BuildConfig` (the `PhotoStorage.folderBase`
  pattern): `googleServerClientId` (empty ⇒ Google button hidden) and
  `uiEnabled`, the kill-switch the behaviour tests flip so no system
  sheet ever blocks driven UI (instrumented tests run in the app's
  process, so they can just assign it).
- **`CurrentActivityHolder`** — Credential Manager *requires an activity
  context* (its sheets attach to a window; an application context is
  refused). `MainActivity` registers itself in `onResume`/`onPause`; the
  gateway captures the reference before launching a sheet (the sheet
  itself pauses the activity — capture-then-launch is why that's safe).

Dependencies (`gradle/libs.versions.toml`): `androidx.credentials
:credentials`, `:credentials-play-services-auth` (the Play-backed
provider path), `com.google.android.libraries.identity.googleid`.

### The login screen flows

`LoginViewModel` + `LoginScreen` (commonMain):

- **Passive offer** — as the screen opens, `offerSavedCredential()` asks
  the gateway once per visit. A returned credential fills the form and
  submits with `saveOnSuccess = false` (it came *from* the provider;
  re-offering to save would nag). A dismissal leaves the plain form.
  This is the "sign in with what's saved on this device" experience —
  correctly scoped to our own credentials.
- **Save-on-success** — a *manual* login that succeeds offers the
  provider the credential (`savePassword`); the provider shows its own
  save sheet; declining is fine, the login stands.
- **Continue with Google** — below the OR divider, only when
  `googleAvailable` (client id configured). Tap → `googleIdToken()` →
  null means dismissed/unavailable (silently back to the form) → token
  means `SessionManager.loginWithGoogle(idToken)` →
  `AuthApi.googleNative()` → the endpoint → `finishLogin` (the shared
  local tail: store tokens, LoggedIn state, best-effort `me()` fetch for
  the username — Google logins have no username until then).

Layout matches the Tauri login page (`frontend/src/routes/login/
+page.svelte`): form, "OR", Google button. GitHub is *not* surfaced —
the original has its button commented out too; parity means deciding
deliberately later, not surfacing it accidentally.

Tests: `shared/src/jvmTest/.../CredentialLoginTest.kt` — fake gateway +
fake backend through the real screen: keystroke-free saved-credential
login (and no save-back), manual login saves, button hidden when
unconfigured, Google token buys a session, dismissal is not an error.

## 6. Configuration & operations

| Where | Variable | Meaning |
|---|---|---|
| backend env | `GOOGLE_CLIENT_ID` | Web client id; OAuth *and* the required ID-token audience. Unset ⇒ native endpoint 503s. |
| app build env | `HILLVIEW_GOOGLE_CLIENT_ID` | The same value, baked into `BuildConfig`. Unset ⇒ Google button hidden. |

Build with the button: `HILLVIEW_GOOGLE_CLIENT_ID=<id> ./gradlew
:androidApp:assembleDebug`.

Behavioral notes:

- **Degoogled phones**: `GetGoogleIdOption` fails (no Play services) →
  gateway returns null → nothing happens visually. Saved passwords still
  work on Android 14+ with any installed provider. When the browser
  OAuth flow is ported (deep-link work), the Google button will fall
  back to it — one button, no user-facing native-vs-web choice, both
  paths converging on the same backend identity.
- **Emulator/CI**: `GetGoogleIdOption` needs Play services *and* a
  signed-in Google account — untestable in CI; behaviour tests keep
  using password login with `NativeAuthConfig.uiEnabled = false`.
- **First-login UX**: manual login → provider offers to save → next
  login-screen visit offers it back → one tap, signed in.

## 7. Future doors (designed-for, not built)

- **Browser-fallback Google + GitHub**: needs the deep-link/OAuth-polling
  port from the Tauri app. The backend side already exists.
- **Passkeys**: Credential Manager does the on-device ceremony; the
  backend needs four WebAuthn endpoints (register/authenticate ×
  options/verify — `py_webauthn`), an RP ID equal to our domain, and an
  `assetlinks.json` at `https://<domain>/.well-known/` binding the
  package name + signing-cert SHA-256s (without it Android refuses the
  app that RP ID). They'd surface through the *same* passive sheet with
  zero layout change, and end at the same token pair.

## 8. File map (for a code-reading session)

- backend endpoint + verify seam + shared tail:
  `backend/api/app/user_routes.py` (`google_native_login`,
  `verify_google_id_token`, `oauth_user_to_tokens`)
- backend session machinery (unchanged, worth reading once):
  `backend/api/app/auth.py` (sid families, refresh rotation, blacklist)
- endpoint tests: `backend/api/app/tests/unit/test_google_native_login.py`
- seam: `frontend2/shared/src/commonMain/kotlin/cz/hillview/auth/CredentialGateway.kt`
- Android impl + config + activity holder:
  `frontend2/shared/src/androidMain/kotlin/cz/hillview/auth/CredentialGateway.android.kt`
- flows: `LoginViewModel.kt`, `ui/LoginScreen.kt`,
  `SessionManager.kt` (`loginWithGoogle`, `finishLogin`),
  `AuthApi.kt` (`googleNative`)
- flow tests: `frontend2/shared/src/jvmTest/kotlin/cz/hillview/auth/ui/CredentialLoginTest.kt`
- test kill-switch use:
  `frontend2/androidApp/src/androidTest/kotlin/cz/hillview/BehaviourSupport.kt`
  (`loginThroughTheUi`)
