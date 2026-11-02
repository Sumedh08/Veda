"""Read and persist progress from the isolated local OpenRouter browser run.

This observer uses local development auth, read-only research endpoints and the
owner export endpoint. It never reads or receives provider credentials.
"""

from __future__ import annotations

import argparse
import json
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

TERMINAL = {
    "completed",
    "completed_with_limitations",
    "terminal_failure",
    "budget_exhausted",
    "canceled",
}


def _get(client: httpx.Client, base_url: str, path: str, headers: dict[str, str]) -> Any:
    response = client.get(f"{base_url}{path}", headers=headers)
    response.raise_for_status()
    return response.json()


def capture(client: httpx.Client, base_url: str) -> dict[str, Any]:
    session_response = client.post(f"{base_url}/auth/dev-session")
    session_response.raise_for_status()
    token = session_response.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    projects = _get(client, base_url, "/projects", headers)["items"]
    project = next(
        item for item in projects if item["title"] == "Local browser integration (synthetic data)"
    )
    jobs = _get(client, base_url, f"/projects/{project['id']}/research-jobs", headers)["items"]
    research_jobs = [
        job
        for job in jobs
        if job["question"]
        != "Synthetic browser/API citation-inspection test — not a research question"
    ]
    enriched: list[dict[str, Any]] = []
    for job in research_jobs:
        item: dict[str, Any] = {"job": job}
        endpoints = {
            "plan": f"/research-jobs/{job['id']}/plan",
            "events": f"/research-jobs/{job['id']}/events",
            "sources": f"/research-jobs/{job['id']}/sources",
            "candidates": f"/research-jobs/{job['id']}/candidates?limit=200",
            "claims": f"/research-jobs/{job['id']}/claims",
        }
        if job["status"] in TERMINAL:
            endpoints.update(
                {
                    "relationships": f"/research-jobs/{job['id']}/relationships",
                    "hypotheses": f"/research-jobs/{job['id']}/hypotheses",
                }
            )
        for name, path in endpoints.items():
            item[name] = _get(client, base_url, path, headers)
        if job["status"] in {"completed", "completed_with_limitations"}:
            report = _get(client, base_url, f"/research-jobs/{job['id']}/report", headers)
            item["report"] = report
            item["inspection"] = _get(
                client, base_url, f"/reports/{report['id']}/inspection", headers
            )
        enriched.append(item)
    account_export = _get(client, base_url, "/me/export", headers)
    usages = [
        usage
        for usage in account_export.get("collections", {}).get("usage_ledger", [])
        if usage["job_id"] in {job["id"] for job in research_jobs}
    ]
    return {
        "captured_at": datetime.now(UTC).isoformat(),
        "project_id": project["id"],
        "target_research_jobs": 10,
        "observed_research_jobs": len(research_jobs),
        "research_jobs": enriched,
        "provider_usage": usages,
        "usage_summary": {
            "entries": len(usages),
            "succeeded": sum(bool(item["succeeded"]) for item in usages),
            "reported_zero_cost": sum(item["reported_cost_usd"] == 0 for item in usages),
            "reported_nonzero_cost": sum(
                isinstance(item["reported_cost_usd"], (int, float))
                and item["reported_cost_usd"] > 0
                for item in usages
            ),
            "reported_cost_unknown": sum(item["reported_cost_usd"] is None for item in usages),
            "model_ids": sorted({item["model_name"] for item in usages if item.get("model_name")}),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8001/api/v1")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--interval-seconds", default=10.0, type=float)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    last_summary: tuple[int, int, int] | None = None

    with httpx.Client(timeout=httpx.Timeout(8, connect=2)) as client:
        while True:
            try:
                snapshot = capture(client, args.base_url.rstrip("/"))
            except (httpx.HTTPError, KeyError, StopIteration, ValueError):
                time.sleep(args.interval_seconds)
                continue

            temporary_path = args.output.with_suffix(args.output.suffix + ".tmp")
            temporary_path.write_text(
                json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
            temporary_path.replace(args.output)
            terminal_count = sum(
                item["job"]["status"] in TERMINAL for item in snapshot["research_jobs"]
            )
            summary = (
                snapshot["observed_research_jobs"],
                terminal_count,
                snapshot["usage_summary"]["entries"],
            )
            if summary != last_summary:
                print(
                    f"Observed {summary[0]}/10 jobs; {summary[1]} terminal; "
                    f"{summary[2]} provider-usage rows. Snapshot saved.",
                    flush=True,
                )
                last_summary = summary
            if summary[0] >= 10 and terminal_count == summary[0]:
                return 0
            time.sleep(args.interval_seconds)


if __name__ == "__main__":
    raise SystemExit(main())
