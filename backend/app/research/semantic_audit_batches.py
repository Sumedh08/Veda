"""Bounded, provenance-preserving batches for semantic report review."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel

from app.providers.llm import maximum_input_token_estimate

MAX_ITEMS_PER_BATCH = 8
SCAN_OVERLAP_CHARS = 280
MIN_NONFINAL_SCAN_CHARS = 512
MAX_PLANNED_BATCHES = 128


@dataclass(frozen=True)
class SemanticAuditBatch:
    batch_id: str
    user: str
    item_ids: tuple[str, ...]
    scan_start: int
    scan_end: int


@dataclass(frozen=True)
class SemanticAuditBatchPlan:
    batches: tuple[SemanticAuditBatch, ...]
    skipped_item_ids: tuple[str, ...]
    uncovered_scan_start: int | None


def _safe_chunk_end(text: str, start: int, maximum_end: int) -> int:
    """Prefer line/sentence boundaries while retaining exact contiguous coverage."""
    if maximum_end >= len(text):
        return len(text)
    available = maximum_end - start
    floor = start + max(1, available * 2 // 3)
    candidates = [text.rfind("\n", floor, maximum_end), text.rfind(" ", floor, maximum_end)]
    for match in re.finditer(r"[.!?](?:\s|$)", text[floor:maximum_end]):
        candidates.append(floor + match.end() - 1)
    valid = [position + 1 for position in candidates if position >= floor]
    return max(valid) if valid else maximum_end


def plan_semantic_audit_batches(
    *,
    system: str,
    audit_items: list[dict[str, Any]],
    scan_text: str,
    max_prompt_characters: int,
    max_prompt_tokens: int,
    schema_name: str,
    schema_model: type[BaseModel],
) -> SemanticAuditBatchPlan:
    """Partition without dropping passages or report text; overlaps protect quote boundaries."""
    batches: list[SemanticAuditBatch] = []
    skipped: list[str] = []
    item_index = 0
    scan_start = 0

    def make_user(batch_id: str, items: list[dict[str, Any]], start: int, end: int) -> str:
        return json.dumps(
            {
                "audit_batch_id": batch_id,
                "scan_start": start,
                "scan_end": end,
                "items_for_passage_support_review": items,
                "report_text_for_uncited_material_claim_scan": scan_text[start:end],
            },
            ensure_ascii=False,
        )

    def fits(user: str) -> bool:
        if len(system) + len(user) > max_prompt_characters:
            return False
        return (
            maximum_input_token_estimate(
                system, user, schema_name=schema_name, schema_model=schema_model
            )
            <= max_prompt_tokens
        )

    while item_index < len(audit_items) or scan_start < len(scan_text):
        if len(batches) >= MAX_PLANNED_BATCHES:
            return SemanticAuditBatchPlan(tuple(batches), tuple(skipped), scan_start)
        batch_id = f"SA{len(batches) + 1:03d}"
        selected: list[dict[str, Any]] = []
        while item_index < len(audit_items) and len(selected) < MAX_ITEMS_PER_BATCH:
            candidate = [*selected, audit_items[item_index]]
            if fits(make_user(batch_id, candidate, scan_start, scan_start)):
                selected = candidate
                item_index += 1
                continue
            if selected:
                break
            # A single unbounded passage bundle is not silently truncated or assessed.
            skipped.append(str(audit_items[item_index]["item_id"]))
            item_index += 1

        scan_end = scan_start
        if scan_start < len(scan_text):
            low = scan_start
            high = len(scan_text)
            while low < high:
                middle = (low + high + 1) // 2
                if fits(make_user(batch_id, selected, scan_start, middle)):
                    low = middle
                else:
                    high = middle - 1
            maximum_end = low
            remaining = len(scan_text) - scan_start
            if maximum_end > scan_start and (
                maximum_end == len(scan_text) or maximum_end - scan_start >= MIN_NONFINAL_SCAN_CHARS
            ):
                scan_end = _safe_chunk_end(scan_text, scan_start, maximum_end)
                if scan_end <= scan_start:
                    scan_end = maximum_end
            elif not selected and maximum_end > scan_start:
                # A short final tail is still scanned; non-final fragments are kept with
                # the following chunk so statements are not needlessly split.
                if maximum_end == len(scan_text) or remaining <= MIN_NONFINAL_SCAN_CHARS:
                    scan_end = maximum_end

        if not selected and scan_end == scan_start:
            return SemanticAuditBatchPlan(tuple(batches), tuple(skipped), scan_start)
        user = make_user(batch_id, selected, scan_start, scan_end)
        if not fits(user):
            return SemanticAuditBatchPlan(tuple(batches), tuple(skipped), scan_start)
        batches.append(
            SemanticAuditBatch(
                batch_id=batch_id,
                user=user,
                item_ids=tuple(str(item["item_id"]) for item in selected),
                scan_start=scan_start,
                scan_end=scan_end,
            )
        )
        if scan_end > scan_start:
            if scan_end == len(scan_text):
                scan_start = scan_end
            else:
                scan_start = scan_end - min(SCAN_OVERLAP_CHARS, (scan_end - scan_start) // 2)

    return SemanticAuditBatchPlan(tuple(batches), tuple(skipped), None)
