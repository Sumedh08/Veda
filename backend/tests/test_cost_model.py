from scripts.calculate_cost_scenarios import calculate


def test_cost_scenarios_are_reproducible_and_match_enforced_profile_budgets():
    result = calculate()
    assert result["price_snapshot"] == "2026-10-29"
    assert result["reference_model"] == "gpt-6-luna"
    assert result["planning_assumptions"]["quick"]["per_job_usd"] == "0.00110000"
    assert result["planning_assumptions"]["standard"]["workloads_usd"]["1000"] == "2.75000000"
    assert result["enforced_profile_caps"]["quick"]["max_input_tokens_per_job"] == 72_000
    assert result["enforced_profile_caps"]["quick"]["per_job_usd"] == "0.07273600"
    assert result["enforced_profile_caps"]["standard"]["per_job_usd"] == "0.11630400"
    assert result["enforced_profile_caps"]["deep"]["per_job_usd"] == "0.16410000"
    assert result["enforced_cap_sensitivity_for_1000_jobs_usd"]["deep"]["5"] == "820.50000000"
    glm_caps = result["sarvam_glm53_enforced_profile_caps"]
    assert glm_caps["quick"]["maximum_reserved_cost_inr"] == "8.24428800"
    assert glm_caps["standard"]["maximum_reserved_cost_inr"] == "13.53283200"
    assert glm_caps["deep"]["maximum_reserved_cost_inr"] == "19.96920000"
    assert all(cap["within_twenty_rupee_internal_ceiling"] for cap in glm_caps.values())
    assert "No provider request is made by this script." in result["limitations"]
