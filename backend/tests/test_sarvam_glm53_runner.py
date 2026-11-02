import importlib
import json
import sys
from pathlib import Path

from app.config import Settings
from app.providers.llm import LLMProviderError
from app.providers.registry import configured_model

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
runner = importlib.import_module("run_sarvam_glm53_research_validation")
server = importlib.import_module("serve_sarvam_glm53_research_e2e")


def test_glm_live_preflight_reserves_standard_run_under_twenty_rupees():
    config = Settings(
        llm_provider="sarvam",
        sarvam_api_key="fixture-secret",
        sarvam_model="glm5.3-flash",
        sarvam_max_job_cost_inr=20.0,
        allow_paid_llm_calls=True,
    )
    profile = configured_model("sarvam", "glm5.3-flash", config=config)

    preflight = runner._build_preflight(profile, billing_confirmed=True)

    assert preflight["model"] == "glm5.3-flash"
    assert preflight["strict_json_schema"] is True
    assert preflight["initial_reasoning_effort"] == "low"
    assert preflight["separate_compatibility_probe"] is False
    assert preflight["provider_request_hard_cap"] == 24
    assert preflight["maximum_internal_pretax_reservation_inr"] == 20
    assert preflight["conservative_standard_run_reservation_inr"] < 20


def test_glm_failure_artifact_is_allowlisted_and_contains_no_provider_message():
    error = LLMProviderError(
        "raw provider detail and fixture-secret must never be persisted",
        code="provider_output_truncated",
        model_name="glm5.3-flash",
        finish_reason="length",
        input_tokens=400,
        output_tokens=8192,
        reasoning_tokens=6000,
        estimated_cost_amount=0.45,
        cost_currency="INR",
        validation_error_types=("missing",),
        validation_error_paths=("support_assessments",),
    )

    diagnostic = server._safe_failure(error, "appraisal")

    assert diagnostic["stage"] == "appraisal"
    assert diagnostic["error_class"] == "provider_output_truncated"
    assert diagnostic["model"] == "glm5.3-flash"
    assert diagnostic["finish_reason"] == "length"
    assert diagnostic["input_tokens"] == 400
    assert diagnostic["output_tokens"] == 8192
    assert diagnostic["reasoning_tokens"] == 6000
    assert diagnostic["estimated_cost_inr"] == 0.45
    assert diagnostic["validation_error_types"] == ["missing"]
    assert diagnostic["validation_error_paths"] == ["support_assessments"]
    assert "raw provider detail" not in repr(diagnostic)
    assert "fixture-secret" not in repr(diagnostic)


def test_prior_sarvam_cost_skips_zero_post_run_and_reserves_remaining_amount(tmp_path):
    prior = tmp_path / "sarvam-glm53-research-20261030T000000000000Z.json"
    prior.write_text(
        json.dumps(
            {
                "configured_model": "glm5.3-flash",
                "provider_request_attempts": 9,
                "conservative_combined_reservation_inr": 0.7941078,
                "job": {"cost_spent_estimate_inr": 0.7941078, "cost_reserved_inr": 0},
            }
        ),
        encoding="utf-8",
    )
    prior_counter = tmp_path / "sarvam-glm-request-count-20261030T000000000000Z.txt"
    prior_counter.write_text("9\n", encoding="ascii")
    zero = tmp_path / "sarvam-glm53-research-20261030T000001000000Z.json"
    zero.write_text(json.dumps({"configured_model": "glm5.3-flash"}), encoding="utf-8")
    zero_counter = tmp_path / "sarvam-glm-request-count-20261030T000001000000Z.txt"
    zero_counter.write_text("0\n", encoding="ascii")

    assert runner._prior_validation_totals(tmp_path) == (0.7941078, 9)
    assert runner._remaining_budget(0.7941078, 9) == (19.20, 24)


def test_prior_sarvam_105b_probe_reservation_counts_toward_shared_ceiling(tmp_path):
    glm_run = tmp_path / "sarvam-glm53-research-20261030T000000000000Z.json"
    glm_run.write_text(
        json.dumps(
            {
                "configured_model": "glm5.3-flash",
                "provider_request_attempts": 2,
                "conservative_combined_reservation_inr": 0.5,
            }
        ),
        encoding="utf-8",
    )
    glm_counter = tmp_path / "sarvam-glm-request-count-20261030T000000000000Z.txt"
    glm_counter.write_text("2\n", encoding="ascii")
    starter_run = tmp_path / "sarvam-research-validation-20261030T000001000000Z.json"
    starter_run.write_text(
        json.dumps(
            {
                "configured_model": "sarvam-105b",
                "provider_request_attempts": 1,
                "compatibility_probe_pre_dispatch_reserved_cost_inr": 0.08049,
                "actual_estimated_cost_inr": None,
                "actual_reported_cost_inr": None,
            }
        ),
        encoding="utf-8",
    )

    prior_cost, prior_posts = runner._prior_validation_totals(tmp_path)

    assert prior_cost == 0.58049
    assert prior_posts == 3
    assert runner._remaining_budget(prior_cost, prior_posts) == (19.41, 24)


def test_prior_sarvam_post_with_unknown_cost_fails_closed(tmp_path):
    artifact = tmp_path / "sarvam-glm53-research-20261030T000000000000Z.json"
    artifact.write_text(
        json.dumps({"configured_model": "glm5.3-flash", "provider_request_attempts": 1}),
        encoding="utf-8",
    )
    counter = tmp_path / "sarvam-glm-request-count-20261030T000000000000Z.txt"
    counter.write_text("1\n", encoding="ascii")

    import pytest

    with pytest.raises(ValueError, match="unknown conservative cost"):
        runner._prior_validation_totals(tmp_path)


def test_prior_sarvam_105b_post_with_unknown_reservation_fails_closed(tmp_path):
    artifact = tmp_path / "sarvam-research-validation-20261030T000000000000Z.json"
    artifact.write_text(
        json.dumps(
            {
                "configured_model": "sarvam-105b",
                "provider_request_attempts": 1,
                "actual_estimated_cost_inr": None,
                "actual_reported_cost_inr": None,
            }
        ),
        encoding="utf-8",
    )

    import pytest

    with pytest.raises(ValueError, match="unknown conservative cost"):
        runner._prior_validation_totals(tmp_path)


def test_orphaned_glm_request_counter_fails_closed_before_new_reservation(tmp_path):
    counter = tmp_path / "sarvam-glm-request-count-20261030T000000000000Z.txt"
    counter.write_text("2\n", encoding="ascii")

    import pytest

    with pytest.raises(ValueError, match="unfinalized.*2 provider POSTs"):
        runner._prior_validation_totals(tmp_path)


def test_preflight_without_result_or_request_counter_fails_closed(tmp_path):
    preflight = tmp_path / "sarvam-glm53-preflight-20261030T000000000000Z.json"
    preflight.write_text("{}", encoding="utf-8")

    import pytest

    with pytest.raises(ValueError, match="unfinalized.*request count is unavailable"):
        runner._prior_validation_totals(tmp_path)


def test_final_glm_artifact_must_match_provider_request_counter(tmp_path):
    result = tmp_path / "sarvam-glm53-research-20261030T000000000000Z.json"
    result.write_text(
        json.dumps(
            {
                "configured_model": "glm5.3-flash",
                "provider_request_attempts": 3,
                "conservative_combined_reservation_inr": 0.5,
            }
        ),
        encoding="utf-8",
    )
    counter = tmp_path / "sarvam-glm-request-count-20261030T000000000000Z.txt"
    counter.write_text("2\n", encoding="ascii")

    import pytest

    with pytest.raises(ValueError, match="request-count mismatch"):
        runner._prior_validation_totals(tmp_path)


def test_usage_ledger_warning_is_reconciled_from_costed_provider_calls(tmp_path):
    stamp = "20261030T000000000000Z"
    result = tmp_path / f"sarvam-glm53-research-{stamp}.json"
    provider_usage = [
        {
            "provider": "sarvam",
            "model_name": "glm5.3-flash",
            "estimated_cost_inr": 0.1,
        }
        for _ in range(9)
    ]
    provider_usage.extend(
        {
            "provider": "sarvam",
            "model_name": "glm5.3-flash",
            "estimated_cost_inr": None,
            "error_class": "sarvam_live_run_stopped_after_failure",
        }
        for _ in range(2)
    )
    result.write_text(
        json.dumps(
            {
                "configured_model": "glm5.3-flash",
                "provider_request_attempts": 9,
                "request_count_matches_usage": False,
                "conservative_combined_reservation_inr": 0.9,
                "provider_usage": provider_usage,
            }
        ),
        encoding="utf-8",
    )
    counter = tmp_path / f"sarvam-glm-request-count-{stamp}.txt"
    counter.write_text("9\n", encoding="ascii")

    assert runner._prior_validation_totals(tmp_path) == (0.9, 9)


def test_usage_ledger_warning_without_cost_for_every_post_fails_closed(tmp_path):
    stamp = "20261030T000000000000Z"
    result = tmp_path / f"sarvam-glm53-research-{stamp}.json"
    result.write_text(
        json.dumps(
            {
                "configured_model": "glm5.3-flash",
                "provider_request_attempts": 2,
                "request_count_matches_usage": False,
                "conservative_combined_reservation_inr": 0.2,
                "provider_usage": [
                    {
                        "provider": "sarvam",
                        "model_name": "glm5.3-flash",
                        "estimated_cost_inr": 0.1,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    counter = tmp_path / f"sarvam-glm-request-count-{stamp}.txt"
    counter.write_text("2\n", encoding="ascii")

    import pytest

    with pytest.raises(ValueError, match="cannot reconcile every provider POST"):
        runner._prior_validation_totals(tmp_path)


def test_remaining_sarvam_authorization_is_rounded_down_to_paise():
    assert runner._remaining_budget(0.001, 0) == (19.99, 24)


def test_prior_request_count_is_audited_but_does_not_shrink_next_job_depth_cap():
    assert runner._remaining_budget(1.50, 19) == (18.5, 24)


def test_runner_exits_before_inference_without_both_explicit_confirmation_flags(capsys):
    assert runner.main([]) == 2
    assert "No inference dispatched" in capsys.readouterr().out
