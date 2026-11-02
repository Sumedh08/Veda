from app.research.execution_plan import PlannedModelOperation, plan_model_execution
from app.research.workflow import _minimum_completion_tokens


def test_seven_call_graph_is_reported_incomplete_under_six_call_limit():
    operations = [
        PlannedModelOperation("compatibility_probe", "probe", 1, 4096, priority=0),
        PlannedModelOperation("planning", "planning", 1, 2048, priority=0),
        PlannedModelOperation("appraisal", "appraisal", 1, 4096, priority=10),
        PlannedModelOperation("appraisal", "appraisal", 2, 4096, priority=10),
        PlannedModelOperation("comparison", "comparison", 1, 4096, priority=0),
        PlannedModelOperation("synthesis", "synthesis", 1, 4096, priority=1),
        PlannedModelOperation("semantic_audit", "semantic_audit", 1, 4096, priority=2),
    ]

    plan = plan_model_execution(
        operations,
        available_calls=6,
        available_output_tokens=6 * 4096,
        max_output_tokens_per_call=4096,
        provider_completion_limit=4096,
    )

    assert plan["required_calls"] == 7
    assert plan["planned_calls"] == 6
    assert plan["deferred_calls"] == 1
    assert plan["complete"] is False
    assert plan["deferred"][0]["deferred_reason"] == "request_quota"
    assert all(item["stage"] != "semantic_audit" for item in plan["deferred"])


def test_256_token_appraisal_is_deferred_as_underallocated():
    minimum = _minimum_completion_tokens("veda_appraisal_batch_v2")
    plan = plan_model_execution(
        [
            PlannedModelOperation(
                "veda_appraisal_batch_v2",
                "appraisal",
                1,
                256,
                minimum_completion_tokens=minimum,
            )
        ],
        available_calls=6,
        available_output_tokens=24_576,
        max_output_tokens_per_call=4096,
    )

    assert plan["planned_calls"] == 0
    assert plan["deferred"][0]["deferred_reason"] == "insufficient_operation_capacity"


def test_fixture_sized_appraisal_fits_provider_capacity_without_claiming_provider_validation():
    minimum = _minimum_completion_tokens("veda_appraisal_batch_v2")
    assert minimum == 2560
    accepted = plan_model_execution(
        [
            PlannedModelOperation(
                "veda_appraisal_batch_v2",
                "appraisal",
                1,
                minimum,
                minimum_completion_tokens=minimum,
            )
        ],
        available_calls=1,
        available_output_tokens=4096,
        max_output_tokens_per_call=4096,
        provider_completion_limit=4096,
    )
    assert accepted["complete"] is True
    assert accepted["accepted"][0]["completion_tokens"] == 2560


def test_provider_completion_limit_and_total_output_budget_are_independent():
    operations = [
        PlannedModelOperation("appraisal", "appraisal", 1, 4096, minimum_completion_tokens=2560),
        PlannedModelOperation("synthesis", "synthesis", 1, 4096, priority=1),
    ]
    provider_limited = plan_model_execution(
        operations,
        available_calls=10,
        available_output_tokens=8192,
        max_output_tokens_per_call=4096,
        provider_completion_limit=2048,
    )
    assert provider_limited["planned_calls"] == 0
    assert {item["deferred_reason"] for item in provider_limited["deferred"]} == {
        "provider_completion_limit"
    }

    output_limited = plan_model_execution(
        operations,
        available_calls=10,
        available_output_tokens=4096,
        max_output_tokens_per_call=4096,
        provider_completion_limit=4096,
    )
    assert output_limited["planned_calls"] == 1
    assert output_limited["planned_output_tokens"] == 4096
    assert output_limited["deferred"][0]["deferred_reason"] == "output_token_budget"
