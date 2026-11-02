import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine

from app.config import Settings
from app.db import engine_options_for


def test_postgres_engine_uses_bounded_connect_and_pool_timeouts():
    options = engine_options_for(
        "postgresql+psycopg://veda:secret@db.example/veda",
        connect_timeout_seconds=7,
        pool_timeout_seconds=11,
    )

    assert options["connect_args"] == {"connect_timeout": 7}
    assert options["pool_timeout"] == 11
    engine = create_engine(
        "postgresql+psycopg://veda:secret@127.0.0.1:1/veda",
        **options,
    )
    try:
        assert engine.pool._timeout == 11
        actual_connect_args = {}

        def capture_connect_args(*_args, **kwargs):
            actual_connect_args.update(kwargs)
            raise RuntimeError("stop before any network connection")

        engine.dialect.connect = capture_connect_args
        with pytest.raises(RuntimeError, match="stop before any network connection"):
            engine.pool._creator()
        assert actual_connect_args["connect_timeout"] == 7
    finally:
        engine.dispose()


def test_sqlite_engine_keeps_sqlite_connection_options_only():
    options = engine_options_for(
        "sqlite:///./veda.db",
        connect_timeout_seconds=7,
        pool_timeout_seconds=11,
    )

    assert options == {
        "pool_pre_ping": True,
        "connect_args": {"check_same_thread": False},
    }


def test_engine_timeout_inputs_are_bounded_by_settings():
    for field in ("database_connect_timeout_seconds", "database_pool_timeout_seconds"):
        with pytest.raises(ValidationError):
            Settings(**{field: 0})
