# SSR auth ticket

The web build server-renders `/`, `/bestof`, `/activity` and `/photo/[uid]`
for crawlers. Tokens live in the browser's IndexedDB, which the server never
sees, so those renders used to be anonymous and the client corrected them after
hydration: a spinner over content that was already right for an anonymous
visitor, and the wrong hidden-content filtering for a signed-in one until the
refetch landed.

The fix is a third token, the **SSR read ticket**, which the browser mirrors
into a cookie on the frontend's own origin so the server can render the
visitor's own view.

## What the ticket is

- A JWT of type `ssr_read`, minted by `create_ssr_read_token` alongside every
  access/refresh pair: password login, `/auth/refresh`, the `/auth/oauth`
  exchange and the OAuth polling endpoint. Claims: `sub` (user id),
  `username`, `sid` (session family).
- Its lifetime is the refresh token's, and it is reissued on every refresh, so
  it tracks the session instead of aging out mid-session.
- The `Token` response model declares `ssr_token` and `ssr_token_expires_at`.
  A `response_model` strips anything it does not name, so a field minted in a
  route but missing from the model never reaches the client.

## Read-only by allowlist

The ticket authenticates on exactly two dependencies, and endpoints opt in by
name:

- `get_current_user_optional_ssr` — the strict flavour, for `/bestof/photos`,
  `/activity/recent` and `/photos/public/{uid}`;
- `get_current_user_optional_soft_ssr` — the forgiving flavour, for annotation
  listing, which has always shrugged at a bad credential.

`get_current_user`, `get_current_user_optional` and
`get_current_user_optional_with_query` all reject it explicitly, and
`/auth/refresh` checks for type `refresh`, so it cannot be laundered into a
session. Several write endpoints authenticate through the shared optional
dependency (contact, push registration), which is why the allowance lives on
the endpoints and not there: a new write endpoint cannot inherit it by
accident.

What a leaked ticket buys: the victim's hidden-content filtering, their own
rating and ownership flag on a photo, and their user id. All of that is equally
readable from IndexedDB by any script on the origin, which is why the cookie
being script-writable (and so not HttpOnly) does not widen anything. It has to
be written by JS: in production the API answers on api.hillview.cz and the site
on hillview.cz, so the backend cannot set a cookie the frontend server would
ever see.

A ticket that fails validation — expired past its cookie because the client
clock ran behind, or signed with a rotated key — degrades to the anonymous
render, never a 401. `is_dead_ssr_ticket` takes an unverified look at the type
claim of a token validation has already refused; forging it buys nothing,
since "anonymous" is what a caller gets with no token at all. Without this the
strict fallthrough produced a 401, which the photo page turned into a 502 error
page. A ticket of a revoked session (logout, refresh-token reuse) renders
anonymously too: `_user_for_ssr_ticket` checks the session family.

## The cookie

`hv_ssr`, written by `$lib/ssrTicketCookie.ts`: host-only, `Path=/`,
`SameSite=Lax` (a top-level navigation from a search result must carry it),
`Secure` on https, `Max-Age` equal to the ticket's remaining life. It is
written, and read back to detect a browser that silently refuses cookies, by
`webTokenManager.mirrorSsrTicket` after every `storeTokens` and on every
`refreshCache`. The latter is what covers the service worker: it refreshes
tokens with no `document` to write a cookie into, saves the ticket to IndexedDB
and announces `auth_changed`, and the next tab to hear it re-mirrors.
`clearTokens` drops the cookie.

`completeAuthentication` in `auth.svelte.ts` builds the stored object from an
explicit field list, and so does the OAuth polling component. The ticket fields
are on both lists and have to stay there, or login stores no ticket and the
cookie first appears at the first refresh, which passes the whole response
through. `storeTokens` deliberately does not fall back to a cached ticket the
way it does for the refresh expiry: a ticket is bound to its `sid`, so one from
an earlier login must not outlive that login.

Android stores nothing of this: the native token manager picks its fields
before anything reaches Kotlin, and the Kotlin refresh parser is quote-anchored
per field, so the extra fields are invisible to installed builds.

## The server side

`hooks.server.ts` reads the cookie into `event.locals.ssrTicket` when
`SSR_AUTH` is not `off`. That is a runtime variable on the frontend container,
not a `VITE_` build-time one, so a restart is enough to fall back to anonymous
rendering with the client correcting it. The four server loads pass the ticket
to the API through `ssrAuthHeaders`. Every document and `__data.json` response
gets `Vary: Cookie`, switch on or off; ones rendered with a ticket get
`Cache-Control: private, no-cache`.

The list endpoints and the public photo endpoint echo `viewer_id`: who the
batch was filtered for, `null` when anonymous. The loads pass it to the page,
and `createSsrBackedLoad` fetches only when the batch on screen was not
rendered for the visitor looking at it — an anonymous batch for a signed-in
visitor, another account's batch restored from back/forward cache, or no batch
at all. It is an id from the API rather than from the ticket the server sent,
so a refused ticket reads as the anonymous batch it actually produced. When the
backend call fails, the list loads return no batch, so the page loads for
itself instead of sitting on an empty list it believes is final.

## Tests

`backend/tests/integration/test_auth_token_lifecycle.py` pins the contract:
ticket issued on login and refresh, accepted with the right `viewer_id`,
rejected by `/auth/me`, `/auth/logout` and `/auth/refresh`, anonymous after
logout, and anonymous rather than 401 when tampered while an invalid access
token on the same endpoint stays a 401. `frontend/src/lib/ssrBackedLoad.test.ts`
covers the client-side decision.
