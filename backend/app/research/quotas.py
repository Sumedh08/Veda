import math
from datetime import UTC, date, datetime

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.models import DailyModelQuota, ModelCallReservation, Project, ResearchJob, utcnow

GLOBAL_QUOTA_ID = "all-users"


class ModelCallQuotaExceeded(Exception):
    def __init__(self, scope: str):
        super().__init__(scope)
        self.scope = scope


def _owner_id(db: Session, job_id: str) -> str | None:
    return db.scalar(
        select(Project.owner_id)
        .join(ResearchJob, ResearchJob.project_id == Project.id)
        .where(ResearchJob.id == job_id)
    )


def _ensure_counter(db: Session, *, scope: str, scope_id: str, quota_date: date) -> None:
    dialect = db.get_bind().dialect.name
    values = {
        "scope": scope,
        "scope_id": scope_id,
        "quota_date": quota_date,
        "calls_used": 0,
        "created_at": utcnow(),
        "updated_at": utcnow(),
    }
    if dialect == "sqlite":
        statement = sqlite_insert(DailyModelQuota).values(**values)
    elif dialect == "postgresql":
        statement = postgresql_insert(DailyModelQuota).values(**values)
    else:
        raise RuntimeError(
            f"Atomic model-call quotas are unsupported for database dialect {dialect}."
        )
    db.execute(statement.on_conflict_do_nothing(index_elements=["scope", "scope_id", "quota_date"]))


def daily_model_call_blocker(
    db: Session,
    *,
    job_id: str,
    global_limit: int,
    per_user_limit: int,
    now: datetime | None = None,
) -> str | None:
    owner_id = _owner_id(db, job_id)
    if owner_id is None:
        return "the research job owner could not be checked"
    today = (now or datetime.now(UTC)).astimezone(UTC).date()
    counters = (
        (
            "global",
            GLOBAL_QUOTA_ID,
            global_limit,
            "Veda's global daily model-call limit has been reached",
        ),
        ("user", owner_id, per_user_limit, "This user's daily model-call limit has been reached"),
    )
    for scope, scope_id, limit, message in counters:
        used = db.scalar(
            select(DailyModelQuota.calls_used).where(
                DailyModelQuota.scope == scope,
                DailyModelQuota.scope_id == scope_id,
                DailyModelQuota.quota_date == today,
            )
        )
        if limit <= 0 or (used is not None and used >= limit):
            return message
    return None


def daily_model_call_capacity(
    db: Session,
    *,
    job_id: str,
    global_limit: int,
    per_user_limit: int,
    now: datetime | None = None,
) -> tuple[int, str | None]:
    """Return the conservative remaining daily slots for a pre-dispatch plan.

    The atomic reservation remains authoritative because another job can consume a
    slot after this read. This snapshot is for transparent planning only.
    """
    snapshot = daily_model_quota_snapshot(
        db,
        job_id=job_id,
        global_limit=global_limit,
        per_user_limit=per_user_limit,
        now=now,
    )
    if snapshot is None:
        return 0, "the research job owner could not be checked"
    capacity = snapshot["available_calls"]
    if capacity == 0:
        return capacity, "a global or per-user daily request quota is exhausted"
    return capacity, None


def daily_model_quota_snapshot(
    db: Session,
    *,
    job_id: str,
    global_limit: int,
    per_user_limit: int,
    now: datetime | None = None,
) -> dict[str, int | str] | None:
    """Return safe, owner-anonymous daily quota counts for a pre-dispatch plan.

    Counts are a transparent snapshot only. ``reserve_daily_model_call`` still
    performs the atomic check immediately before each provider dispatch.
    """
    owner_id = _owner_id(db, job_id)
    if owner_id is None:
        return None
    today = (now or datetime.now(UTC)).astimezone(UTC).date()
    values: dict[str, int | str] = {"utc_date": today.isoformat()}
    remaining: list[int] = []
    for scope, scope_id, prefix, limit in (
        ("global", GLOBAL_QUOTA_ID, "global", global_limit),
        ("user", owner_id, "per_user", per_user_limit),
    ):
        used_value = db.scalar(
            select(DailyModelQuota.calls_used).where(
                DailyModelQuota.scope == scope,
                DailyModelQuota.scope_id == scope_id,
                DailyModelQuota.quota_date == today,
            )
        )
        used = max(0, used_value or 0)
        available = max(0, limit - used)
        values[f"{prefix}_limit"] = limit
        values[f"{prefix}_used"] = used
        values[f"{prefix}_remaining"] = available
        remaining.append(available)
    values["available_calls"] = min(remaining)
    return values


def reserve_daily_model_call(
    db: Session,
    *,
    job_id: str,
    operation: str,
    attempt: int,
    provider: str,
    model_name: str | None,
    request_hash: str | None = None,
    reserved_cost_usd: float = 0.0,
    reserved_cost_inr: float = 0.0,
    max_job_cost_inr: float | None = None,
    prompt_characters: int = 0,
    prompt_token_upper_bound: int = 0,
    output_token_cap: int = 0,
    max_job_model_calls: int | None = None,
    max_job_prompt_characters: int | None = None,
    max_job_prompt_token_budget: int | None = None,
    max_job_output_token_budget: int | None = None,
    global_limit: int,
    per_user_limit: int,
    now: datetime | None = None,
) -> ModelCallReservation:
    """Atomically consume one global and per-user daily call slot before dispatch."""
    if not math.isfinite(reserved_cost_usd) or reserved_cost_usd < 0:
        raise ValueError("Reserved model cost must be finite and non-negative")
    if not math.isfinite(reserved_cost_inr) or reserved_cost_inr < 0:
        raise ValueError("Reserved INR model cost must be finite and non-negative")
    if max_job_cost_inr is not None and (
        not math.isfinite(max_job_cost_inr) or max_job_cost_inr < 0
    ):
        raise ValueError("Per-job INR budget must be finite and non-negative")
    if prompt_characters < 0 or prompt_token_upper_bound < 0 or output_token_cap < 0:
        raise ValueError("Model request character and token reservations must be non-negative")
    owner_id = _owner_id(db, job_id)
    if owner_id is None:
        raise ModelCallQuotaExceeded("owner_unavailable")
    today = (now or datetime.now(UTC)).astimezone(UTC).date()
    scopes = (
        ("global", GLOBAL_QUOTA_ID, global_limit),
        ("user", owner_id, per_user_limit),
    )
    try:
        job_budget_filters = [
            ResearchJob.id == job_id,
            ResearchJob.cost_spent_estimate_usd + ResearchJob.cost_reserved_usd + reserved_cost_usd
            <= ResearchJob.budget_ceiling_usd,
        ]
        if max_job_cost_inr is not None:
            job_budget_filters.append(
                ResearchJob.cost_spent_estimate_inr
                + ResearchJob.cost_reserved_inr
                + reserved_cost_inr
                <= max_job_cost_inr
            )
        job_budget = db.execute(
            update(ResearchJob)
            .where(*job_budget_filters)
            .values(
                cost_reserved_usd=ResearchJob.cost_reserved_usd + reserved_cost_usd,
                cost_reserved_inr=ResearchJob.cost_reserved_inr + reserved_cost_inr,
            )
        )
        if job_budget.rowcount != 1:
            raise ModelCallQuotaExceeded("job_budget")
        profile_limits = [ResearchJob.id == job_id]
        if max_job_model_calls is not None:
            profile_limits.append(ResearchJob.model_calls_reserved < max_job_model_calls)
        if max_job_prompt_characters is not None:
            profile_limits.append(
                ResearchJob.prompt_characters_reserved + prompt_characters
                <= max_job_prompt_characters
            )
        if max_job_prompt_token_budget is not None:
            profile_limits.append(
                ResearchJob.prompt_token_budget_reserved + prompt_token_upper_bound
                <= max_job_prompt_token_budget
            )
        if max_job_output_token_budget is not None:
            profile_limits.append(
                ResearchJob.output_token_budget_reserved + output_token_cap
                <= max_job_output_token_budget
            )
        profile_reservation = db.execute(
            update(ResearchJob)
            .where(*profile_limits)
            .values(
                model_calls_reserved=ResearchJob.model_calls_reserved + 1,
                prompt_characters_reserved=(
                    ResearchJob.prompt_characters_reserved + prompt_characters
                ),
                prompt_token_budget_reserved=(
                    ResearchJob.prompt_token_budget_reserved + prompt_token_upper_bound
                ),
                output_token_budget_reserved=(
                    ResearchJob.output_token_budget_reserved + output_token_cap
                ),
            )
        )
        if profile_reservation.rowcount != 1:
            used = db.execute(
                select(
                    ResearchJob.model_calls_reserved,
                    ResearchJob.prompt_characters_reserved,
                    ResearchJob.prompt_token_budget_reserved,
                    ResearchJob.output_token_budget_reserved,
                ).where(ResearchJob.id == job_id)
            ).one_or_none()
            if used is None:
                raise ModelCallQuotaExceeded("owner_unavailable")
            calls_used, prompt_used, prompt_tokens_used, output_used = used
            if max_job_model_calls is not None and calls_used >= max_job_model_calls:
                raise ModelCallQuotaExceeded("depth_model_calls")
            if (
                max_job_prompt_characters is not None
                and prompt_used + prompt_characters > max_job_prompt_characters
            ):
                raise ModelCallQuotaExceeded("depth_prompt_characters")
            if (
                max_job_prompt_token_budget is not None
                and prompt_tokens_used + prompt_token_upper_bound > max_job_prompt_token_budget
            ):
                raise ModelCallQuotaExceeded("depth_prompt_tokens")
            if (
                max_job_output_token_budget is not None
                and output_used + output_token_cap > max_job_output_token_budget
            ):
                raise ModelCallQuotaExceeded("depth_output_tokens")
            raise ModelCallQuotaExceeded("owner_unavailable")
        for scope, scope_id, _limit in scopes:
            _ensure_counter(db, scope=scope, scope_id=scope_id, quota_date=today)
        for scope, scope_id, limit in scopes:
            result = db.execute(
                update(DailyModelQuota)
                .where(
                    DailyModelQuota.scope == scope,
                    DailyModelQuota.scope_id == scope_id,
                    DailyModelQuota.quota_date == today,
                    DailyModelQuota.calls_used < limit,
                )
                .values(calls_used=DailyModelQuota.calls_used + 1, updated_at=utcnow())
            )
            if result.rowcount != 1:
                raise ModelCallQuotaExceeded(scope)
        reservation = ModelCallReservation(
            job_id=job_id,
            user_id=owner_id,
            operation=operation[:80],
            attempt=max(0, attempt),
            provider=provider[:40],
            model_name=model_name[:160] if model_name else None,
            request_hash=request_hash,
            reserved_cost_usd=reserved_cost_usd,
            reserved_cost_inr=reserved_cost_inr,
            prompt_characters=prompt_characters,
            prompt_token_upper_bound=prompt_token_upper_bound,
            output_token_cap=output_token_cap,
            quota_date=today,
            state="reserved",
        )
        db.add(reservation)
        db.commit()
        db.refresh(reservation)
        return reservation
    except Exception:
        db.rollback()
        raise


def settle_model_call_reservation(
    db: Session,
    *,
    reservation_id: str,
    state: str,
    actual_cost_usd: float | None = None,
    actual_cost_inr: float | None = None,
    error_class: str | None = None,
    now: datetime | None = None,
) -> None:
    if state not in {"succeeded", "failed", "uncertain"}:
        raise ValueError("Invalid model-call reservation state")
    reservation = db.get(ModelCallReservation, reservation_id)
    if reservation is None or reservation.state != "reserved":
        return
    if actual_cost_usd is not None and (not math.isfinite(actual_cost_usd) or actual_cost_usd < 0):
        raise ValueError("Actual model cost must be finite and non-negative")
    if actual_cost_inr is not None and (not math.isfinite(actual_cost_inr) or actual_cost_inr < 0):
        raise ValueError("Actual INR model cost must be finite and non-negative")
    reservation.state = state
    reservation.error_class = error_class[:80] if error_class else None
    reservation.settled_at = now or utcnow()
    if state != "uncertain":
        cost_update = (
            ResearchJob.cost_spent_estimate_usd + actual_cost_usd
            if actual_cost_usd is not None
            else ResearchJob.cost_spent_estimate_usd
        )
        inr_cost_update = (
            ResearchJob.cost_spent_estimate_inr + actual_cost_inr
            if actual_cost_inr is not None
            else ResearchJob.cost_spent_estimate_inr
        )
        db.execute(
            update(ResearchJob)
            .where(ResearchJob.id == reservation.job_id)
            .values(
                cost_reserved_usd=ResearchJob.cost_reserved_usd - reservation.reserved_cost_usd,
                cost_spent_estimate_usd=cost_update,
                cost_reserved_inr=ResearchJob.cost_reserved_inr - reservation.reserved_cost_inr,
                cost_spent_estimate_inr=inr_cost_update,
            )
        )
        reservation.actual_cost_usd = actual_cost_usd
        reservation.actual_cost_inr = actual_cost_inr
