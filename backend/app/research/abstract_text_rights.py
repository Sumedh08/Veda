"""Fail-closed checks for retaining or displaying bibliographic abstract text."""

from __future__ import annotations

import re
from hashlib import sha256
from typing import Any

WITHHELD_ABSTRACT_TEXT = "[Abstract text withheld: item/version reuse permission for storage and display was not recorded.]"
WITHHELD_CLAIM_TEXT = (
    "[Abstract-derived claim withheld: item/version reuse permission was not recorded.]"
)
WITHHELD_COMPARISON_TEXT = (
    "[Abstract-derived comparison text withheld: item/version reuse permission was not recorded.]"
)
WITHHELD_HYPOTHESIS_TEXT = (
    "[Abstract-derived hypothesis text withheld: item/version reuse permission was not recorded.]"
)


def abstract_text_reuse_permitted(
    source: Any,
    text: str | None,
    *,
    source_version: str | None = None,
) -> bool:
    """Require a Veda decision bound to the exact work, version, and text hash.

    Provider-level open-data terms, an abstract availability flag, or a legacy
    status string cannot authorize storage/display. No existing adapter writes
    this decision record, so historical abstracts remain withheld by default.
    """
    if not isinstance(text, str) or not text.strip():
        return False
    metadata = source.metadata_json if isinstance(source.metadata_json, dict) else {}
    decision = metadata.get("abstract_text_rights_decision_v1")
    if not isinstance(decision, dict):
        return False

    resolved_version = source_version or metadata.get("abstract_text_version_id")
    evidence_url = decision.get("evidence_url")
    return bool(
        decision.get("schema_version") == 1
        and decision.get("decision") == "PERMITTED"
        and decision.get("scope") == "item_version_text_retention_and_display"
        and decision.get("source_id") == source.id
        and decision.get("source_identity") == source.external_id
        and isinstance(resolved_version, str)
        and resolved_version.strip()
        and decision.get("source_version_id") == resolved_version
        and decision.get("text_sha256") == sha256(text.encode("utf-8")).hexdigest()
        and isinstance(decision.get("license_id"), str)
        and decision["license_id"].strip()
        and isinstance(evidence_url, str)
        and evidence_url.startswith("https://")
        and not re.search(r"[\r\n\x00]", evidence_url)
        and isinstance(decision.get("decided_at"), str)
        and decision["decided_at"].strip()
    )


def passage_abstract_text_reuse_permitted(passage: Any) -> bool:
    """Validate a passage grant against its source and immutable document version."""
    if (
        passage.access_level not in {"abstract_only", "abstract_excerpt"}
        or passage.document is None
    ):
        return False
    source = passage.source
    if source is None:
        return False
    excerpt = source.abstract_excerpt
    if isinstance(excerpt, str) and passage.content not in excerpt:
        return False
    expected_text = excerpt if isinstance(excerpt, str) and excerpt else passage.content
    return abstract_text_reuse_permitted(
        source,
        expected_text,
        source_version=passage.document.source_version,
    )
