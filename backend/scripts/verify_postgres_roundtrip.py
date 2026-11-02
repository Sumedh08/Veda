"""Run Alembic migration round-trip only against a loopback *_test database."""

import os
import subprocess
import sys
from pathlib import Path

from sqlalchemy.engine import make_url


def main() -> None:
    raw_url = os.environ.get("VEDA_TEST_POSTGRES_URL", "")
    if not raw_url:
        raise SystemExit("Set VEDA_TEST_POSTGRES_URL to a disposable local PostgreSQL *_test DB.")
    url = make_url(raw_url)
    if url.get_backend_name() != "postgresql":
        raise SystemExit("Refusing migration checks for non-PostgreSQL URLs.")
    if url.host not in {"localhost", "127.0.0.1", "::1"}:
        raise SystemExit("Refusing migration checks for a non-loopback PostgreSQL host.")
    if not (url.database or "").endswith("_test"):
        raise SystemExit("Refusing migration checks unless the database name ends with _test.")

    backend_root = Path(__file__).resolve().parents[1]
    environment = os.environ.copy()
    environment["DATABASE_URL"] = url.render_as_string(hide_password=False)
    commands = (
        ("upgrade", "head"),
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


if __name__ == "__main__":
    main()
