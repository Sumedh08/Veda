"""Recompute conservative metadata-gate counts from the preserved ten-case snapshot."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPOSITORY_ROOT / "backend"))

from app.research.candidate_relevance import (  # noqa: E402
    has_clean_bibliographic_title,
    passes_topic_overlap_gate,
)


def audit(batch: dict[str, Any], runtime: dict[str, Any]) -> dict[str, Any]:
    questions = {
        item["job"]["id"]: item.get("question", item["job"].get("question", ""))
        for item in batch.get("results", [])
    }
    totals: Counter[str] = Counter()
    contamination_examples: list[dict[str, str]] = []
    case_counts: list[dict[str, Any]] = []

    for runtime_job in runtime.get("research_jobs", []):
        job = runtime_job.get("job", {})
        question = questions.get(job.get("id"), job.get("question", ""))
        sources = {
            source.get("id"): source for source in runtime_job.get("sources", {}).get("items", [])
        }
        case = Counter()
        for candidate in runtime_job.get("candidates", {}).get("items", []):
            totals["candidate_occurrences"] += 1
            case["candidate_occurrences"] += 1
            selected = candidate.get("disposition") == "selected"
            title = candidate.get("title") or ""
            clean_title = has_clean_bibliographic_title(title)
            if selected:
                totals["historically_selected_occurrences"] += 1
                case["historically_selected_occurrences"] += 1
            if not clean_title:
                totals["malformed_title_occurrences"] += 1
                case["malformed_title_occurrences"] += 1
                if selected:
                    totals["selected_malformed_title_occurrences"] += 1
                    case["selected_malformed_title_occurrences"] += 1
                if len(contamination_examples) < 8:
                    contamination_examples.append(
                        {
                            "candidate_id": str(candidate.get("provider_record_id", "unknown")),
                            "title_excerpt": title[:240],
                        }
                    )
                continue

            if passes_topic_overlap_gate(question, title, None):
                totals["clean_title_only_gate_passes"] += 1
                case["clean_title_only_gate_passes"] += 1

            if selected:
                source = sources.get(candidate.get("canonical_source_id"), {})
                if passes_topic_overlap_gate(question, title, source.get("abstract_excerpt")):
                    totals["selected_clean_records_passing_gate"] += 1
                    case["selected_clean_records_passing_gate"] += 1
                else:
                    totals["selected_clean_records_rejected_for_topic_overlap"] += 1
                    case["selected_clean_records_rejected_for_topic_overlap"] += 1

        case_counts.append(
            {
                "job_id": job.get("id"),
                "question": question,
                **dict(case),
            }
        )

    return {
        "schema_version": 1,
        "artifact": "evaluation/openrouter-live-runtime-snapshot-20261029.json",
        "paired_batch_artifact": "evaluation/openrouter-live-batch-20261029T155042Z.json",
        "method": "Reapply current deterministic title-integrity and lexical topic filters to saved candidate titles; selected records can also use their saved abstract excerpt.",
        "counts": dict(totals),
        "malformed_title_examples": contamination_examples,
        "per_case": case_counts,
        "interpretation_limits": [
            "Candidate occurrences are not unique papers; the same record can appear in multiple queries or jobs.",
            "Nonselected candidate abstracts are not present in the saved runtime snapshot, so the title-only pass count is not a replay of the full discovery gate.",
            "Selected records have saved abstracts; rejection counts are deterministic filter outcomes, not human relevance judgments.",
            "No precision, recall, false-positive rate, or scientific quality score can be calculated without reviewed labels.",
        ],
        "manual_regression_examples": {
            "false_positive_blocked": "The sPHENIX fast-data-processing/detector-control title previously passed via generic AI, processing and time overlap; the query-context filter now rejects it.",
            "adjacent_synonym_recovered": "Designing and Evaluating Generative AI Search Tools for Human Cognitive Augmentation now passes a knowledge-retrieval query via direct title term search plus generative-AI intervention match; the paper's topical adequacy remains unverified because its abstract was not in that snapshot.",
        },
    }


def markdown(result: dict[str, Any]) -> str:
    counts = result["counts"]
    lines = [
        "# Offline retrieval-filter replay",
        "",
        "This is a deterministic replay over preserved metadata, not a labeled relevance benchmark.",
        "",
        "## Counts",
        "",
    ]
    lines.extend(f"- `{key}`: {value}" for key, value in sorted(counts.items()))
    lines.extend(["", "## Contaminated title examples", ""])
    lines.extend(
        f"- `{item['candidate_id']}`: {item['title_excerpt']}"
        for item in result["malformed_title_examples"]
    )
    lines.extend(["", "## Regression review", ""])
    lines.extend(
        f"- **{label.replace('_', ' ')}:** {description}"
        for label, description in result["manual_regression_examples"].items()
    )
    lines.extend(["", "## Limits", ""])
    lines.extend(f"- {limit}" for limit in result["interpretation_limits"])
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--batch",
        type=Path,
        default=REPOSITORY_ROOT / "evaluation/openrouter-live-batch-20261029T155042Z.json",
    )
    parser.add_argument(
        "--runtime",
        type=Path,
        default=REPOSITORY_ROOT / "evaluation/openrouter-live-runtime-snapshot-20261029.json",
    )
    parser.add_argument(
        "--json-out",
        type=Path,
        default=REPOSITORY_ROOT / "evaluation/retrieval-overlap-audit-2026-10-30.json",
    )
    parser.add_argument(
        "--markdown-out",
        type=Path,
        default=REPOSITORY_ROOT / "evaluation/retrieval-overlap-audit-2026-10-30.md",
    )
    args = parser.parse_args()
    result = audit(
        json.loads(args.batch.read_text(encoding="utf-8")),
        json.loads(args.runtime.read_text(encoding="utf-8")),
    )
    args.json_out.write_text(
        json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    args.markdown_out.write_text(markdown(result), encoding="utf-8")
    print(
        f"Wrote replay audit for {result['counts'].get('candidate_occurrences', 0)} candidate occurrences"
    )


if __name__ == "__main__":
    main()
