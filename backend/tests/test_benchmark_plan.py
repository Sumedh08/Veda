import copy
import json
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPOSITORY_ROOT))

from scripts.validate_benchmark_plan import validate  # noqa: E402


def test_pre_registered_sample_is_fixed_to_existing_draft_cases():
    result = validate()

    assert result["validation"] == "passed"
    assert result["selected_cases"] == 7
    assert result["quality_scores_reported"] is False
    assert "BRYNJOLFSSON-2025-SUPPORT-STUDY" in result["candidate_sources_reused_across_cases"]


def test_selected_sample_has_no_registry_gold_answers():
    plan = json.loads((REPOSITORY_ROOT / "evaluation/benchmark-plan.json").read_text())
    registry = json.loads(
        (REPOSITORY_ROOT / "evaluation/questions/ai_economics_cases.json").read_text()
    )
    cases = {case["case_id"]: case for case in registry["cases"]}
    for selected in plan["cases"]:
        assert cases[selected["case_id"]]["status"] == "draft"
        assert cases[selected["case_id"]]["gold_answer"] is None


def test_source_metadata_screen_is_distinct_from_gold_source_review_and_quality():
    result = validate()

    assert result["candidate_source_metadata_screened"] is True
    assert result["primary_source_review_complete"] is False
    assert result["source_set_finalized"] is False
    assert result["quality_scores_reported"] is False


def test_completed_source_metadata_screen_requires_a_dated_note():
    plan = json.loads((REPOSITORY_ROOT / "evaluation/benchmark-plan.json").read_text())
    changed = copy.deepcopy(plan)
    changed["current_state"]["candidate_source_screen_note"] = "docs/research/missing-note.md"

    errors = validate(changed)["errors"]

    assert any("existing evidence note" in error for error in errors)


def test_validator_source_requires_explicit_access_classification():
    plan = json.loads((REPOSITORY_ROOT / "evaluation/benchmark-plan.json").read_text())
    changed = copy.deepcopy(plan)
    changed["cases"][0]["candidate_primary_sources"][0]["access_status"] = ""
    errors = validate(changed)["errors"]
    assert any("explicit access status" in error for error in errors)


def test_validator_rejects_selecting_a_case_more_than_once():
    plan = json.loads((REPOSITORY_ROOT / "evaluation/benchmark-plan.json").read_text())
    changed = copy.deepcopy(plan)
    changed["cases"][1]["case_id"] = changed["cases"][0]["case_id"]

    errors = validate(changed)["errors"]

    assert "selected case IDs must be unique" in errors


def test_validator_does_not_allow_scores_without_complete_runs_and_two_reviews():
    plan = json.loads((REPOSITORY_ROOT / "evaluation/benchmark-plan.json").read_text())
    changed = copy.deepcopy(plan)
    changed["current_state"]["quality_scores_reported"] = True

    errors = validate(changed)["errors"]

    assert any("one completed Veda run per selected case" in error for error in errors)
    assert any("two independent reviews per selected case-run" in error for error in errors)
