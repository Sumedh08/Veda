from dataclasses import dataclass, field
from typing import Any
from urllib.parse import unquote, urlsplit


@dataclass(frozen=True)
class ScholarlyWork:
    """Provider-neutral bibliographic record with a bounded abstract excerpt."""

    external_id: str
    title: str
    doi: str | None
    url: str | None
    authors: list[dict[str, str]]
    published_year: int | None
    publisher: str | None
    abstract_excerpt: str | None
    query: str
    provider: str = "Crossref"
    provider_metadata: dict[str, Any] = field(default_factory=dict)
    source_type: str = "scholarly_article"


def canonical_work_identity(work: ScholarlyWork) -> str:
    """Use verified DOI identity; keep other records in their provider namespace."""
    doi = work.doi
    if not doi:
        external_id = work.external_id.strip()
        if external_id.casefold().startswith("doi:"):
            doi = external_id[4:]
        elif external_id.casefold().startswith(("https://", "http://")):
            try:
                parsed = urlsplit(external_id)
                host = (parsed.hostname or "").casefold()
                if host in {"doi.org", "dx.doi.org"}:
                    doi = unquote(parsed.path.lstrip("/"))
            except ValueError:
                doi = None
    if doi:
        normalized = doi.strip().casefold()
        for prefix in (
            "https://doi.org/",
            "http://doi.org/",
            "https://dx.doi.org/",
            "http://dx.doi.org/",
            "doi:",
        ):
            if normalized.startswith(prefix):
                normalized = normalized[len(prefix) :]
                break
        normalized = normalized.strip().rstrip(".,; ")
        if normalized:
            return f"doi:{normalized}"[:500]
    provider_id = " ".join(work.external_id.split())[:400]
    provider = " ".join(work.provider.casefold().split())[:40] or "unknown"
    return f"{provider}:{provider_id}"[:500]
