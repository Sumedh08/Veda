"""Reconcile requirement rows, residual task links, and machine task graph."""

from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INVENTORY_PATH = ROOT / "docs" / "implementation-inventory.md"
BACKLOG_PATH = ROOT / "docs" / "implementation-backlog.json"
BACKLOG_MD_PATH = ROOT / "docs" / "implementation-backlog.md"
REQUIREMENT_STATES = {
    "VERIFIED COMPLETE",
    "IMPLEMENTED BUT UNVERIFIED",
    "PARTIALLY IMPLEMENTED",
    "NOT IMPLEMENTED",
    "EXTERNALLY BLOCKED",
}
TASK_STATUSES = {"READY", "IN_PROGRESS", "DONE", "BLOCKED", "DEFERRED"}
TASK_PATTERN = re.compile(r"\bT-\d{2,}\b")
REQUIREMENT_PATTERN = re.compile(r"\bM-\d{2}\b")
NON_DONE_STATUSES = {"READY", "IN_PROGRESS", "BLOCKED", "DEFERRED"}


def has_non_done_task_link(task_cell: str, task_status_by_id: dict[str, str]) -> bool:
    """Return whether a residual requirement links to work that is not closed."""
    return any(
        task_status_by_id.get(task_id) in NON_DONE_STATUSES
        for task_id in TASK_PATTERN.findall(task_cell)
    )


def table_rows(section: str) -> list[list[str]]:
    rows = []
    for line in section.splitlines():
        if not line.startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if cells and cells[0].startswith(("M-", "T-")):
            rows.append(cells)
    return rows


def validate() -> dict[str, object]:
    errors: list[str] = []
    inventory = INVENTORY_PATH.read_text(encoding="utf-8")
    backlog_markdown = BACKLOG_MD_PATH.read_text(encoding="utf-8")
    tasks = json.loads(BACKLOG_PATH.read_text(encoding="utf-8"))
    if not isinstance(tasks, list):
        tasks = []
        errors.append("implementation-backlog.json must contain a task list")
    task_ids = [task.get("id") for task in tasks if isinstance(task, dict)]
    if len(task_ids) != len(set(task_ids)):
        errors.append("machine-readable task IDs must be unique")
    task_id_set = set(task_ids)

    task_status_counts: Counter[str] = Counter()
    task_status_by_id: dict[str, str] = {}
    for task in tasks:
        if not isinstance(task, dict):
            errors.append("every machine-readable task must be an object")
            continue
        task_id = task.get("id", "<missing>")
        status = task.get("status")
        if status not in TASK_STATUSES:
            errors.append(f"{task_id} has invalid task status {status!r}")
        else:
            task_status_counts[status] += 1
            task_status_by_id[task_id] = status
        if not isinstance(task_id, str) or not re.fullmatch(r"T-\d{2,}", task_id):
            errors.append(f"{task_id} has malformed task ID")
        if not task.get("task") or not task.get("acceptance"):
            errors.append(f"{task_id} needs a task description and acceptance criteria")
        if not task.get("verification") or not task.get("next_action"):
            errors.append(f"{task_id} needs durable verification and next-action fields")
        dependencies = task.get("depends_on", [])
        if not isinstance(dependencies, list):
            errors.append(f"{task_id} dependencies must be a list")
            continue
        for dependency in dependencies:
            if dependency not in task_id_set:
                errors.append(f"{task_id} depends on unknown task {dependency}")
            if dependency == task_id:
                errors.append(f"{task_id} cannot depend on itself")

    main_section = inventory.split("## Requirement-by-requirement coverage", 1)
    if len(main_section) != 2:
        errors.append("inventory is missing the requirement coverage section")
        requirements: list[list[str]] = []
        residual_rows: list[list[str]] = []
    else:
        requirement_block = main_section[1].split("## Residual requirement-to-task map", 1)
        if len(requirement_block) != 2:
            errors.append("inventory is missing the residual crosswalk section")
            requirements = []
            residual_rows = []
        else:
            requirements = table_rows(requirement_block[0])
            residual_rows = table_rows(requirement_block[1])

    requirement_ids = [row[0] for row in requirements if len(row) >= 5]
    if len(requirement_ids) != 66 or len(requirement_ids) != len(set(requirement_ids)):
        errors.append(
            f"inventory must contain 66 unique requirement rows; found {len(requirement_ids)}"
        )
    state_by_requirement: dict[str, str] = {}
    for row in requirements:
        if len(row) < 5:
            errors.append(f"malformed requirement row: {row!r}")
            continue
        requirement_id, _title, state, evidence, remaining = row[:5]
        if state not in REQUIREMENT_STATES:
            errors.append(f"{requirement_id} has invalid requirement state {state!r}")
        state_by_requirement[requirement_id] = state
        if not evidence:
            errors.append(f"{requirement_id} needs repository evidence")
        if not remaining:
            errors.append(f"{requirement_id} needs a residual-work statement")

    residual_ids: list[str] = []
    for row in residual_rows:
        if len(row) < 3:
            errors.append(f"malformed residual-map row: {row!r}")
            continue
        requirement_id, task_cell, boundary = row[:3]
        residual_ids.append(requirement_id)
        if requirement_id not in state_by_requirement:
            errors.append(f"residual map references unknown requirement {requirement_id}")
            continue
        if state_by_requirement[requirement_id] == "VERIFIED COMPLETE":
            errors.append(f"verified requirement {requirement_id} is still in the residual map")
        linked_tasks = TASK_PATTERN.findall(task_cell)
        if not linked_tasks:
            errors.append(
                f"{requirement_id} needs at least one residual task or explicit blocker task"
            )
        elif not has_non_done_task_link(task_cell, task_status_by_id):
            errors.append(
                f"{requirement_id} residual links contain no READY/IN_PROGRESS/BLOCKED/DEFERRED task"
            )
        for linked_task in linked_tasks:
            if linked_task not in task_id_set:
                errors.append(f"{requirement_id} references unknown task {linked_task}")
        if not boundary:
            errors.append(f"{requirement_id} needs a residual boundary or blocker note")

    residual_set = set(residual_ids)
    expected_residuals = {
        requirement_id
        for requirement_id, state in state_by_requirement.items()
        if state != "VERIFIED COMPLETE"
    }
    if len(residual_ids) != len(residual_set):
        errors.append("each residual requirement must appear once in the crosswalk")
    if residual_set != expected_residuals:
        missing = sorted(expected_residuals - residual_set)
        extra = sorted(residual_set - expected_residuals)
        errors.append(f"residual crosswalk mismatch; missing={missing}, extra={extra}")

    active_queue = backlog_markdown.split("## Active queue", 1)
    if len(active_queue) != 2:
        errors.append("human-readable backlog is missing its active queue")
        markdown_tasks = []
    else:
        queue = active_queue[1].split("## Completed since the previous checkpoint", 1)[0]
        markdown_tasks = table_rows(queue)
    markdown_ids = [row[0] for row in markdown_tasks if len(row) >= 5]
    if set(markdown_ids) != task_id_set or len(markdown_ids) != len(task_id_set):
        errors.append("human-readable active queue and machine-readable task IDs differ")
    for row in markdown_tasks:
        if len(row) < 5:
            errors.append(f"malformed human-readable task row: {row!r}")
            continue
        task = next(
            (item for item in tasks if isinstance(item, dict) and item.get("id") == row[0]), None
        )
        if task and row[2] != task.get("status"):
            errors.append(
                f"{row[0]} status differs between human and machine backlog: "
                f"{row[2]} vs {task.get('status')}"
            )

    # Check the dependency graph for cycles.
    dependencies_by_task = {
        task["id"]: task.get("depends_on", [])
        for task in tasks
        if isinstance(task, dict) and isinstance(task.get("id"), str)
    }
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(task_id: str) -> None:
        if task_id in visiting:
            errors.append(f"dependency graph contains a cycle at {task_id}")
            return
        if task_id in visited:
            return
        visiting.add(task_id)
        for dependency in dependencies_by_task.get(task_id, []):
            if dependency in dependencies_by_task:
                visit(dependency)
        visiting.remove(task_id)
        visited.add(task_id)

    for task_id in dependencies_by_task:
        visit(task_id)

    return {
        "validation": "passed" if not errors else "failed",
        "requirements": len(requirement_ids),
        "non_verified_requirements": len(expected_residuals),
        "residual_crosswalk_rows": len(residual_ids),
        "tasks": len(task_ids),
        "task_status_counts": dict(sorted(task_status_counts.items())),
        "errors": errors,
    }


if __name__ == "__main__":
    try:
        result = validate()
    except (OSError, json.JSONDecodeError, ValueError, TypeError) as exc:
        result = {"validation": "failed", "error": f"{type(exc).__name__}: {exc}"}
    print(json.dumps(result, indent=2))
    sys.exit(0 if result.get("validation") == "passed" else 1)
