import importlib
import sys
from pathlib import Path

from app.providers.llm import LLMProviderError, maximum_input_token_estimate
from app.research.llm_tasks import ResearchAppraisalBatch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
runner = importlib.import_module("serve_sarvam_research_e2e")


def test_probe_output_budget_fits_conservative_pre_dispatch_reservation():
    system, user = runner._probe_payload()
    input_token_bound = maximum_input_token_estimate(
        system,
        user,
        schema_name="veda_sarvam_compatibility_probe_v1",
        schema_model=ResearchAppraisalBatch,
    )
    estimate = input_token_bound * 15 / 1_000_000 + runner.PROBE_OUTPUT_TOKEN_CAP * 60 / 1_000_000

    assert estimate <= runner.PROBE_RESERVATION_INR


def test_sarvam_validation_failure_keeps_sanitized_usage_metadata():
    error = LLMProviderError(
        "provider detail must not be persisted",
        code="provider_output_truncated",
        model_name="sarvam-105b",
        finish_reason="length",
        input_tokens=4_468,
        output_tokens=256,
        reasoning_tokens=0,
        latency_ms=1_250,
        estimated_cost_amount=0.08,
        cost_currency="INR",
    )

    diagnostic = runner._provider_failure_details(error, stage="compatibility_probe")

    assert diagnostic == {
        "stage": "compatibility_probe",
        "error_class": "provider_output_truncated",
        "model": "sarvam-105b",
        "model_identity_confirmed": True,
        "finish_reason": "length",
        "input_tokens": 4_468,
        "output_tokens": 256,
        "reasoning_tokens": 0,
        "usage_metadata_complete": True,
        "reported_cost_inr": None,
        "estimated_cost_inr": 0.08,
        "reported_cost_known": False,
        "latency_ms": 1_250,
        "outcome_uncertain": False,
    }
    assert "provider detail must not be persisted" not in repr(diagnostic)


def test_sarvam_validation_failure_keeps_unknown_cost_and_unconfirmed_model_unknown():
    error = LLMProviderError(
        "transport detail must not be persisted",
        code="provider_timeout",
        outcome_uncertain=True,
    )

    diagnostic = runner._provider_failure_details(error, stage="planning")

    assert diagnostic["stage"] == "planning"
    assert diagnostic["model"] is None
    assert diagnostic["model_identity_confirmed"] is False
    assert diagnostic["usage_metadata_complete"] is False
    assert diagnostic["reported_cost_inr"] is None
    assert diagnostic["estimated_cost_inr"] is None
    assert diagnostic["reported_cost_known"] is False
    assert diagnostic["outcome_uncertain"] is True
    assert "transport detail must not be persisted" not in repr(diagnostic)
