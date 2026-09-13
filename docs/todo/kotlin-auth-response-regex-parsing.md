# Parse the token refresh response properly on Android

`AuthenticationManager.performTokenRefresh` (in `shared-kt/src/cz/hillview/plugin/`) reads
`/auth/refresh` with four regexes over the raw body, under its own comment "Parse JSON
response (simple manual parsing)":

```kotlin
val accessTokenMatch = Regex("\"access_token\":\\s*\"([^\"]+)\"").find(responseBody)
val refreshTokenMatch = Regex("\"refresh_token\":\\s*\"([^\"]+)\"").find(responseBody)
val expiresAtMatch = Regex("\"expires_at\":\\s*\"([^\"]+)\"").find(responseBody)
val refreshExpiresAtMatch = Regex("\"refresh_token_expires_at\":\\s*\"([^\"]+)\"").find(responseBody)
```

This is the only place in the Kotlin sources that parses JSON this way; every other decoder
(`PhotoWorkerService`, `StreamPhotoLoader`, `PanoramaxPhotoLoader`) uses kotlinx.serialization
with `ignoreUnknownKeys = true`.

## Why it matters

It holds today, but by luck rather than by construction:

- `find` takes the first match **anywhere** in the body, so a nested object echoing one of
  these names would win over the real field.
- A value containing a `"` truncates the capture. Only JWTs and ISO timestamps land here,
  which is the sole reason this has never bitten.
- A partial parse is accepted silently: no `refresh_token` match simply means a null refresh
  token, not an error.
- It quietly constrains the API. Those four fields must stay top-level strings under exactly
  those names forever, or installed builds stop refreshing and their sessions die. Nothing on
  the backend records that promise.

Noticed on 2026-09-07 while adding `ssr_token` / `ssr_token_expires_at` to the same response
for authed server rendering. Those additions are invisible to these regexes — each pattern
needs a quote immediately before the field name — but only because of how they happen to be
named. A field called `access_token_v2` would have been read as `access_token`.

## It was not always a free choice

The regexes went in on 2025-08-25 (9a33977d), and at that commit the plugin's
`build.gradle.kts` applied no serialization plugin and declared no serialization
dependency — so kotlinx.serialization genuinely was not available to that file. It is now:
the same build file applies `org.jetbrains.kotlin.plugin.serialization` and pulls in
`kotlinx-serialization-json`, and sibling files in shared-kt (`StreamPhotoLoader`,
`PanoramaxPhotoLoader`) decode with it. `org.json.JSONObject` is a platform API and is
already imported by this very file, which uses it to *build* the request body in
`registerClientPublicKey`.

Whether org.json was ruled out for some other reason back then is unverified; it would take
digging into the pre-shared-kt history to say. Not worth doing before the rewrite — both
parsers are available today, which is what decides the approach below.

## Proposed approach

A `@Serializable` data class for the response plus `Json { ignoreUnknownKeys = true }`, as the
other decoders already do. Treat a missing `access_token` or `expires_at` as a failed refresh
rather than storing half a session.

Constraint from `shared-kt/README.md`: this file is compiled as source by **both** toolchains
(Kotlin 2.0.20 on the Tauri side, 2.4.x in frontend2), so whatever lands must build under
both — the same reason the README calls for conservative Kotlin only.

## The part this does not fix

Builds already on devices keep the regexes, and they are the population compatibility is
about. So the backend constraint above stands regardless of when this lands: the four field
names are effectively frozen until the old builds age out. Worth stating in the API's own
comments rather than leaving it implicit here.
