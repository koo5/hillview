"""Async engine for the panoramax container.

Deliberately not common.database: this service runs as the dedicated
panoramax_ro role, uses raw SQL only (no ORM models), and must not drag in the
main app's model imports. DATABASE_URL uses the same postgresql+asyncpg://
scheme as the rest of the backend.
"""
import os

from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.pool import NullPool

_engine: AsyncEngine | None = None


def _require_password(url: str) -> str:
	"""Refuse an empty DB password instead of limping.

	Compose defaults PANORAMAX_DB_PASSWORD to '' because marking it required
	(`:?`) in a profile-gated service breaks EVERY compose command for people
	who never enable the profile (verified on compose v2.37: interpolation
	runs before profiles are applied). So the fail-fast lives here: one clear
	exit at boot beats an endless mislabelled "database not reachable yet"
	retry loop and 500s from a healthy-looking container.
	"""
	if make_url(url).password in (None, ''):
		raise SystemExit(
			'DATABASE_URL has an empty password — set PANORAMAX_DB_PASSWORD in '
			'.env (see docs/panoramax-federation.md, Deployment)')
	return url


def get_engine() -> AsyncEngine:
	global _engine
	if _engine is None:
		url = _require_password(os.environ['DATABASE_URL'])
		kwargs = {}
		if os.getenv('DB_NULLPOOL', '').lower() in ('1', 'true', 'yes'):
			kwargs['poolclass'] = NullPool
		else:
			kwargs['pool_size'] = int(os.getenv('DB_POOL_SIZE', '5'))
			kwargs['max_overflow'] = int(os.getenv('DB_MAX_OVERFLOW', '5'))
			kwargs['pool_pre_ping'] = True
		_engine = create_async_engine(url, **kwargs)
	return _engine
