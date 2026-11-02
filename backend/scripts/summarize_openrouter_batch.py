"""Merge redacted OpenRouter batch and runtime snapshots into an audit report."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.research.candidate_relevance import passes_topic_overlap_gate


def _read(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def summarize(batch: dict[str, Any], runtime: dict[str, Any]) -> dict[str, Any]:
    usage = batch.get("provider_usage", [])
    runtime_jobs = {item["job"]["id"]: item for item in runtime.get("research_jobs", [])}
    results = []
    source_providers: Counter[str] = Counter()
    stage_events: Counter[str] = Counter()
    candidate_dispositions: Counter[str] = Counter()
    claims_total = 0
    selected_sources_total = 0
    candidates_total = 0
    title_only_gate_passes = 0
    selected_gate_rejections = 0

    for result in batch.get("results", []):
        job = result["job"]
        runtime_job = runtime_jobs.get(job["id"], {})
        plan = runtime_job.get("plan", {})
        sources = runtime_job.get("sources", {}).get("items", [])
        candidates = runtime_job.get("candidates", {}).get("items", [])
        claims = runtime_job.get("claims", {}).get("items", [])
        events = runtime_job.get("events", {}).get("items", [])
        sources_by_id = {source["id"]: source for source in sources}
        source_counts = Counter(source.get("provider", "unknown") for source in sources)
        for provider, count in source_counts.items():
            source_providers[provider] += count
        for candidate in candidates:
            candidate_dispositions[str(candidate.get("disposition", "unknown"))] += 1
        for event in events:
            stage_events[str(event.get("stage", "unknown"))] += 1
        claims_total += len(claims)
        candidates_total += len(candidates)
        selected_sources_total += len(sources)
        title_only_gate_passes += sum(
            passes_topic_overlap_gate(job["question"], candidate.get("title", ""), None)
            for candidate in candidates
        )
        selected_gate_rejections += sum(
            not passes_topic_overlap_gate(
                job["question"],
                candidate.get("title", ""),
                sources_by_id.get(candidate.get("canonical_source_id"), {}).get("abstract_excerpt"),
            )
            for candidate in candidates
            if candidate.get("disposition") == "selected"
        )
        rows = [row for row in usage if row.get("job_id") == job["id"]]
        results.append(
            {
                "case_id": result.get("case_id"),
                "question": result.get("question", job.get("question")),
                "job_id": job["id"],
                "terminal_status": job.get("status"),
                "last_stage": job.get("current_stage"),
                "plan_mode": plan.get("planning_mode"),
                "plan_provenance": plan.get("planning_provenance"),
                "discovery_candidates": len(candidates),
                "candidates_passing_retrospective_title_only_gate": sum(
                    passes_topic_overlap_gate(job["question"], candidate.get("title", ""), None)
                    for candidate in candidates
                ),
                "previously_selected_sources_failing_gate_with_saved_abstract": sum(
                    not passes_topic_overlap_gate(
                        job["question"],
                        candidate.get("title", ""),
                        sources_by_id.get(candidate.get("canonical_source_id"), {}).get(
                            "abstract_excerpt"
                        ),
                    )
                    for candidate in candidates
                    if candidate.get("disposition") == "selected"
                ),
                "selected_sources": len(sources),
                "selected_sources_by_provider": dict(source_counts),
                "extracted_claims": len(claims),
                "persisted_events_by_stage": dict(
                    Counter(str(event.get("stage", "unknown")) for event in events)
                ),
                "provider_usage_entries": len(rows),
                "provider_usage_operations": dict(
                    Counter(row.get("operation", "unknown") for row in rows)
                ),
                "backend_error_class": job.get("error_class"),
                "backend_error_message": job.get("error_message"),
                "sample_selected_titles": [source.get("title") for source in sources[:4]],
                "report_generated": False,
                "citation_count": 0,
            }
        )

    successes = [row for row in usage if row.get("succeeded") is True]
    failures = [row for row in usage if row.get("succeeded") is False]
    model_ids = sorted({str(row.get("model_name")) for row in usage if row.get("model_name")})
    return {
        "schema_version": 1,
        "created_at": datetime.now(UTC).isoformat(),
        "test_date": "2026-10-29",
        "authorization": "One-time local OpenRouter free-route test; credential was supplied through a temporary process environment variable and is omitted from this record.",
        "environment": {
            "application": "Veda",
            "database": "isolated local SQLite",
            "browser": "Playwright with the local Veda UI",
            "external_deployment": False,
            "openai_calls": 0,
            "paid_routes_configured": False,
            "route": batch.get("route"),
            "openrouter_model_ids_reported": model_ids,
            "retry_count": batch.get("retries"),
            "provider_call_count_basis": "Count of persisted provider usage records; raw HTTP transport counter was not retained.",
            "provider_call_records": len(usage),
            "provider_successes": len(successes),
            "provider_failures": len(failures),
        },
        "usage_and_cost": {
            "successful_calls": [
                {
                    "operation": row.get("operation"),
                    "model": row.get("model_name"),
                    "reported_cost_usd": row.get("reported_cost_usd"),
                    "prompt_tokens": row.get("prompt_tokens"),
                    "completion_tokens": row.get("completion_tokens"),
                }
                for row in successes
            ],
            "reported_zero_cost_calls": sum(row.get("reported_cost_usd") == 0 for row in usage),
            "reported_nonzero_cost_calls": sum(
                isinstance(row.get("reported_cost_usd"), (int, float))
                and row.get("reported_cost_usd") > 0
                for row in usage
            ),
            "unknown_reported_cost_calls": sum(
                row.get("reported_cost_usd") is None for row in usage
            ),
            "reported_cost_total_usd_for_known_calls_only": sum(
                row["reported_cost_usd"]
                for row in usage
                if isinstance(row.get("reported_cost_usd"), (int, float))
            ),
            "interpretation": "Two accepted free-model responses reported $0.00. Eighteen unsuccessful provider records had no reported cost, so total provider billing is unconfirmed by Veda's persisted response data. No positive cost was reported. The route was openrouter/free and no paid fallback was configured.",
        },
        "workflow_coverage": {
            "cases_started": batch.get("started_cases"),
            "cases": results,
            "all_cases_terminal_failure": all(
                item["terminal_status"] == "terminal_failure" for item in results
            ),
            "last_completed_stage": "extraction; appraisal calls were attempted and failed before appraisals could be persisted",
            "persisted_stage_event_counts_in_runtime_snapshot": dict(stage_events),
            "selected_source_total": selected_sources_total,
            "selected_source_provider_counts": dict(source_providers),
            "discovery_candidate_total": candidates_total,
            "candidate_dispositions": dict(candidate_dispositions),
            "extracted_claim_total": claims_total,
            "retrospective_current_gate_replay": {
                "title_only_candidates_passing_gate": title_only_gate_passes,
                "previously_selected_candidates_failing_gate_with_saved_abstract": selected_gate_rejections,
                "interpretation": "Offline replay against the prior candidate snapshot. Nonselected abstracts were unavailable, queries predate the query-length fix, and no source-quality labels were collected; this is implementation-impact evidence, not a retrieval benchmark.",
            },
            "reports_persisted": 0,
            "cited_claim_total": 0,
            "citation_integrity_checks_completed": 0,
            "semantic_support_checks_completed": 0,
            "methodological_appraisals_persisted": 0,
            "hypothesis_or_contradiction_analyses_persisted": 0,
            "evidence_grounded_syntheses_persisted": 0,
            "browser_report_or_citation_inspection_for_this_batch": "not reached; no report was generated and the browser assertions exited before report-history inspection",
        },
        "quality_findings": [
            "The application did use the returned free model for two structured planning selections; their exact returned model was nvidia/nemotron-3-ultra-550b-a55b:free. The other eight plans fell back deterministically after uncertain provider outcomes.",
            "All ten appraisal operations failed with the generic backend error model_call_uncertain. The persisted usage records do not retain enough provider response detail to identify a more specific cause. Requests were not automatically resent.",
            "Crossref/OpenAlex discovery was live, but selected records showed poor topical relevance in several cases. Examples and full candidate/source records remain in the raw runtime snapshot; selection therefore does not establish evidence relevance.",
            "The planned counterevidence searches were persisted, but comparison of opposing results was not reached. No claim support, methodological quality, scientific accuracy, or outcome-effect conclusion can be assessed from this run.",
            f"Offline replay of the new conservative topic-overlap gate against the old candidate snapshot passes {title_only_gate_passes} candidates on title alone; {selected_gate_rejections} of the 140 previously selected records fail even when their saved abstract excerpt is included. This is a heuristic regression signal, not a reviewed precision/recall score.",
            "The browser UI created and advanced the real jobs, but this run did not inspect generated reports or citations because none were saved.",
        ],
        "limitations": [
            "Cost is known only for successful responses; unknown costs must not be interpreted as zero.",
            "The runtime snapshot was captured shortly before child-process shutdown and shows one job as active, while the final browser artifact records all ten as terminal failures. The final browser artifact is the terminal-status source; the snapshot is used for persisted research material counts.",
            "A raw provider transport attempt counter was not retained; 20 persisted Veda provider usage entries are used as the call count, with zero configured retries.",
            "No reports were produced, so report-level evaluation remains unperformed.",
        ],
        "raw_artifacts": [
            "evaluation/openrouter-live-batch-20261029T155042Z.json",
            "evaluation/openrouter-live-runtime-snapshot-20261029.json",
        ],
    }


def to_markdown(report: dict[str, Any]) -> str:
    usage = report["usage_and_cost"]
    workflow = report["workflow_coverage"]
    source_provider_counts = ", ".join(
        f"{provider}: {count}"
        for provider, count in workflow["selected_source_provider_counts"].items()
    )
    lines = [
        "# OpenRouter ten-case live research run",
        "",
        f"Test date: {report['test_date']}. Status: **incomplete; all ten research jobs failed before appraisal was persisted**.",
        "",
        "## Configuration and provider usage",
        "",
        f"- Route: `{report['environment']['route']}`; returned model IDs: {', '.join(f'`{model}`' for model in report['environment']['openrouter_model_ids_reported'])}.",
        f"- Local isolated SQLite and Playwright UI; OpenAI calls: {report['environment']['openai_calls']}; paid fallback: disabled; Veda retries: {report['environment']['retry_count']}.",
        f"- Persisted provider usage records: {report['environment']['provider_call_records']} ({report['environment']['provider_successes']} accepted, {report['environment']['provider_failures']} failed).",
        f"- Known response costs: {usage['reported_zero_cost_calls']} at $0.00 and {usage['reported_nonzero_cost_calls']} nonzero; cost is unknown for {usage['unknown_reported_cost_calls']}. The known-cost subtotal is ${usage['reported_cost_total_usd_for_known_calls_only']:.2f}; this is **not** a confirmed total bill.",
        "- Two structured planning responses were accepted from `nvidia/nemotron-3-ultra-550b-a55b:free` at reported $0.00. Eighteen other provider records lack confirmed cost/model response fields. No positive reported cost was observed; Veda data cannot confirm total provider billing.",
        "",
        "## Research work completed",
        "",
        f"- Ten detailed research questions started; {workflow['selected_source_total']} selected scholarly records ({source_provider_counts}) from {workflow['discovery_candidate_total']} candidates.",
        f"- {workflow['extracted_claim_total']} extracted claims were persisted. No methodological appraisals were persisted.",
        f"- Offline gate replay: {workflow['retrospective_current_gate_replay']['title_only_candidates_passing_gate']} old candidates pass on title alone; {workflow['retrospective_current_gate_replay']['previously_selected_candidates_failing_gate_with_saved_abstract']} previously selected records fail using their saved title and abstract. This is not a human-reviewed retrieval score.",
        "- Planning and real Crossref/OpenAlex discovery ran. Extraction ran for all ten cases. Appraisal was attempted, but all ten jobs ended `terminal_failure` at the appraisal stage.",
        "- Reports persisted: 0; cited claims: 0; citation integrity checks: 0; semantic support checks: 0; contradiction/hypothesis analyses: 0; final syntheses: 0.",
        "- The browser created and advanced jobs. This batch did not inspect report pages or citations because no report existed and the test stopped before report-history inspection.",
        "",
        "## Quality and reliability observations",
        "",
    ]
    lines.extend(f"- {finding}" for finding in report["quality_findings"])
    lines.extend(
        [
            "",
            "## Per-case coverage",
            "",
            "| Case | Status | Candidates | Selected | Claims | Plan |",
            "|---|---:|---:|---:|---:|---|",
        ]
    )
    for case in workflow["cases"]:
        lines.append(
            f"| {case['case_id']} | {case['terminal_status']} | {case['discovery_candidates']} | {case['selected_sources']} | {case['extracted_claims']} | {case['plan_mode']} |"
        )
    lines.extend(["", "## Limitations", ""])
    lines.extend(f"- {limitation}" for limitation in report["limitations"])
    lines.extend(
        [
            "",
            "Raw browser result and runtime snapshot are retained next to this report. This record contains no credential.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch", type=Path, required=True)
    parser.add_argument("--runtime", type=Path, required=True)
    parser.add_argument("--json-out", type=Path, required=True)
    parser.add_argument("--markdown-out", type=Path, required=True)
    args = parser.parse_args()
    report = summarize(_read(args.batch), _read(args.runtime))
    args.json_out.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    args.markdown_out.write_text(to_markdown(report), encoding="utf-8")
    print(
        f"Wrote redacted live-run report: {args.json_out} and {args.markdown_out}; "
        f"cases={len(report['workflow_coverage']['cases'])}, "
        f"provider usage rows={report['environment']['provider_call_records']}"
    )


if __name__ == "__main__":
    main()
