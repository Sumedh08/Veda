"""Local, non-uploading secret-pattern scan for the Veda source tree."""

from __future__ import annotations

import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MAX_FILE_BYTES = 4 * 1024 * 1024
TEXT_SUFFIXES = {
    ".c",
    ".cfg",
    ".css",
    ".env",
    ".example",
    ".go",
    ".h",
    ".html",
    ".ini",
    ".java",
    ".js",
    ".json",
    ".jsx",
    ".lock",
    ".md",
    ".mjs",
    ".ps1",
    ".py",
    ".rst",
    ".sh",
    ".sql",
    ".toml",
    ".ts",
    ".tsx",
    ".txt",
    ".xml",
    ".yaml",
    ".yml",
}
TEXT_NAMES = {
    "Dockerfile",
    "Makefile",
    ".gitignore",
    ".dockerignore",
    ".npmrc",
    ".pypirc",
    ".netrc",
    "credentials",
    "secrets",
}
SKIP_DIRS = {
    ".git",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "dist",
    "node_modules",
    "playwright-report",
    "test-results",
    "venv",
}

# These patterns recognize high-confidence provider credentials and private-key headers.
# Generic assignments are restricted to secret-bearing variable names and quoted literals.
PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "openai_or_openrouter_key",
        re.compile(r"(?<![A-Za-z0-9])sk-(?:or-v1-|proj-)?[A-Za-z0-9_-]{24,}"),
    ),
    (
        "github_token",
        re.compile(r"(?<![A-Za-z0-9_])(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,})"),
    ),
    ("aws_access_key", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("google_api_key", re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b")),
    ("slack_token", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{20,}\b")),
    ("private_key_header", re.compile(r"-----BEGIN (?:(?:RSA|EC|OPENSSH|DSA) )?PRIVATE KEY-----")),
    (
        "secret_assignment",
        re.compile(
            r"(?i)\b(?:[a-z0-9_]*api[_-]?key|[a-z0-9_]*access[_-]?token|"
            r"[a-z0-9_]*secret|[a-z0-9_]*password|[a-z0-9_]*private[_-]?key)\b"
            r"\s*[:=]\s*(['\"])([^'\"\r\n]{20,})\1"
        ),
    ),
    (
        "database_url_password",
        re.compile(
            r"(?i)\b(?:postgres(?:ql)?|mysql|mongodb(?:\+srv)?|redis)://"
            r"[^:/\s'\"]+:([^@/\s'\"]{8,})@([^/\s'\"]+)"
        ),
    ),
)
PLACEHOLDER_MARKERS = (
    "change-me",
    "changeme",
    "dummy",
    "example",
    "fake",
    "fixture",
    "not-a-real",
    "placeholder",
    "replace-with",
    "sample-only",
    "test-only",
)
ALLOWED_HOST_MARKERS = (
    "localhost",
    "127.0.0.1",
    "::1",
    "example",
    "test",
    "db:5432",
    "postgres:5432",
)
IGNORE_MARKER = "veda-secret-scan:ignore --"


@dataclass(frozen=True)
class Finding:
    rule: str
    line: int


def _is_placeholder(value: str) -> bool:
    lowered = value.casefold()
    return any(marker in lowered for marker in PLACEHOLDER_MARKERS)


def scan_text(content: str) -> list[Finding]:
    findings: list[Finding] = []
    seen: set[tuple[str, int]] = set()
    for line_number, line in enumerate(content.splitlines(), start=1):
        if IGNORE_MARKER in line and line.partition(IGNORE_MARKER)[2].strip():
            continue
        for rule, pattern in PATTERNS:
            for match in pattern.finditer(line):
                if rule == "secret_assignment":
                    candidate = match.group(2)
                    if _is_placeholder(candidate):
                        continue
                elif rule == "database_url_password":
                    if any(marker in match.group(2).casefold() for marker in ALLOWED_HOST_MARKERS):
                        continue
                elif rule in {
                    "openai_or_openrouter_key",
                    "github_token",
                    "aws_access_key",
                    "google_api_key",
                    "slack_token",
                }:
                    candidate = match.group(0)
                    if _is_placeholder(candidate):
                        continue
                item = (rule, line_number)
                if item not in seen:
                    seen.add(item)
                    findings.append(Finding(rule=rule, line=line_number))
    return findings


def iter_source_files(root: Path, oversized: list[Path]):
    for directory, names, filenames in os.walk(root, followlinks=False):
        names[:] = sorted(name for name in names if name not in SKIP_DIRS)
        current = Path(directory)
        for filename in sorted(filenames):
            path = current / filename
            is_env_file = filename == ".env" or filename.startswith(".env.")
            is_dot_config = filename.startswith(".") and "." not in filename[1:]
            if path.is_symlink() or (
                path.suffix.casefold() not in TEXT_SUFFIXES
                and filename not in TEXT_NAMES
                and not is_env_file
                and not is_dot_config
            ):
                continue
            try:
                if path.stat().st_size <= MAX_FILE_BYTES:
                    yield path
                else:
                    oversized.append(path)
            except OSError:
                continue


def main() -> int:
    failures = 0
    scanned = 0
    oversized: list[Path] = []
    for path in iter_source_files(ROOT, oversized):
        try:
            content = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            continue
        scanned += 1
        for finding in scan_text(content):
            # Never print the matched text or credential value.
            print(f"{path.relative_to(ROOT).as_posix()}:{finding.line}: possible {finding.rule}")
            failures += 1
    print(f"Secret-pattern scan: {scanned} text files checked; {failures} finding(s).")
    if oversized:
        print(
            f"Secret-pattern scan could not inspect {len(oversized)} text file(s) over the 4 MiB cap."
        )
    return 2 if oversized else 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
