"""Engine, session factory, and the declarative Base. Sync SQLAlchemy 2.0."""
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import shared_settings


class Base(DeclarativeBase):
    """All ORM models inherit from this. Alembic reads Base.metadata."""
    pass


# pool_pre_ping avoids handing out a dead connection after Postgres restarts.
engine = create_engine(
    shared_settings.database_url_sync,
    pool_pre_ping=True,
    future=True,
)

# expire_on_commit=False lets us read attributes off an object after commit()
# without triggering a fresh SELECT — handy in the engine loop.
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
