"""Validate benchmark registry completeness without claiming research quality."""

import json
import sys
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "evaluation" / "questions" / "ai_economics_cases.json"
REQUIRED = {
    "case_id",
    "title",
    "question",
    "scope",
    "expected_study_design",
    "counterevidence_query",
    "candidate_primary_sources",
    "source_search_status",
    "rubric_dimensions",
    "gold_answer",
    "status",
}


def validate() -> dict[str, object]:
    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    cases = registry.get("cases")
    errors: list[str] = []
    if not isinstance(cases, list) or not 30 <= len(cases) <= 50:
        errors.append("case count must be between 30 and 50")
        cases = cases if isinstance(cases, list) else []
    ids = [case.get("case_id") for case in cases if isinstance(case, dict)]
    if len(ids) != len(set(ids)):
        errors.append("case IDs must be unique")
    for index, case in enumerate(cases):
        if not isinstance(case, dict):
            errors.append(f"case {index} must be an object")
            continue
        missing = REQUIRED - case.keys()
        if missing:
            errors.append(f"{case.get('case_id', index)} missing {', '.join(sorted(missing))}")
            continue
        if case["status"] not in {"draft", "human_reviewed", "validated"}:
            errors.append(f"{case['case_id']} has invalid status")
        if case["status"] == "draft" and case["gold_answer"] is not None:
            errors.append(f"draft case {case['case_id']} must not contain a gold answer")
        if not case["expected_study_design"] or not case["counterevidence_query"]:
            errors.append(f"{case['case_id']} needs study-design and counterevidence guidance")
        if not isinstance(case["candidate_primary_sources"], list):
            errors.append(f"{case['case_id']} candidate sources must be a list")
    counts = Counter(case.get("status", "invalid") for case in cases if isinstance(case, dict))
    return {
        "registry_validation": "passed" if not errors else "failed",
        "case_count": len(cases),
        "status_counts": dict(sorted(counts.items())),
        "gold_answers_present": sum(case.get("gold_answer") is not None for case in cases if isinstance(case, dict)),
        "research_quality_evaluated": False,
        "errors": errors,
    }


if __name__ == "__main__":
    result = validate()
    print(json.dumps(result, indent=2))
    sys.exit(0 if result["registry_validation"] == "passed" else 1)
