from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings


class Base(DeclarativeBase):
    pass


def engine_options_for(
    database_url: str,
    *,
    connect_timeout_seconds: int,
    pool_timeout_seconds: int,
) -> dict[str, object]:
    options: dict[str, object] = {"pool_pre_ping": True}
    if database_url.startswith(("postgresql+psycopg://", "postgresql://")):
        options["connect_args"] = {"connect_timeout": connect_timeout_seconds}
        options["pool_timeout"] = pool_timeout_seconds
    elif database_url.startswith("sqlite"):
        options["connect_args"] = {"check_same_thread": False}
    return options


engine_options = engine_options_for(
    settings.database_url,
    connect_timeout_seconds=settings.database_connect_timeout_seconds,
    pool_timeout_seconds=settings.database_pool_timeout_seconds,
)

engine = create_engine(settings.database_url, **engine_options)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Generator[Session, None, None]:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
