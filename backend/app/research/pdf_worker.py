"""No-network, bounded subprocess entry point for untrusted PDF parsing."""

import json
import sys

from app.research.safe_fetch import SafeFetchError
from app.research.safe_pdf import MAX_PDF_BYTES, extract_pdf_pages_in_worker


def main() -> int:
    data = sys.stdin.buffer.read(MAX_PDF_BYTES + 1)
    try:
        if len(data) > MAX_PDF_BYTES:
            raise SafeFetchError("response_too_large", "The PDF exceeds the byte limit.")
        pages, page_count, truncated = extract_pdf_pages_in_worker(data)
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
