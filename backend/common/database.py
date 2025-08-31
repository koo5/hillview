from sqlalchemy import create_engine, text
from sqlalchemy.orm import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
import os
import logging
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
    # Create async engine with connection pooling
    engine = create_async_engine(
        DATABASE_URL,
        pool_size=POOL_SIZE,
        max_overflow=MAX_OVERFLOW,
        pool_timeout=POOL_TIMEOUT,
        pool_recycle=POOL_RECYCLE,
        pool_pre_ping=True,  # Test connections before using them
        echo=os.getenv("DB_ECHO", "false").lower() == "true"
    )
    SessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
else:
    # In alembic mode, don't create the async engine
    engine = None
    SessionLocal = None

Base = declarative_base()

# Dependency to get DB session
async def get_db():
    db = SessionLocal()
    try:
        yield db
        # Note: Commit is handled by the endpoint if needed
    except Exception:
        await db.rollback()  # Rollback on any exception
        raise
    finally:
        await db.close()
