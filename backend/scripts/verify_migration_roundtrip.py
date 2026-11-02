"""Verify the full SQLite migration chain without touching the developer DB."""

import os
import sqlite3
import subprocess
import sys
import tempfile
from contextlib import closing
from pathlib import Path


def main() -> None:
    backend_root = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(prefix="veda-migrations-") as temp_dir:
        database_path = Path(temp_dir, "roundtrip.sqlite3")
        environment = os.environ.copy()
        environment["DATABASE_URL"] = f"sqlite:///{database_path.as_posix()}"
        subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "20261029_usage_response_repair"],
            cwd=backend_root,
            env=environment,
            check=True,
        )
        legacy_sentence = "Legacy source claim 🚀."
        with closing(sqlite3.connect(database_path)) as connection:
            connection.execute(
                """
                INSERT INTO passages (
                    id, source_id, ordinal, locator, content, content_hash,
                    access_level, truncated, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "legacy-passage",
                    "legacy-source",
                    0,
                    "abstract sentence 1",
                    legacy_sentence,
                    "legacy-content-hash",
                    "abstract_excerpt",
                    0,
                    "2026-10-29T00:00:00+00:00",
                ),
            )
            connection.execute(
                """
                INSERT INTO claims (
                    id, job_id, source_id, passage_id, text, claim_type,
                    evidence_status, appraisal, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "legacy-claim",
                    "legacy-job",
                    "legacy-source",
                    "legacy-passage",
                    legacy_sentence,
                    "source_reported",
                    "not_independently_verified",
                    "{}",
                    "2026-10-29T00:00:00+00:00",
                ),
            )
            connection.commit()
        subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "20261031_usage_validation_diagnostics"],
            cwd=backend_root,
            env=environment,
            check=True,
        )
        legacy_candidate_title = "Legacy candidate before abstract snapshot migration"
        with closing(sqlite3.connect(database_path)) as connection:
            connection.execute(
                """
                INSERT INTO discovery_candidates (
                    id, job_id, candidate_key, provider, provider_record_id,
                    canonical_identity, title, doi, url, published_year, query_text,
                    ranking_order, relevance_score, relevance, disposition, reason_code,
                    canonical_source_id, discovered_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "legacy-candidate",
                    "legacy-job",
                    "a" * 64,
                    "Crossref",
                    "doi:10.5555/legacy",
                    "doi:10.5555/legacy",
                    legacy_candidate_title,
                    "10.5555/legacy",
                    "https://doi.org/10.5555/legacy",
                    2025,
                    "legacy research query",
                    1,
                    0.5,
                    "{}",
                    "selected",
                    "selected_by_relevance",
                    None,
                    "2026-10-31T00:00:00+00:00",
                ),
            )
            connection.commit()
        subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            cwd=backend_root,
            env=environment,
            check=True,
        )
        with closing(sqlite3.connect(database_path)) as connection:
            candidate_columns = {
                row[1]
                for row in connection.execute("PRAGMA table_info(discovery_candidates)").fetchall()
            }
            legacy_candidate = connection.execute(
                """SELECT title, abstract_excerpt, abstract_excerpt_retention_status,
                          source_governance
                   FROM discovery_candidates WHERE id = ?""",
                ("legacy-candidate",),
            ).fetchone()
        if not {
            "abstract_excerpt",
            "abstract_excerpt_retention_status",
            "source_governance",
        }.issubset(candidate_columns):
            raise AssertionError(
                "Discovery candidate abstract snapshot or source governance migration is missing"
            )
        if legacy_candidate != (legacy_candidate_title, None, None, None):
            raise AssertionError(
                "Legacy discovery candidate must survive the nullable abstract migration: "
                f"{legacy_candidate!r}"
            )

        commands = (
            ("downgrade", "20261029_request_limits"),
            ("upgrade", "head"),
            ("check",),
        )
        for command in commands:
            subprocess.run(
                [sys.executable, "-m", "alembic", *command],
                cwd=backend_root,
                env=environment,
                check=True,
            )
        with closing(sqlite3.connect(database_path)) as connection:
            claim = connection.execute(
                """
                SELECT c.span_start, c.span_end, c.atomization_status,
                       c.atomization_version, p.content
                FROM claims c JOIN passages p ON p.id = c.passage_id
                WHERE c.id = ?
                """,
                ("legacy-claim",),
            ).fetchone()
            passage = connection.execute(
                """
                SELECT p.id, p.document_id, p.identity_version, p.identity_key,
                       d.source_version, d.hash_scope, d.metadata
                FROM passages p JOIN retrieved_documents d ON d.id = p.document_id
                WHERE p.id = ?
                """,
                ("legacy-passage",),
            ).fetchone()
            usage_columns = {
                row[1] for row in connection.execute("PRAGMA table_info(usage_ledger)").fetchall()
            }
        expected = (0, len(legacy_sentence), "legacy_whole_sentence", 1, legacy_sentence)
        if claim != expected:
            raise AssertionError(f"Legacy claim span backfill mismatch: {claim!r} != {expected!r}")
        if not passage or passage[0] != "legacy-passage" or not passage[1] or passage[2] != 0:
            raise AssertionError(f"Legacy passage/document backfill mismatch: {passage!r}")
        if len(passage[3]) != 64 or passage[4:6] != (
            "legacy_unknown",
            "legacy_passage_snapshot",
        ):
            raise AssertionError(f"Legacy passage identity metadata mismatch: {passage!r}")
        if "error_class" not in usage_columns:
            raise AssertionError("Usage ledger provider error classification migration is missing")
        if not {
            "validation_error_types_json",
            "validation_error_paths_json",
        }.issubset(usage_columns):
            raise AssertionError("Usage ledger sanitized schema diagnostics migration is missing")


if __name__ == "__main__":
    main()
