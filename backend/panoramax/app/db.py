"""Async engine for the panoramax container.

Deliberately not common.database: this service runs as the dedicated
panoramax_ro role, uses raw SQL only (no ORM models), and must not drag in the
main app's model imports. DATABASE_URL uses the same postgresql+asyncpg://
scheme as the rest of the backend.
"""
import os

from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.pool import NullPool

_engine: AsyncEngine | None = None


def get_engine() -> AsyncEngine:
	global _engine
	if _engine is None:
		url = os.environ['DATABASE_URL']
		kwargs = {}
		if os.getenv('DB_NULLPOOL', '').lower() in ('1', 'true', 'yes'):
			kwargs['poolclass'] = NullPool
		else:
			kwargs['pool_size'] = int(os.getenv('DB_POOL_SIZE', '5'))
			kwargs['max_overflow'] = int(os.getenv('DB_MAX_OVERFLOW', '5'))
			kwargs['pool_pre_ping'] = True
		_engine = create_async_engine(url, **kwargs)
	return _engine
