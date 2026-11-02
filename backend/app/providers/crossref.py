import html
import re
from collections.abc import Sequence
from dataclasses import replace
from html.parser import HTMLParser
from urllib.parse import quote, urlsplit

import httpx

from app.config import settings
from app.providers.retry import MAX_SAFE_GET_RETRIES, SAFE_GET_RETRY_STATUSES, wait_for_retry
from app.providers.scholarly import ScholarlyWork

MAX_ABSTRACT_EXCERPT = 560
_DOI = re.compile(r"10\.\d{4,9}/[-._;()/:A-Z0-9]+", re.IGNORECASE)


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        if data.strip():
            self.parts.append(data.strip())


def plain_text(value: str) -> str:
    parser = _TextExtractor()
    try:
        parser.feed(value)
    except Exception:
        return " ".join(html.unescape(re.sub(r"<[^>]*>", " ", value)).split())
    return " ".join(" ".join(parser.parts).split())


# Kept as a compatibility name for existing callers and test fixtures.
CrossrefRecord = ScholarlyWork


class CrossrefError(Exception):
    pass


class CrossrefProvider:
    def __init__(self, client: httpx.Client | None = None) -> None:
        self._owns_client = client is None
        headers = {
            "User-Agent": "VedaResearch/0.1 (contact: {})".format(
                settings.crossref_mailto or "not-configured"
            )
        }
        self.client = client or httpx.Client(timeout=httpx.Timeout(12, connect=4), headers=headers)

    def close(self) -> None:
        if self._owns_client:
            self.client.close()

    def _request_items(self, params: dict[str, str | int]) -> list[dict]:
        try:
            for attempt in range(MAX_SAFE_GET_RETRIES + 1):
                response = self.client.get("https://api.crossref.org/works", params=params)
                if (
                    response.status_code in SAFE_GET_RETRY_STATUSES
                    and attempt < MAX_SAFE_GET_RETRIES
                ):
                    delay = wait_for_retry(response.headers, retry_number=attempt)
                    if delay is not None:
                        continue
                response.raise_for_status()
                items = response.json().get("message", {}).get("items", [])
                if not isinstance(items, list):
                    raise ValueError("Crossref returned an invalid work list")
                return [item for item in items if isinstance(item, dict)]
        except (httpx.HTTPError, ValueError, AttributeError) as exc:
            raise CrossrefError(
                "Crossref discovery failed; retry later or use another provider"
            ) from exc
        raise CrossrefError("Crossref discovery failed; retry later or use another provider")

    @staticmethod
    def _work_from_item(item: dict, *, query: str) -> ScholarlyWork | None:
        titles = item.get("title") or []
        title = " ".join(str(titles[0] if titles else "Untitled scholarly record").split())[:1000]
        doi = str(item["DOI"]).strip() if item.get("DOI") else None
        external_id = f"doi:{doi.lower()}" if doi else str(item.get("URL", ""))
        if not external_id:
            return None
        date_parts = (
            item.get("published", {}).get("date-parts")
            or item.get("published-print", {}).get("date-parts")
            or item.get("published-online", {}).get("date-parts")
            or []
        )
        year = int(date_parts[0][0]) if date_parts and date_parts[0] else None
        abstract = plain_text(str(item.get("abstract", "")))
        authors = [
            {key: str(person[key]) for key in ("given", "family") if person.get(key)}
            for person in item.get("author", [])[:12]
            if isinstance(person, dict)
        ]
        return ScholarlyWork(
            external_id=external_id,
            title=title,
            doi=doi,
            url=f"https://doi.org/{doi}" if doi else item.get("URL"),
            authors=authors,
            published_year=year,
            publisher=str(item.get("publisher", ""))[:300] or None,
            abstract_excerpt=abstract[:MAX_ABSTRACT_EXCERPT].strip() or None,
            query=query,
            provider="Crossref",
            provider_metadata={
                "work_type": item.get("type"),
                "journal_issns": [
                    value.strip()
                    for value in item.get("ISSN", [])[:16]
                    if isinstance(value, str) and value.strip()
                ]
                if isinstance(item.get("ISSN"), list)
                else [],
                "abstract_excerpt_truncated": len(abstract) > MAX_ABSTRACT_EXCERPT,
                "crossref_full_text": CrossrefProvider._full_text_metadata(item),
            },
            source_type=(
                "institutional_report"
                if isinstance(item.get("type"), str) and item["type"].casefold() == "report"
                else "scholarly_article"
            ),
        )

    @staticmethod
    def _safe_https_url(value: object) -> str | None:
        if not isinstance(value, str) or len(value) > 2000 or any(ord(c) < 32 for c in value):
            return None
        try:
            parsed = urlsplit(value.strip())
            _ = parsed.port
        except ValueError:
            return None
        if (
            parsed.scheme.casefold() != "https"
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
        ):
            return None
        return value.strip()

    @staticmethod
    def _license_code(value: str) -> str | None:
        safe_url = CrossrefProvider._safe_https_url(value)
        if safe_url is None:
            return None
        parsed = urlsplit(safe_url)
        if parsed.hostname.casefold() not in {"creativecommons.org", "www.creativecommons.org"}:
            return None
        path = parsed.path.casefold().rstrip("/")
        if path in {"/licenses/by/4.0", "/licenses/by/3.0"}:
            return "cc-by"
        if path == "/publicdomain/zero/1.0":
            return "cc0"
        return None

    @staticmethod
    def _full_text_metadata(item: dict) -> dict:
        license_records: list[dict[str, str]] = []
        for record in item.get("license", [])[:8] if isinstance(item.get("license"), list) else []:
            if not isinstance(record, dict) or not isinstance(record.get("URL"), str):
                continue
            url = CrossrefProvider._safe_https_url(record["URL"])
            code = CrossrefProvider._license_code(record["URL"])
            version = record.get("content-version")
            if url is None or code is None:
                continue
            license_records.append(
                {
                    "url": url,
                    "license_code": code,
                    "content_version": version[:40] if isinstance(version, str) else "unknown",
                }
            )
        links: list[dict[str, str]] = []
        for record in item.get("link", [])[:8] if isinstance(item.get("link"), list) else []:
            if not isinstance(record, dict):
                continue
            url = CrossrefProvider._safe_https_url(record.get("URL"))
            if url is None:
                continue
            content_type = record.get("content-type")
            content_version = record.get("content-version")
            intended = record.get("intended-application")
            links.append(
                {
                    "url": url,
                    "content_type": content_type[:100]
                    if isinstance(content_type, str)
                    else "unknown",
                    "content_version": content_version[:40]
                    if isinstance(content_version, str)
                    else "unknown",
                    "intended_application": intended[:80]
                    if isinstance(intended, str)
                    else "unknown",
                }
            )
        primary_license = license_records[0] if license_records else {}
        return {
            "rights_evidence_source": "crossref_deposited_work_metadata",
            "license_code": primary_license.get("license_code"),
            "license_url": primary_license.get("url"),
            "content_version": primary_license.get("content_version", "unknown"),
            "license_records": license_records,
            "links": links,
            "retrieval_status": "not_retrieved",
        }

    def search(self, query: str, *, limit: int = 5) -> list[ScholarlyWork]:
        params = {
            "query.bibliographic": query[:300],
            "rows": min(max(limit, 1), 8),
            "select": "DOI,title,author,published,published-print,published-online,publisher,URL,abstract,type,ISSN,license,link",
        }
        return [
            work
            for item in self._request_items(params)
            if (work := self._work_from_item(item, query=query)) is not None
        ]

    def resolve_doi(self, doi: str) -> ScholarlyWork:
        """Resolve one exact DOI to publisher-deposited bibliographic metadata.

        This bounded GET is used to verify DOI-bearing publication leads from a
        verified official domain. It never treats the search snippet as evidence
        and does not retry an uncertain or throttled lookup.
        """
        normalized = doi.strip() if isinstance(doi, str) else ""
        if len(normalized) > 255 or _DOI.fullmatch(normalized) is None:
            raise CrossrefError("Crossref DOI is invalid")
        encoded = quote(normalized, safe="/()")
        try:
            response = self.client.get(f"https://api.crossref.org/works/{encoded}")
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError, AttributeError):
            raise CrossrefError("Crossref DOI metadata could not be resolved") from None
        item = payload.get("message") if isinstance(payload, dict) else None
        if not isinstance(item, dict):
            raise CrossrefError("Crossref returned an invalid DOI record")
        returned_doi = item.get("DOI")
        if not isinstance(returned_doi, str) or returned_doi.casefold() != normalized.casefold():
            raise CrossrefError("Crossref returned a different DOI identity")
        work = self._work_from_item(item, query=f"doi:{normalized}")
        if work is None or not work.doi or work.doi.casefold() != normalized.casefold():
            raise CrossrefError("Crossref returned an incomplete DOI record")
        return work

    def search_for_organization(
        self,
        query: str,
        *,
        organization_names: Sequence[str],
        limit: int = 3,
    ) -> list[ScholarlyWork]:
        """Find topic-relevant works with an author affiliation matching a verified identity.

        Crossref returns deposited affiliation strings, not an institution-quality
        judgment. The caller must verify the organization independently and still
        apply Veda's ordinary topic-eligibility and evidence gates.
        """
        normalized_query = " ".join(query.split()) if isinstance(query, str) else ""
        names = [
            " ".join(name.split())
            for name in organization_names[:8]
            if isinstance(name, str) and name.strip() and len(name) <= 300
        ]
        if (
            not normalized_query
            or len(normalized_query) > 300
            or not names
            or isinstance(limit, bool)
            or not isinstance(limit, int)
            or limit < 1
        ):
            raise CrossrefError("Crossref organization publication query is invalid")
        params = {
            "query.affiliation": names[0],
            "query.bibliographic": normalized_query,
            "rows": min(limit, 3),
            "select": "DOI,title,author,published,published-print,published-online,publisher,URL,abstract,type,ISSN,license,link",
        }
        records: list[ScholarlyWork] = []
        for item in self._request_items(params):
            matched_affiliation = None
            for author in (
                item.get("author", [])[:32] if isinstance(item.get("author"), list) else []
            ):
                if not isinstance(author, dict) or not isinstance(author.get("affiliation"), list):
                    continue
                for affiliation in author["affiliation"][:8]:
                    raw_name = affiliation.get("name") if isinstance(affiliation, dict) else None
                    if not isinstance(raw_name, str):
                        continue
                    affiliation_name = plain_text(raw_name)[:500]
                    affiliation_tokens = set(re.findall(r"[a-z0-9]+", affiliation_name.casefold()))
                    if any(
                        (tokens := set(re.findall(r"[a-z0-9]+", name.casefold())))
                        and tokens.issubset(affiliation_tokens)
                        for name in names
                    ):
                        matched_affiliation = affiliation_name
                        break
                if matched_affiliation:
                    break
            if matched_affiliation is None:
                continue
            work = self._work_from_item(item, query=normalized_query)
            if work is None:
                continue
            metadata = dict(work.provider_metadata)
            metadata["matched_author_affiliation"] = matched_affiliation
            metadata["affiliation_query"] = names[0]
            records.append(replace(work, provider_metadata=metadata))
        return records
