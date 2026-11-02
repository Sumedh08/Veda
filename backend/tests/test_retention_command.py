import sys
from datetime import UTC, datetime, timedelta

from sqlalchemy import create_engine, select
from sqlalchemy.engine import URL
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.maintenance import purge_expired_projects as retention_command
from app.models import Project


def test_retention_command_previews_by_default_and_applies_only_due_archived_projects(
    monkeypatch, capsys, tmp_path
):
    engine = create_engine(
        URL.create("sqlite", database=str(tmp_path / "retention-command.sqlite3")),
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    now = datetime.now(UTC)
    records = [
        Project(
            owner_id="retention-command-test-user",
            title="Due archived 1",
            domain="test",
            archived_at=now - timedelta(days=31),
            purge_at=now - timedelta(seconds=2),
        ),
        Project(
            owner_id="retention-command-test-user",
            title="Due archived 2",
            domain="test",
            archived_at=now - timedelta(days=31),
            purge_at=now - timedelta(seconds=1),
        ),
        Project(
            owner_id="retention-command-test-user",
            title="Future archived",
            domain="test",
            archived_at=now - timedelta(days=2),
            purge_at=now + timedelta(days=1),
        ),
        Project(
            owner_id="retention-command-test-user",
            title="Never expires",
            domain="test",
            archived_at=now - timedelta(days=365),
            purge_at=None,
        ),
        Project(
            owner_id="retention-command-test-user",
            title="Active with stale purge time",
            domain="test",
            archived_at=None,
            purge_at=now - timedelta(days=1),
        ),
    ]
    try:
        with sessions() as db:
            db.add_all(records)
            db.commit()
        monkeypatch.setattr(retention_command, "SessionLocal", sessions)

        monkeypatch.setattr(sys, "argv", ["purge_expired_projects", "--batch-size", "1"])
        retention_command.main()
        assert capsys.readouterr().out.strip() == (
            "Dry run: 2 expired archived project(s) are eligible for purge."
        )
        with sessions() as db:
            assert db.scalar(select(Project.title).where(Project.title == "Due archived 1"))
            assert db.scalar(select(Project.title).where(Project.title == "Due archived 2"))

        monkeypatch.setattr(sys, "argv", ["purge_expired_projects", "--apply", "--batch-size", "1"])
        retention_command.main()
        assert (
            capsys.readouterr().out.strip() == "Permanently deleted 2 expired archived project(s)."
        )

        with sessions() as db:
            remaining_titles = set(db.scalars(select(Project.title)).all())
            assert remaining_titles == {
                "Future archived",
                "Never expires",
                "Active with stale purge time",
            }

        retention_command.main()
        assert (
            capsys.readouterr().out.strip() == "Permanently deleted 0 expired archived project(s)."
        )
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()
