"""No-network, bounded subprocess entry point for untrusted PDF parsing."""

import json
import sys
from pathlib import Path

from app.research.safe_fetch import SafeFetchError
from app.research.safe_pdf import (
    MAX_PDF_BYTES,
    extract_pdf_pages_from_file_in_worker,
    extract_pdf_pages_in_worker,
)


def main() -> int:
    try:
        if len(sys.argv) == 3 and sys.argv[1] == "--input-file":
            pages, page_count, truncated = extract_pdf_pages_from_file_in_worker(Path(sys.argv[2]))
        elif len(sys.argv) == 1:
            data = sys.stdin.buffer.read(MAX_PDF_BYTES + 1)
            if len(data) > MAX_PDF_BYTES:
                raise SafeFetchError("response_too_large", "The PDF exceeds the byte limit.")
            pages, page_count, truncated = extract_pdf_pages_in_worker(data)
        else:
            raise SafeFetchError("invalid_pdf", "The PDF worker received invalid input.")
        result = {
            "ok": True,
            "pages": [[page, text] for page, text in pages],
            "page_count": page_count,
            "truncated": truncated,
        }
        status = 0
    except SafeFetchError as exc:
        result = {"ok": False, "error_code": exc.code}
        status = 2
    except Exception:
        result = {"ok": False, "error_code": "pdf_parser_error"}
        status = 2
    sys.stdout.buffer.write(json.dumps(result, ensure_ascii=False).encode("utf-8"))
    return status


if __name__ == "__main__":
    raise SystemExit(main())
