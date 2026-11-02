"""Stable identities for immutable retrieved-document and passage snapshots."""

import hashlib
import json
import unicodedata
from uuid import UUID, uuid5

_VEDA_NAMESPACE = UUID("1c621c12-38c9-4d3d-a7ce-4cf7ca10ba5a")


def _digest(value: dict[str, str]) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def document_identity(
    *,
    source_id: str,
    source_version: str,
    document_sha256: str,
    media_type: str,
    access_class: str,
) -> tuple[str, str]:
    """Return a stable document ID and key; a changed content/version makes a new snapshot."""
    key = _digest(
        {
            "version": "retrieved_document_v1",
            "source_id": source_id,
            "source_version": source_version,
            "document_sha256": document_sha256,
            "media_type": media_type,
            "access_class": access_class,
        }
    )
    return str(uuid5(_VEDA_NAMESPACE, f"document:v1:{key}")), key


def passage_identity(
    *, source_id: str, document_id: str, locator: str, content_sha256: str
) -> tuple[str, str]:
    """Return a passage ID scoped to one source version, locator, and exact text hash."""
    normalized_locator = " ".join(unicodedata.normalize("NFC", locator).split())
    key = _digest(
        {
            "version": "passage_v1",
            "source_id": source_id,
            "document_id": document_id,
            "locator": normalized_locator,
            "content_sha256": content_sha256,
        }
    )
    return str(uuid5(_VEDA_NAMESPACE, f"passage:v1:{key}")), key
