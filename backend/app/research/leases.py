from datetime import datetime, timedelta

from sqlalchemy import or_, update
from sqlalchemy.orm import Session

from app.models import ResearchJob


def acquire_job_lease(
    db: Session,
    *,
    job_id: str,
    expected_version: int,
    lease_token: str,
    now: datetime,
    lease_seconds: int = 180,
) -> bool:
    """Atomically acquire an empty/expired lease at the caller's observed version."""
    result = db.execute(
        update(ResearchJob)
        .where(
            ResearchJob.id == job_id,
            ResearchJob.version == expected_version,
            or_(ResearchJob.lease_expires_at.is_(None), ResearchJob.lease_expires_at < now),
        )
        .values(
            lease_owner=lease_token,
            lease_expires_at=now + timedelta(seconds=lease_seconds),
            status="active",
            version=ResearchJob.version + 1,
            updated_at=now,
        )
    )
    return result.rowcount == 1
