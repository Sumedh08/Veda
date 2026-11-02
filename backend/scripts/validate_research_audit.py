"""Fail if the paper/repository evidence ledgers lose row coverage or explicit fields."""

import csv
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RESEARCH = ROOT / "docs" / "research"


def read_rows(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames is None:
            raise ValueError(f"Missing CSV header: {path}")
        rows = list(reader)
    if any(None in row for row in rows):
        raise ValueError(f"Unexpected extra CSV columns: {path}")
    if any(any(value is None or not value.strip() for value in row.values()) for row in rows):
        raise ValueError(f"Blank CSV field; use an explicit unknown/not-applicable value: {path}")
    return list(reader.fieldnames), rows


def validate() -> tuple[int, int]:
    paper_fields, papers = read_rows(RESEARCH / "papers.csv")
    repo_fields, repositories = read_rows(RESEARCH / "repos.csv")
    if not {
        "id",
        "primary_url",
        "related_code_or_data",
        "verification_status",
        "access_level",
    } <= set(paper_fields):
        raise ValueError("Paper ledger is missing evidence/access columns")
    if not {"id", "head_commit", "license", "archive_status", "decision", "status"} <= set(
        repo_fields
    ):
        raise ValueError("Repository ledger is missing snapshot/reuse columns")

    expected_papers = [f"P{index:02d}" for index in range(1, 29)]
    expected_repos = [f"R{index:02d}" for index in range(1, 24)]
    if [row["id"] for row in papers] != expected_papers:
        raise ValueError("Paper ledger must contain P01–P28 exactly once and in order")
    if [row["id"] for row in repositories] != expected_repos:
        raise ValueError("Repository ledger must contain R01–R23 exactly once and in order")
    for row in repositories:
        if not re.fullmatch(r"[0-9a-f]{40}", row["head_commit"]):
            raise ValueError(f"{row['id']} is missing a pinned 40-character commit SHA")
        if row["archive_status"] not in {"true", "false"}:
            raise ValueError(f"{row['id']} archive status must be true or false")

    paper_audits = "\n".join(
        (RESEARCH / name).read_text(encoding="utf-8")
        for name in ("paper-audit-P01-P14.md", "paper-audit-P15-P28.md")
    )
    repository_audit = (RESEARCH / "repository-audit-2026-10-29.md").read_text(encoding="utf-8")
    reuse_matrix = (RESEARCH / "reuse-matrix.md").read_text(encoding="utf-8")
    repository_rows = "\n".join(row["notes"] for row in repositories)
    for prefix, count, documents in (
        ("P", 28, paper_audits),
        ("R", 23, repository_audit),
    ):
        for index in range(1, count + 1):
            if not re.search(rf"(?m)^### {prefix}{index:02d} — ", documents):
                raise ValueError(f"Missing detailed audit section {prefix}{index:02d}")
    matrix_ids = re.findall(r"(?m)^\| (R\d\d) ", reuse_matrix)
    if matrix_ids != expected_repos:
        raise ValueError("Reuse matrix must contain a concrete decision row for R01–R23")
    evidence_text = repository_audit + reuse_matrix + repository_rows
    for required_finding in ("pyproject.toml", "package.json", "ODC-By", "dataset"):
        if required_finding not in evidence_text:
            raise ValueError(f"Reuse decision must retain the audit finding: {required_finding}")
    return len(papers), len(repositories)


def main() -> None:
    paper_count, repository_count = validate()
    print(f"Research audit ledgers valid: {paper_count} papers and {repository_count} repositories")


if __name__ == "__main__":
    main()
