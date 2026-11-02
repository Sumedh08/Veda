"""Idempotent archived-project expiry logic for a deployment-scheduled command."""

from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Project


def _cutoff(now: datetime | None) -> datetime:
    current = now or datetime.now(UTC)
    if current.tzinfo is None:
        raise ValueError("Retention cutoff must be timezone-aware")
    return current


def count_expired_projects(db: Session, *, now: datetime | None = None) -> int:
    cutoff = _cutoff(now)
    return int(
        db.scalar(
            select(func.count())
            .select_from(Project)
            .where(
                Project.archived_at.is_not(None),
                Project.purge_at.is_not(None),
                Project.purge_at <= cutoff,
            )
        )
        or 0
    )


def purge_expired_projects(
    db: Session, *, now: datetime | None = None, batch_size: int = 100
) -> int:
    """Delete due archived projects in locked, bounded, idempotent batches."""
    cutoff = _cutoff(now)
    if not 1 <= batch_size <= 1000:
        raise ValueError("Retention batch_size must be between 1 and 1000")

    deleted = 0
    while True:
        projects = list(
            db.scalars(
                select(Project)
                .where(
                    Project.archived_at.is_not(None),
                    Project.purge_at.is_not(None),
                    Project.purge_at <= cutoff,
                )
                .order_by(Project.purge_at, Project.id)
                .limit(batch_size)
                .with_for_update(skip_locked=True)
            ).all()
        )
        if not projects:
            return deleted
        for project in projects:
            db.delete(project)
        db.commit()
        deleted += len(projects)
