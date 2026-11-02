import json
import runpy
import subprocess
import sys
from pathlib import Path


def test_requirement_inventory_and_task_graph_stay_crosswalked():
    repository_root = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        [sys.executable, str(repository_root / "scripts" / "validate_implementation_backlog.py")],
        cwd=repository_root,
        check=True,
        capture_output=True,
        text=True,
    )

    report = json.loads(result.stdout)

    assert report["validation"] == "passed"
    assert report["requirements"] == 66
    assert report["non_verified_requirements"] == report["residual_crosswalk_rows"]
    assert report["tasks"] > 0
    assert report["errors"] == []


def test_backlog_validator_recognizes_multi_digit_task_ids():
    repository_root = Path(__file__).resolve().parents[2]
    validator = runpy.run_path(
        str(repository_root / "scripts" / "validate_implementation_backlog.py")
    )

    assert validator["TASK_PATTERN"].findall("T-01, T-99, T-100, T-101, T-106") == [
        "T-01",
        "T-99",
        "T-100",
        "T-101",
        "T-106",
    ]


def test_residual_row_requires_at_least_one_open_task_link():
    repository_root = Path(__file__).resolve().parents[2]
    validator = runpy.run_path(
        str(repository_root / "scripts" / "validate_implementation_backlog.py")
    )

    assert validator["has_non_done_task_link"](
        "T-82, T-83, T-101", {"T-82": "DONE", "T-83": "DONE", "T-101": "BLOCKED"}
    )
    assert not validator["has_non_done_task_link"]("T-82, T-83", {"T-82": "DONE", "T-83": "DONE"})
