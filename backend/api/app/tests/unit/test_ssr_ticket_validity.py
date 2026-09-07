"""Unit tests for how a dead SSR ticket is told apart from a dead access token.

The integration suite covers a ticket whose SIGNATURE no longer verifies (a
rotated key). It cannot cover the commoner death — plain expiry — because a test
process has no private key to mint an already-expired token with. In here the
signing key is loaded, so the real thing can be built and the branch exercised
for what it actually was written for.

Why the branch exists: once validate_token has said no, its claims are gone, and
the SSR dependencies still have to choose between rendering anonymously and
answering 401. Getting that wrong is not cosmetic — a cookie outliving its ticket
(a client clock behind the server, a key rotation) turned the photo page into an
error page, because its server load raises 502 on any non-404 failure.
"""
from common.jwt_utils import create_jwt_token
from jwt_service import PRIVATE_KEY, validate_token
from auth import is_dead_ssr_ticket, is_ssr_read_token


def _minted(token_type: str, expires_minutes: float) -> str:
	"""A real token of `token_type`, signed with the server's own key."""
	token, _ = create_jwt_token(
		{"sub": "user-1", "username": "u", "sid": "sid-1", "type": token_type},
		PRIVATE_KEY,
		expires_minutes,
	)
	return token


def test_an_expired_ssr_ticket_reads_as_a_dead_ticket():
	token = _minted("ssr_read", -1)
	# Precondition: this really is dead by the normal path.
	assert validate_token(token) is None
	assert is_dead_ssr_ticket(token) is True


def test_an_expired_access_token_is_not_mistaken_for_a_ticket():
	# The distinction that keeps 401 meaning 401: an expired *credential* must not
	# be quietly downgraded to an anonymous render.
	token = _minted("access", -1)
	assert validate_token(token) is None
	assert is_dead_ssr_ticket(token) is False


def test_a_live_ticket_is_recognised_from_its_verified_claims():
	claims = validate_token(_minted("ssr_read", 60))
	assert claims is not None
	assert is_ssr_read_token(claims) is True


def test_a_live_access_token_is_not_a_ticket():
	claims = validate_token(_minted("access", 60))
	assert claims is not None
	assert is_ssr_read_token(claims) is False


def test_garbage_is_neither():
	# Nothing here may throw: these run on whatever arrives in an Authorization
	# header, including a truncated cookie or a wholly unrelated string.
	for junk in ["", "not.a.jwt", "a.b", "....", "Bearer x"]:
		assert is_dead_ssr_ticket(junk) is False
