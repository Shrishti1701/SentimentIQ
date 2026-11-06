"""Lazy SQLAlchemy engine and session configuration.

Importing this module or starting the API does not connect to PostgreSQL.
"""

from collections.abc import Generator

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from config.settings import settings


class Base(DeclarativeBase):
    """Base class for database models."""


def get_engine() -> Engine:
    """Create an engine only when persistence is explicitly requested."""
    if not settings.database_url:
        raise RuntimeError("DATABASE_URL is not configured")
    return create_engine(settings.database_url, pool_pre_ping=True)


def get_session() -> Generator[Session, None, None]:
    """Yield a database session; connecting occurs only when used."""
    factory = sessionmaker(bind=get_engine(), expire_on_commit=False)
    with factory() as session:
        yield session
