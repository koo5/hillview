"""Canonical fixed development/test-user accounts — the single source of truth.

Defined once here and imported by:
  - the server's recreate flow (``api/app/auth.py``: ``recreate_test_users``),
  - the test-suite credential helpers (``tests/utils/auth_utils.py``),
  - the debug CLI's default login (``tests/utils/debug_utils.py``).

These are NOT secrets: they are fixed local dev/test credentials, and the server
only ever creates these accounts when the ``TEST_USERS`` / ``DEBUG_ENDPOINTS``
env flags are enabled. The test suite seeds from this list but overrides it at
runtime with whatever the running server's recreate endpoint actually returns
(see ``auth_utils.update_test_credentials``), so it also works against a server
whose test-user passwords differ from these defaults.
"""
from common.models import UserRole

# (username, password, role)
TEST_USER_ACCOUNTS = [
	("test", "StrongTestPassword123!", UserRole.USER),
	("admin", "StrongAdminPassword123!", UserRole.ADMIN),
	("testuser", "StrongTestUserPassword123!", UserRole.USER),
	("moderator", "StrongModeratorPassword123!", UserRole.MODERATOR),
]

# username -> password, for consumers that only need to authenticate.
TEST_USER_PASSWORDS = {username: password for username, password, _ in TEST_USER_ACCOUNTS}
