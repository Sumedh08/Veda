import json
import subprocess
import sys
from pathlib import Path


def test_fixture_runner_reproduces_metrics_without_scoring_draft_cases():
    repository_root = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        [sys.executable, str(repository_root / "scripts" / "evaluate_fixtures.py")],
        cwd=repository_root,
        check=True,
        capture_output=True,
        text=True,
    )
    repeated_result = subprocess.run(
        [sys.executable, str(repository_root / "scripts" / "evaluate_fixtures.py")],
        cwd=repository_root,
        check=True,
        capture_output=True,
        text=True,
    )
    report = json.loads(result.stdout)
    assert json.loads(repeated_result.stdout) == report

    assert report["evaluation_status"] == "passed"
    assert report["evaluation_type"] == "synthetic_fixture_metric_logic"
    assert report["fixture_cases"] == 1
    assert report["draft_registry_case_status_counts"] == {"draft": 36}
    assert report["draft_registry_gold_answers_present"] == 0
    assert report["scientific_quality_scored"] is False
    assert report["provider_calls"] == 0
    assert report["database"] == "none"
    assert report["metrics"]["passage_support_label_accuracy"] == {
        "numerator": 2,
        "denominator": 3,
        "rate": 0.666667,
    }
    assert report["metrics"]["citation_link_integrity"] == {
        "numerator": 3,
        "denominator": 4,
        "rate": 0.75,
    }
    assert report["metrics"]["scope_safe_relationship_classification"]["rate"] == 0.8
    assert report["metrics"]["competing_hypothesis_evidence_disjointness"]["rate"] == 0.333333
    assert report["metrics"]["provider_call_budget_compliance"]["rate"] == 0.666667
