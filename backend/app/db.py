from collections.abc import Iterator
from functools import lru_cache
from pathlib import Path

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import DeclarativeBase, Session

from .config import get_settings


class Base(DeclarativeBase):
    pass


def start_dev_database(path: Path) -> str:
    """Start (or attach to) a project-local Postgres. Development and tests only."""
    import pixeltable_pgserver

    uri = pixeltable_pgserver.get_server(path.resolve()).get_uri()
    return uri.replace("postgresql://", "postgresql+psycopg://", 1)


@lru_cache
def get_engine() -> Engine:
    settings = get_settings()
    url = settings.database_url or start_dev_database(Path(".devdb"))
    return create_engine(url, pool_pre_ping=True)


def get_db() -> Iterator[Session]:
    with Session(get_engine(), expire_on_commit=False) as session:
        yield session
