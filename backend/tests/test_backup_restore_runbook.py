from pathlib import Path

from scripts.validate_backup_restore import ROOT, validate_repository, validate_text


def test_repository_backup_restore_runbook_has_required_safeguards_and_links():
    assert validate_repository(ROOT) == []


def test_validator_rejects_destructive_restore_flags_and_commands():
    runbook = (ROOT / "docs" / "deployment" / "backup-restore.md").read_text(encoding="utf-8")
    unsafe_variants = (
        runbook.replace(
            "pg_restore --single-transaction", "pg_restore --clean --single-transaction"
        ),
        runbook.replace(
            "pg_restore --single-transaction", "pg_restore --if-exists --single-transaction"
        ),
        runbook.replace(
            "pg_restore --single-transaction", "pg_restore --create --single-transaction"
        ),
        runbook.replace(
            "pg_restore --single-transaction",
            "dropdb veda_restore_test\npg_restore --single-transaction",
        ),
        runbook.replace(
            "pg_restore --single-transaction",
            'psql "service=veda_restore_test" -c "DROP DATABASE veda_restore_test"\npg_restore --single-transaction',
        ),
    )
    for unsafe in unsafe_variants:
        assert any("destructive command" in error for error in validate_text(unsafe))


def test_validator_rejects_a_missing_or_reordered_restore_guard():
    runbook = (ROOT / "docs" / "deployment" / "backup-restore.md").read_text(encoding="utf-8")
    missing_target_guard = runbook.replace(
        'if ($LASTEXITCODE -ne 0 -or $restoreDb -notmatch "_test$") { throw "Restore target must be a reachable *_test database." }',
        "",
    )
    reordered_guard = runbook.replace(
        "$relationCount = psql",
        'pg_restore --single-transaction --no-owner --no-acl --dbname "service=veda_restore_test" $dumpPath\n$relationCount = psql',
    )
    assert any(
        "missing a database identity" in error for error in validate_text(missing_target_guard)
    )
    assert any("before pg_restore" in error for error in validate_text(reordered_guard))
    wrong_restore_database = runbook.replace(
        '--dbname "service=veda_restore_test"', '--dbname "service=veda_production"'
    )
    assert any(
        "missing a database identity" in error for error in validate_text(wrong_restore_database)
    )


def test_validator_rejects_missing_no_run_and_operator_link_disclosures():
    runbook = (ROOT / "docs" / "deployment" / "backup-restore.md").read_text(encoding="utf-8")
    assert any(
        "not executed" in error for error in validate_text(runbook.replace("not executed", "unrun"))
    )
    assert any(
        "RPO" in error for error in validate_text(runbook.replace("RPO", "recovery objective"))
    )


def test_repository_validator_rejects_a_missing_runbook_link(tmp_path: Path):
    for relative in (
        Path("README.md"),
        Path("docs/deployment/backup-restore.md"),
        Path("docs/deployment/recovery.md"),
        Path("docs/deployment/render.md"),
        Path("docs/implementation-inventory.md"),
    ):
        destination = tmp_path / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text((ROOT / relative).read_text(encoding="utf-8"), encoding="utf-8")

    readme = tmp_path / "README.md"
    readme.write_text(
        readme.read_text(encoding="utf-8").replace("docs/deployment/backup-restore.md", ""),
        encoding="utf-8",
    )
    errors = validate_repository(tmp_path)
    assert any("README.md must link" in error for error in errors)
