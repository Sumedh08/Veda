"""Check backup/restore documentation for required safeguards and unsafe commands."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RUNBOOK = ROOT / "docs" / "deployment" / "backup-restore.md"
REQUIRED_TEXT = (
    "PGSERVICEFILE",
    "PGPASSFILE",
    "[veda_backup]",
    "[veda_restore_test]",
    "--format=custom",
    "pg_restore --list",
    "pg_restore --single-transaction",
    "template0",
    "*_test",
    "not executed",
    "RPO",
    "RTO",
    "Get-FileHash",
    "/api/v1/health/ready",
    "FROM pg_class c JOIN pg_namespace n",
    "FROM pg_namespace WHERE nspname NOT LIKE",
)
POWERSHELL_BLOCK = re.compile(r"```powershell\s*(.*?)```", re.IGNORECASE | re.DOTALL)
DESTRUCTIVE_COMMANDS = (
    re.compile(r"(?i)\b(?:dropdb|DROP\s+DATABASE)\b"),
    re.compile(r"(?i)\bpg_restore\b[^\r\n]*(?:--clean|--if-exists|--create|(?:^|\s)-[cC](?:\s|$))"),
    re.compile(r"(?i)\bRemove-Item\b"),
    re.compile(r"(?i)\bpostgres(?:ql)?://[^\s/@:]+:[^\s/@]+@"),
)
RESTORE_PREFLIGHT = (
    re.compile(
        r"\$restoreDb\s*=\s*psql\s+['\"]service=veda_restore_test['\"][^\r\n]*SELECT current_database\(\)",
        re.IGNORECASE,
    ),
    re.compile(r"-notmatch\s+['\"]_test\$['\"]", re.IGNORECASE),
    re.compile(
        r"\$relationCount\s*=\s*psql\s+['\"]service=veda_restore_test['\"][^\r\n]*FROM pg_class",
        re.IGNORECASE,
    ),
    re.compile(
        r"\$extraSchemaCount\s*=\s*psql\s+['\"]service=veda_restore_test['\"][^\r\n]*FROM pg_namespace",
        re.IGNORECASE,
    ),
    re.compile(
        r"pg_restore\s+--single-transaction[^\r\n]*--dbname\s+['\"]service=veda_restore_test['\"]",
        re.IGNORECASE,
    ),
)


def validate_text(text: str) -> list[str]:
    errors = [
        f"runbook is missing required disclosure or command: {marker}"
        for marker in REQUIRED_TEXT
        if marker not in text
    ]
    blocks = POWERSHELL_BLOCK.findall(text)
    if not blocks:
        errors.append("runbook must contain executable PowerShell examples")

    for block_number, block in enumerate(blocks, start=1):
        for pattern in DESTRUCTIVE_COMMANDS:
            if pattern.search(block):
                errors.append(
                    f"PowerShell example {block_number} contains a destructive command or inline credential"
                )

    restore_block = next(
        (block for block in blocks if "pg_restore --single-transaction" in block), ""
    )
    if restore_block:
        positions = []
        for check in RESTORE_PREFLIGHT:
            match = check.search(restore_block)
            if not match:
                errors.append(
                    "restore example is missing a database identity, *_test, empty-target, or atomic-restore guard"
                )
                break
            positions.append(match.start())
        if len(positions) == len(RESTORE_PREFLIGHT) and positions != sorted(positions):
            errors.append("restore example must run every target guard before pg_restore")
    else:
        errors.append("runbook must include a guarded single-transaction pg_restore command")
    return errors


def validate_repository(root: Path = ROOT) -> list[str]:
    runbook = root / "docs" / "deployment" / "backup-restore.md"
    try:
        text = runbook.read_text(encoding="utf-8")
    except OSError as exc:
        return [f"could not read backup/restore runbook: {exc}"]

    errors = validate_text(text)
    linked_files = (
        (root / "README.md", "docs/deployment/backup-restore.md"),
        (root / "docs" / "deployment" / "recovery.md", "backup-restore.md"),
        (root / "docs" / "deployment" / "render.md", "backup-restore.md"),
    )
    for path, marker in linked_files:
        try:
            content = path.read_text(encoding="utf-8")
        except OSError as exc:
            errors.append(f"could not read linked documentation {path.relative_to(root)}: {exc}")
            continue
        if marker not in content:
            errors.append(f"{path.relative_to(root)} must link the backup/restore runbook")

    inventory = root / "docs" / "implementation-inventory.md"
    if inventory.exists() and "T-90" not in inventory.read_text(encoding="utf-8"):
        errors.append("implementation inventory must track the backup/restore runbook")
    return errors


def main() -> int:
    errors = validate_repository()
    if errors:
        print("Backup/restore runbook safety validation failed:")
        for error in errors:
            print(f"- {error}")
        return 1
    print("Backup/restore runbook safeguards and documentation links passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
