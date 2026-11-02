"""Reproduce planning and enforced-budget cost scenarios without provider calls."""

import json
import sys
from decimal import Decimal

from app.research.depth import PROFILES

PRICE_SNAPSHOT = "2026-10-29"
REFERENCE_MODEL = "gpt-6-luna"
INPUT_PRICE_PER_MILLION = Decimal("0.10")
OUTPUT_PRICE_PER_MILLION = Decimal("0.50")
WORKLOADS = (10, 100, 1000)
PRICE_MULTIPLIERS = (Decimal("1"), Decimal("2"), Decimal("5"))
SARVAM_GLM53_PRICE_SNAPSHOT = "2026-10-31"
SARVAM_GLM53_INPUT_PRICE_INR = Decimal("13.5")
SARVAM_GLM53_OUTPUT_PRICE_INR = Decimal("45")
SARVAM_RESERVATION_MULTIPLIER = Decimal("1.2")
PLANNING_TOKENS = {
    "quick": (6_000, 1_000),
    "standard": (15_000, 2_500),
    "deep": (40_000, 6_000),
}


def _cost(input_tokens: int, output_tokens: int, multiplier: Decimal = Decimal("1")) -> Decimal:
    return (
        (
            Decimal(input_tokens) * INPUT_PRICE_PER_MILLION
            + Decimal(output_tokens) * OUTPUT_PRICE_PER_MILLION
        )
        * multiplier
        / Decimal(1_000_000)
    )


def _money(amount: Decimal) -> str:
    return f"{amount:.8f}"


def _sarvam_cost(input_tokens: int, output_tokens: int) -> Decimal:
    raw = (
        Decimal(input_tokens) * SARVAM_GLM53_INPUT_PRICE_INR
        + Decimal(output_tokens) * SARVAM_GLM53_OUTPUT_PRICE_INR
    ) / Decimal(1_000_000)
    return raw * SARVAM_RESERVATION_MULTIPLIER


def calculate() -> dict:
    planning = {}
    enforced_caps = {}
    sarvam_glm53_caps = {}
    sensitivity = {}
    for depth, profile in PROFILES.items():
        input_tokens, output_tokens = PLANNING_TOKENS[depth]
        planning[depth] = {
            "input_tokens_per_job": input_tokens,
            "output_tokens_per_job": output_tokens,
            "per_job_usd": _money(_cost(input_tokens, output_tokens)),
            "workloads_usd": {
                str(workload): _money(_cost(input_tokens, output_tokens) * workload)
                for workload in WORKLOADS
            },
        }
        cap_cost = _cost(
            profile.max_prompt_token_budget_total,
            profile.max_output_token_budget_total,
        )
        enforced_caps[depth] = {
            "max_input_tokens_per_job": profile.max_prompt_token_budget_total,
            "max_output_tokens_per_job": profile.max_output_token_budget_total,
            "per_job_usd": _money(cap_cost),
            "workloads_usd": {str(workload): _money(cap_cost * workload) for workload in WORKLOADS},
            "price_sensitivity_per_job_usd": {
                str(multiplier): _money(cap_cost * multiplier) for multiplier in PRICE_MULTIPLIERS
            },
        }
        sarvam_reserved = _sarvam_cost(
            profile.max_prompt_token_budget_total,
            profile.max_output_token_budget_total,
        )
        sarvam_glm53_caps[depth] = {
            "max_input_tokens_per_job": profile.max_prompt_token_budget_total,
            "max_output_tokens_per_job": profile.max_output_token_budget_total,
            "maximum_reserved_cost_inr": _money(sarvam_reserved),
            "within_twenty_rupee_internal_ceiling": sarvam_reserved <= Decimal("20"),
        }
        sensitivity[depth] = {
            str(multiplier): _money(cap_cost * multiplier * 1000)
            for multiplier in PRICE_MULTIPLIERS
        }
    return {
        "price_snapshot": PRICE_SNAPSHOT,
        "reference_model": REFERENCE_MODEL,
        "prices_usd_per_million_tokens": {
            "input": str(INPUT_PRICE_PER_MILLION),
            "output": str(OUTPUT_PRICE_PER_MILLION),
        },
        "formula": "(input_tokens * input_price + output_tokens * output_price) / 1000000",
        "planning_assumptions": planning,
        "enforced_profile_caps": enforced_caps,
        "sarvam_glm53_price_snapshot": SARVAM_GLM53_PRICE_SNAPSHOT,
        "sarvam_glm53_prices_inr_per_million": {
            "uncached_input": str(SARVAM_GLM53_INPUT_PRICE_INR),
            "output_including_reasoning": str(SARVAM_GLM53_OUTPUT_PRICE_INR),
            "reservation_multiplier": str(SARVAM_RESERVATION_MULTIPLIER),
            "prices_exclude_gst": True,
        },
        "sarvam_glm53_enforced_profile_caps": sarvam_glm53_caps,
        "enforced_cap_sensitivity_for_1000_jobs_usd": sensitivity,
        "limitations": [
            "Planning token counts are assumptions, not measured provider usage.",
            "Profile input caps use a conservative token estimate, not the provider tokenizer.",
            "Sarvam GLM-5.3 Flash reservations use current public uncached-input/output prices and a 1.2 safety multiplier; this is not account billing certainty and excludes GST.",
            "Provider prices, infrastructure, search/tools, auth, taxes, and human review are excluded.",
            "No provider request is made by this script.",
        ],
    }


if __name__ == "__main__":
    json.dump(calculate(), sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
