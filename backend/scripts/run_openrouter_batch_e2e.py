"""Run the local free-only OpenRouter browser suite with a process-only key.

The credential is read once from this process environment, never echoed,
written to a file, or included in subprocess arguments. The frontend test
server explicitly clears provider credentials; only the isolated backend
receives this environment variable.
"""

from __future__ import annotations

import os
import re
import subprocess
from datetime import UTC, datetime
from pathlib import Path


def main() -> int:
    key = os.environ.pop("OPENROUTER_API_KEY", "")
    if len(key) > 256 or not re.fullmatch(r"sk-or-v1-[A-Za-z0-9-]+", key):
        print("OpenRouter key input was empty or did not match the expected credential format.")
        return 2

    repository_root = Path(__file__).resolve().parents[2]
    frontend = repository_root / "frontend"
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    result_path = repository_root / "evaluation" / f"openrouter-live-batch-{timestamp}.json"
    if result_path.exists():
        print("Refusing to replace an existing live-run result file.")
        return 2

    # Keep the key in this process environment only. Playwright passes it to
    # the isolated API process; playwright.config.ts clears it for Vite.
    os.environ["OPENROUTER_API_KEY"] = key
    os.environ["OPENAI_API_KEY"] = ""
    os.environ["OPENROUTER_MODEL"] = "openrouter/free"
    os.environ["ALLOW_PAID_LLM_CALLS"] = "false"
    os.environ["VEDA_OPENROUTER_LIVE_E2E"] = "1"
    os.environ["VEDA_OPENROUTER_OUTPUT_PATH"] = str(result_path)
    del key

    try:
        completed = subprocess.run(
            [
                os.environ.get("ComSpec", "cmd.exe"),
                "/d",
                "/c",
                "npm exec -- playwright test e2e/openrouter-batch.e2e.ts --workers=1 --reporter=line",
            ],
            cwd=frontend,
            stdin=subprocess.DEVNULL,
            check=False,
        )
        return completed.returncode
    finally:
        os.environ.pop("OPENROUTER_API_KEY", None)
        os.environ.pop("OPENAI_API_KEY", None)


if __name__ == "__main__":
    raise SystemExit(main())
