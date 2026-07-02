# Config-permutation testing & runtime overrides — design / TODO

Status: **design notes, not yet implemented.** Parked mid-way through the auth
token-hardening work (strict refresh-token rotation). Pick up in a later session.

## Why this exists

Prod and dev differ along many axes — rate/request limits, which endpoints are
exposed, debug gates, and worker **container deployment modes** (e.g. CDN-on vs
CDN-off, which is a *build-time* Dockerfile difference). We have no CI, so testing
these permutations has to be a serial script we run locally. We need a coherent
structure for that instead of per-flag hacks.

The immediate trigger: strict refresh-token rotation (`STRICT_REFRESH_ROTATION`,
see below) needs to be exercised in **both** on and off modes, and that shape will
repeat for every future flag.

## Core principle: separate *resolution* from *behavior*

Two different things get conflated; they want different tests:

1. **Config resolution** — "env var / compose profile → typed setting."
   Pure and cheap. Unit-test it with no server boot, exhaustively over messy inputs
   (`"False"`, `"0"`, unset, garbage). A runtime override *bypasses* this, so if we
   only test via the override we get false confidence that the env wiring works.

2. **Config-dependent behavior** — "given strict is off, refresh-token reuse is
   tolerated." Needs the running endpoint. This is where a runtime override earns
   its keep: flip the setting, exercise the behavior, all in one server boot.

Per-flag hygiene = the trio: (a) unit test for resolution, (b) fast-tier behavior
test via override, (c) one slow-tier row that boots with the *real* env var set.

## Two tiers

### Fast tier — the current integration suite, flipping runtime configs

Amounts to: the existing integration suite toggles runtime-tunable config as needed
via debug endpoints, within a single dev-mode server boot. Seconds per permutation.

- Example win: **revive request/rate-limit tests** by refactoring the limits to be
  controllable through the runtime-overrides module. Today limit configuration lives
  in `common/config.py` (`is_rate_limiting_disabled`, etc.) + `rate_limiter.py` and
  is awkwardly complex; routing it through one override registry both simplifies it
  and makes it test-tunable.
- Only works for settings that are genuinely runtime-tunable and for a
  **single-process** server (see caveat below).

### Slow tier — a "prod-like" boot

For everything that is **not** runtime-tunable (worker deployment modes, CDN
build-mode, prod vs dev limits/endpoints, debug gates off). Requires reboots, so it's
a separate, slower runner. Realistically we can probably maintain **one** "prod-like"
configuration, not a big matrix.

Open decisions (undecided — resolve next session):
- Tear down the dev-mode containers and bring up prod-mode containers **in the same
  repo/dir** (nice, but we must sort out `.env` file handling first — dev/prod env
  separation), **or**
- Delegate the prod-like run to a **VM** that the script updates automatically, **or**
- A new one-time VM solution if one turns up.
- How tests select themselves per profile: pytest markers (`-m strict_off`,
  `-m worker_cdn`) driven by the runner, and/or tests reading `GET /api/debug/config`
  and self-skipping on mismatch (robust regardless of how they're launched).

## Runtime overrides module

A small module, **reusable across api and worker** (both need to read the same
tunables), holding an in-memory per-process override registry.

Requirements / hygiene rules:
- **Shared api+worker** — lives somewhere both import (e.g. `common/`), not in
  `api/app`.
- **Gated** — only settable under `DEBUG_ENDPOINTS`/`DEV_MODE` (existing
  `@debug_only` pattern).
- **One reset, enforced by the harness** — an autouse function-scoped fixture in the
  integration `conftest.py` that resets *all* overrides after every test. This is the
  keystone: cross-test leakage from a forgotten reset is the #1 failure mode. Extends
  the existing `push_toggle.reset_to_default()` idea into a single `reset_all()`.
- **Introspectable** — `GET /api/debug/config` echoes *effective* settings so a
  mode-specific test asserts the mode before running (or self-skips). Prevents a
  toggle that silently didn't take from passing against the wrong config.
- **Whitelisted keys** — a known registry of test-tunable flags, never a generic
  "set any setting" backdoor into a running server.
- **Single-process / dev-only** — an in-process override only affects one worker;
  prod with multiple uvicorn workers would toggle one and serve from another. So the
  override is a dev/test tool; the **prod rollout path is the env var**, validated in
  the slow tier. Document this loudly.

Sketch:
```
overrides.get_bool("strict_refresh_rotation", env_default)   # read sites
POST /api/debug/override        {key, value}                 # gated, whitelisted
POST /api/debug/override/reset                               # or fold into reset_all
GET  /api/debug/config                                       # effective settings
```
Existing ad-hoc overrides (force-logout, access-ttl, `debug_delays`, `push_toggle`)
can migrate onto this later or stay; the registry is just the clean home for new ones.

## Concrete first slice (the pick-up point)

1. `common/runtime_overrides.py`: registry with `get_bool`/`set`/`reset_all` +
   whitelist.
2. Route `is_strict_refresh_rotation_enabled()` (currently in `api/app/auth.py`,
   env-only) through it: `overrides.get_bool("strict_refresh_rotation", <env default>)`.
3. `POST /api/debug/override` + `GET /api/debug/config` in `debug_routes.py`, both
   `@debug_only`.
4. Autouse function-scoped reset fixture in `backend/tests/conftest.py`.
5. Unit test for env parsing of the flag (pure, no server).
6. OFF-mode integration test in `test_auth_token_lifecycle.py`: flip strict off via
   the override, assert reuse of a rotated refresh token is **tolerated** (200) and
   the session is **not** revoked; assert mode via `GET /config` first. Reset after.

~an hour; establishes the template every future flag follows. The slow-tier runner is
a separate piece once we have 2–3 boot-time axes to justify its shape.

## Current state of the gated flag (already shipped in this work)

`STRICT_REFRESH_ROTATION` env var, **default true**, read per-call by
`auth.is_strict_refresh_rotation_enabled()`, gates only the reuse *enforcement*
(single-use spend + spent-token rejection + reuse→family-revocation) in
`/auth/refresh`. Logout family revocation, the session-revoked checks, and the
tz-aware blacklist-expiry fix are **always on** (they don't depend on client
concurrency and never fire for a well-behaved old client). Rollout: run with
`STRICT_REFRESH_ROTATION=false` while old Android versions (pre process-wide refresh
lock) are still in the wild, flip to true once they've aged out. See
`auth-session-family-revocation` memory.
