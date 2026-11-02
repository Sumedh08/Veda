"""Versioned, sanitized retrieval attempt outcomes for source records."""

from __future__ import annotations

import re
from collections.abc import Mapping
from datetime import datetime
from math import isfinite
from typing import Literal

from app.schemas import RetrievalAttemptOutcomeV1

_FORMATS = ("html", "pdf", "jats")
_CODE = re.compile(r"^[a-z0-9_]{1,64}$")


def _safe_code(value: object) -> str | None:
    return value if isinstance(value, str) and _CODE.fullmatch(value) else None


def _safe_retry_after(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if not isfinite(value) or value < 0 or value > 86_400:
        return None
    return float(value)


def _outcome_for_status(status: object, *, truncated: object = False) -> str:
    if status == "retrieved":
        return "partial" if truncated is True else "retrieved"
    if status == "deferred":
        return "deferred"
    if status == "failed":
        return "error"
    if status == "unsupported":
        return "unavailable"
    return "not_attempted"


def record_attempt_outcome(
    metadata: dict,
    *,
    format: Literal["html", "pdf", "jats"],
    outcome: Literal["not_attempted", "retrieved", "partial", "unavailable", "error", "deferred"],
    observed_at: datetime | str | None = None,
    reason_code: str | None = None,
    error_code: str | None = None,
    retry_after_seconds: float | None = None,
    truncated: bool | None = None,
) -> None:
    """Persist one strict outcome row without raw URLs, bodies or exception text."""
    row = RetrievalAttemptOutcomeV1(
        schema_version=1,
        format=format,
        outcome=outcome,
        observed_at=observed_at,
        reason_code=_safe_code(reason_code),
        error_code=_safe_code(error_code),
        retry_after_seconds=_safe_retry_after(retry_after_seconds),
        truncated=truncated,
    ).model_dump(mode="json", exclude_none=True)
    raw_envelope = metadata.get("outcomes")
    envelope = dict(raw_envelope) if isinstance(raw_envelope, Mapping) else {}
    raw_formats = envelope.get("by_format")
    by_format = dict(raw_formats) if isinstance(raw_formats, Mapping) else {}
    by_format[format] = row
    metadata["outcomes"] = {"schema_version": 1, "by_format": by_format}


def record_status_outcome(
    metadata: dict,
    *,
    format: Literal["html", "pdf", "jats"],
    status: object,
    observed_at: datetime | str | None = None,
    reason_code: str | None = None,
    error_code: str | None = None,
    retry_after_seconds: float | None = None,
    truncated: bool | None = None,
) -> None:
    """Translate the legacy fetch status into the public versioned taxonomy."""
    record_attempt_outcome(
        metadata,
        format=format,
        outcome=_outcome_for_status(status, truncated=truncated),
        observed_at=observed_at,
        reason_code=reason_code,
        error_code=error_code,
        retry_after_seconds=retry_after_seconds,
        truncated=truncated if isinstance(truncated, bool) else None,
    )


def retrieval_metadata_for_api(value: object, retrieval_status: str) -> dict:
    """Add versioned outcomes to legacy retrieval JSON without inventing timestamps."""
    metadata = dict(value) if isinstance(value, Mapping) else {}
    for key in ("error_code", "reason"):
        if key in metadata:
            safe_value = _safe_code(metadata[key])
            if safe_value is None:
                metadata.pop(key, None)
            else:
                metadata[key] = safe_value
    if "retry_after_seconds" in metadata:
        safe_retry = _safe_retry_after(metadata["retry_after_seconds"])
        if safe_retry is None:
            metadata.pop("retry_after_seconds", None)
        else:
            metadata["retry_after_seconds"] = safe_retry
    if isinstance(metadata.get("pdf"), Mapping):
        pdf_metadata = dict(metadata["pdf"])
        for key in ("error_code", "reason"):
            if key in pdf_metadata:
                safe_value = _safe_code(pdf_metadata[key])
                if safe_value is None:
                    pdf_metadata.pop(key, None)
                else:
                    pdf_metadata[key] = safe_value
        if "retry_after_seconds" in pdf_metadata:
            safe_retry = _safe_retry_after(pdf_metadata["retry_after_seconds"])
            if safe_retry is None:
                pdf_metadata.pop("retry_after_seconds", None)
            else:
                pdf_metadata["retry_after_seconds"] = safe_retry
        metadata["pdf"] = pdf_metadata
    raw_envelope = metadata.get("outcomes")
    raw_formats = raw_envelope.get("by_format") if isinstance(raw_envelope, Mapping) else None
    by_format: dict[str, dict] = {}
    if isinstance(raw_formats, Mapping):
        for format in _FORMATS:
            raw_row = raw_formats.get(format)
            if isinstance(raw_row, Mapping) and raw_row.get("format") == format:
                try:
                    by_format[format] = RetrievalAttemptOutcomeV1.model_validate(
                        raw_row
                    ).model_dump(mode="json", exclude_none=True)
                except Exception:
                    # An invalid/legacy extension is omitted from the public contract.
                    continue

    # Pre-taxonomy records get a lossless status mapping at read time. The original JSON
    # remains untouched and a missing timestamp stays missing.
    root_status = metadata.get("status")
    raw_format = metadata.get("format")
    root_format = raw_format if raw_format in _FORMATS else "html"
    legacy_statuses = {"retrieved", "failed", "deferred", "unsupported", "not_attempted"}
    if (
        isinstance(root_status, str)
        and root_status in legacy_statuses
        and root_format not in by_format
    ):
        by_format[root_format] = _legacy_outcome(metadata, root_format)
    pdf = metadata.get("pdf")
    if (
        isinstance(pdf, Mapping)
        and isinstance(pdf.get("status"), str)
        and pdf.get("status") in legacy_statuses
        and "pdf" not in by_format
    ):
        by_format["pdf"] = _legacy_outcome(pdf, "pdf")
    if not by_format and retrieval_status in {"full_text_html", "full_text_pdf", "full_text_jats"}:
        format = {
            "full_text_pdf": "pdf",
            "full_text_jats": "jats",
        }.get(retrieval_status, "html")
        truncated = metadata.get("truncated")
        by_format[format] = RetrievalAttemptOutcomeV1(
            schema_version=1,
            format=format,
            outcome=("partial" if truncated is True else "retrieved"),
            observed_at=metadata.get("retrieved_at"),
            truncated=truncated if isinstance(truncated, bool) else None,
        ).model_dump(mode="json", exclude_none=True)

    metadata["outcomes"] = {"schema_version": 1, "by_format": by_format}
    return metadata


def _legacy_outcome(raw: Mapping, format: Literal["html", "pdf", "jats"]) -> dict:
    status = raw.get("status")
    truncated = raw.get("truncated")
    retry_after = raw.get("retry_after_seconds")
    retry_after = _safe_retry_after(retry_after)
    try:
        return RetrievalAttemptOutcomeV1(
            schema_version=1,
            format=format,
            outcome=_outcome_for_status(status, truncated=truncated),
            observed_at=raw.get("retrieved_at"),
            reason_code=_safe_code(raw.get("reason")),
            error_code=_safe_code(raw.get("error_code")),
            retry_after_seconds=retry_after,
            truncated=truncated if isinstance(truncated, bool) else None,
        ).model_dump(mode="json", exclude_none=True)
    except Exception:
        return RetrievalAttemptOutcomeV1(
            schema_version=1,
            format=format,
            outcome=_outcome_for_status(status, truncated=truncated),
        ).model_dump(mode="json", exclude_none=True)
