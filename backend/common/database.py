from sqlalchemy.orm import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.pool import NullPool
import os
from dotenv import load_dotenv

load_dotenv()

# Database configuration
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://hillview:hillview@localhost/hillview")

# Connection pool configuration
POOL_SIZE = int(os.getenv("DB_POOL_SIZE", "20"))
MAX_OVERFLOW = int(os.getenv("DB_MAX_OVERFLOW", "10"))
POOL_TIMEOUT = int(os.getenv("DB_POOL_TIMEOUT", "30"))
POOL_RECYCLE = int(os.getenv("DB_POOL_RECYCLE", "3600"))  # Recycle connections after 1 hour

# Only create async engine if not in alembic sync mode
if not os.getenv("ALEMBIC_SYNC_MODE"):
	_echo = os.getenv("DB_ECHO", "false").lower() == "true"
	if os.getenv("DB_NULLPOOL", "").lower() in ("1", "true", "yes"):
		# Tests: use NullPool so each connection is closed (and the close awaited)
		# when its session closes, instead of lingering in a shared pool. Pooled
		# asyncpg connections that outlive the sync TestClient's event loop get
		# GC'd at teardown and emit "coroutine 'Connection._cancel' was never
		# awaited". NullPool avoids that; production keeps the QueuePool below.
		engine = create_async_engine(DATABASE_URL, poolclass=NullPool, echo=_echo)
	else:
		# Create async engine with connection pooling
		engine = create_async_engine(
			DATABASE_URL,
			pool_size=POOL_SIZE,
			max_overflow=MAX_OVERFLOW,
			pool_timeout=POOL_TIMEOUT,
			pool_recycle=POOL_RECYCLE,
			pool_pre_ping=True,  # Test connections before using them
			echo=_echo
		)
	SessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
else:
	# In alembic mode, don't create the async engine
	engine = None
	SessionLocal = None

Base = declarative_base()

# Dependency to get DB session
async def get_db():
	if SessionLocal is None:
		raise RuntimeError("Database not initialized (ALEMBIC_SYNC_MODE is set)")
	db = SessionLocal()
	try:
		yield db
		# Note: Commit is handled by the endpoint if needed
	except Exception:
		await db.rollback()  # Rollback on any exception
		raise
	finally:
		await db.close()
