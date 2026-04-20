"""Runtime on/off gate for outgoing push (both FCM and UnifiedPush).

Motivation: real push delivery hits Firebase and/or third-party
UnifiedPush distributors. We don't want ordinary dev or test workflows
to hammer them just by exercising unrelated code paths. At the same
time prod should default to sending.

Semantics:
  - Startup default: OFF in DEV_MODE, ON otherwise.
  - Test-state wipes (`/api/debug/recreate-test-users`, `clear-database`)
    reset to that startup default — so if a test turned push ON, the
    next test run starts clean.
  - Operators can flip at runtime via
    `POST /api/internal/debug/push-enabled`, which also comes in handy
    during incident response (cut all outgoing push instantly).

State is per-process, in-memory. Multiple API workers behind a load
balancer won't stay in sync — good enough for its purpose.
"""

from __future__ import annotations

import logging
import os

log = logging.getLogger(__name__)

_dev_mode = os.getenv("DEV_MODE", "false").lower() in ("true", "1", "yes")
_enabled = not _dev_mode


def is_enabled() -> bool:
	return _enabled


def set_enabled(enabled: bool) -> None:
	global _enabled
	_enabled = bool(enabled)
	log.info(f"push_toggle: outgoing push enabled={_enabled}")


def reset_to_default() -> None:
	"""Reset to the startup default (OFF in DEV_MODE, ON otherwise)."""
	set_enabled(not _dev_mode)
