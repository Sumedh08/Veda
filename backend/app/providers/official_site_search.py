"""Bounded, metadata-only publication search on verified organization websites.

This adapter discovers a WordPress REST search endpoint only from links on an
identity-verified organization's official domain. It never retrieves report
bodies; metadata discovery is distinct from rights to download, quote, or retain
content.
"""

from __future__ import annotations

import hashlib
import html
import ipaddress
import json
import re
import socket
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from dataclasses import dataclass
from datetime import UTC, datetime
from html.parser import HTMLParser
from typing import Any
from urllib.parse import parse_qs, urljoin, urlsplit
from urllib.robotparser import RobotFileParser

import httpx

from app.providers.crossref import CrossrefProvider
from app.providers.scholarly import ScholarlyWork

MAX_HOME_PAGE_BYTES = 512_000
MAX_SEARCH_RESPONSE_BYTES = 512_000
MAX_QUERY_CHARS = 180
MAX_RESULTS = 20
MAX_ACCEPTED_RECORDS = 8
MAX_DNS_SECONDS = 2.0
MAX_VERIFIED_DOMAIN_REDIRECTS = 3
_DNS_POOL = ThreadPoolExecutor(max_workers=2, thread_name_prefix="veda-official-site-dns")
_TOKEN = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*", re.I)
_QUERY_STOPWORDS = frozenset(
    "a an and are as at be been but by can could did do does for from had has have how if in "
    "into is it its may might more most of on or our should than that the their them then there "
    "these they this those through to under using was were what when where which while who why "
    "will with would uk u k united kingdom question research study studies project projects "
    "company companies organization organizations report reports evidence decision determine "
    "assess assessment evaluate evaluation impact effect effects outcomes result results balance "
    "should can improve improves improved improving reduced reduce reducing policies policy based "
    "consider considering".split()
)
_RESEARCH_SUBTYPES = frozenset(
    {
        "analysis-report",
        "publication",
        "research",
        "research-paper",
        "report",
        "working-paper",
        "policy-paper",
        "technical-report",
    }
)
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")
_TERMS_SOFT_ERROR_PATTERNS = (
    re.compile(r"\b(?:404\s*(?:not found)?|page not found)\b"),
    re.compile(r"\bthe page (?:you requested )?could not be found\b"),
    re.compile(r"\b(?:access denied|this page is unavailable)\b"),
)


class OfficialSitePublicationSearchError(Exception):
    """Safe, redacted failure from official-site metadata discovery."""

    def __init__(self, code: str, *, request_dispatched: bool = False, requests_attempted: int = 0):
        super().__init__("Official-site publication discovery failed.")
        self.code = code
        self.request_dispatched = request_dispatched
        self.requests_attempted = requests_attempted


@dataclass(frozen=True)
class OfficialSitePublicationSearchResult:
    status: str
    organization_id: str
    organization_name: str
    homepage_url: str
    api_url: str | None
    query: str
    records: list[ScholarlyWork]
    request_count: int
    discovery_link_source: str | None


@dataclass(frozen=True)
class OfficialPublicationPageMetadata:
    """Minimal page metadata; no body or search snippet is retained."""

    requested_url: str
    canonical_url: str
    title: str
    publication_date: str | None
    metadata_kind: str
    retrieved_at: str
    request_count: int
    license_code: str | None = None
    license_url: str | None = None
    license_evidence: str | None = None
    license_status: str = "not_declared"
    robots_status: str = "not_checked"
    robots_http_status: int | None = None
    site_terms_status: str = "not_checked"
    site_terms_url: str | None = None
    site_terms_sha256: str | None = None
    site_terms_restriction_codes: tuple[str, ...] = ()
    linked_pdf_url: str | None = None
    item_specific_restriction_codes: tuple[str, ...] = ()
    copyright_notice_detected: bool = False


class _PublicationMetadata(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.metadata: dict[str, str] = {}
        self.canonical: str | None = None
        self.license_urls: list[tuple[str, str]] = []
        self.terms_urls: list[str] = []
        self.pdf_urls: list[str] = []
        self._anchor_href: str | None = None
        self._anchor_text: list[str] = []
        self._in_title = False
        self._title_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if tag.casefold() == "title":
            self._in_title = True
        elif tag.casefold() == "a":
            href = values.get("href")
            self._anchor_href = href.strip()[:2000] if isinstance(href, str) else None
            self._anchor_text = []
        elif tag.casefold() == "meta":
            key = (values.get("name") or values.get("property") or "").casefold().strip()
            content = values.get("content")
            if key and isinstance(content, str) and content.strip() and key not in self.metadata:
                self.metadata[key] = " ".join(content.split())[:500]
            if key in {"citation_license", "license", "dc.rights", "dcterms.rights"}:
                if isinstance(content, str) and content.strip():
                    self.license_urls.append(
                        (content.strip()[:2000], "official_page_license_metadata")
                    )
        elif tag.casefold() == "link":
            relations = (values.get("rel") or "").casefold().split()
            href = values.get("href")
            if isinstance(href, str) and href.strip():
                if "license" in relations:
                    self.license_urls.append((href.strip()[:2000], "official_page_rel_license"))
                if "canonical" in relations and self.canonical is None:
                    self.canonical = href.strip()[:2000]
                if {"terms-of-service", "terms"} & set(relations):
                    self.terms_urls.append(href.strip()[:2000])
                media_type = (values.get("type") or "").casefold().strip()
                if media_type == "application/pdf" and len(self.pdf_urls) < 16:
                    self.pdf_urls.append(href.strip()[:2000])

    def handle_endtag(self, tag: str) -> None:
        if tag.casefold() == "title":
            self._in_title = False
        elif tag.casefold() == "a" and self._anchor_href:
            anchor_text = " ".join(" ".join(self._anchor_text).casefold().split())
            if any(word in anchor_text for word in ("terms", "copyright", "legal notice")):
                self.terms_urls.append(self._anchor_href)
            parsed_href = urlsplit(self._anchor_href)
            if parsed_href.path.casefold().endswith(".pdf") and len(self.pdf_urls) < 16:
                self.pdf_urls.append(self._anchor_href)
            self._anchor_href = None
            self._anchor_text = []

    def handle_data(self, data: str) -> None:
        if self._in_title and len(self._title_parts) < 40:
            self._title_parts.append(data[:300])
        if self._anchor_href and len(self._anchor_text) < 20:
            self._anchor_text.append(data[:200])

    @property
    def document_title(self) -> str | None:
        value = " ".join(" ".join(self._title_parts).split()).strip()
        return value[:500] or None

    def reuse_license(self) -> tuple[str | None, str | None, str | None, str]:
        """Return one unambiguous, recognized item license without retaining page text."""
        if not self.license_urls:
            return None, None, None, "not_declared"
        if len(self.license_urls) > 16:
            return None, None, None, "unrecognized_or_conflicting"
        normalized: dict[str, set[str]] = {}
        for raw_url, evidence in self.license_urls[:16]:
            safe_url = _safe_https_url(raw_url)
            if safe_url is None:
                return None, None, None, "unrecognized_or_conflicting"
            normalized.setdefault(safe_url, set()).add(evidence)
        if len(normalized) != 1:
            return None, None, None, "unrecognized_or_conflicting"
        license_url, evidence_values = next(iter(normalized.items()))
        license_code = CrossrefProvider._license_code(license_url)
        if license_code not in {"cc-by", "cc0"}:
            return None, None, None, "unrecognized_or_restricted"
        evidence = (
            "official_page_rel_license"
            if "official_page_rel_license" in evidence_values
            else "official_page_license_metadata"
        )
        return license_code, license_url, evidence, "recognized_item_license"


class _TermsText(HTMLParser):
    """Collect a bounded text view for deterministic restriction-signal checks."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._ignored_depth = 0

    def handle_starttag(self, tag: str, _attrs: list[tuple[str, str | None]]) -> None:
        if tag.casefold() in {"script", "style", "svg", "iframe", "template", "noscript"}:
            self._ignored_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag.casefold() in {"script", "style", "svg", "iframe", "template", "noscript"}:
            self._ignored_depth = max(0, self._ignored_depth - 1)

    def handle_data(self, data: str) -> None:
        if self._ignored_depth == 0 and len(self.parts) < 5000:
            self.parts.append(data[:500])


def _site_terms_signals(content: bytes) -> tuple[str | None, tuple[str, ...]]:
    """Extract bounded visible text and deterministic signals, without legal interpretation."""
    parser = _TermsText()
    try:
        parser.feed(content[:64_000].decode("utf-8", errors="replace"))
        parser.close()
    except (UnicodeError, ValueError):
        return None, ()
    text = " ".join(" ".join(parser.parts).casefold().split())
    if len(text) < 40 or any(pattern.search(text) for pattern in _TERMS_SOFT_ERROR_PATTERNS):
        return None, ()
    patterns = {
        "automated_access": re.compile(
            r"\b(?:automated|automatic)\s+(?:access|means|requests|systems|tools|scraping|crawling)\b"
            r"|\brobots?\s+(?:and|or)\s+other\s+automated\b"
            r"|\b(?:scraping|crawling)\s+(?:is|are)\s+(?:prohibited|not permitted|not allowed)\b"
        ),
        "text_data_mining": re.compile(r"\btext\s+(?:and|&)\s+data\s+mining\b|\bdata\s+mining\b"),
        "bulk_download": re.compile(
            r"\bbulk\s+(?:download|downloads|downloading|extraction|harvesting)\b"
        ),
        "ai_training": re.compile(
            r"\b(?:artificial intelligence|machine learning|ai)\s+(?:training|train)\b"
        ),
        "reproduction_without_consent": re.compile(
            r"\b(?:may not|must not|prohibited|not permitted|not allowed)\b"
            r".{0,100}\b(?:copy|reproduce|reproduction|download|extract)\b"
        ),
    }
    return text, tuple(code for code, pattern in patterns.items() if pattern.search(text))


def _publication_rights_signals(content: bytes) -> tuple[tuple[str, ...], bool]:
    """Record restrictive item-page signals and copyright-notice presence only.

    Signals trigger review; they do not interpret the notice or override a legal
    exception. Page text is bounded, parsed for visible text, and discarded.
    """
    parser = _TermsText()
    parser.feed(content[:64_000].decode("utf-8", errors="replace"))
    parser.close()
    text = " ".join(" ".join(parser.parts).casefold().split())
    restriction_patterns = {
        "item_specific_reproduction_restriction": re.compile(
            r"\bno part of .{0,140}\bmay be reproduced\b"
            r"|\breproduction\b.{0,120}\b(?:prohibited|not permitted|not allowed|requires? written permission)\b"
            r"|\b(?:may not|must not|shall not|not permitted|not allowed|prohibited)\b"
            r".{0,120}\b(?:reproduce|copy|redistribute)\b"
        ),
        "item_specific_automated_processing_restriction": re.compile(
            r"\b(?:automated access|text and data mining|machine-readable extraction)\b"
            r".{0,120}\b(?:prohibited|not permitted|not allowed|requires? permission)\b"
            r"|\b(?:prohibited|not permitted|not allowed)\b.{0,120}"
            r"\b(?:automated access|text and data mining|machine-readable extraction)\b"
        ),
    }
    codes = tuple(code for code, pattern in restriction_patterns.items() if pattern.search(text))
    copyright_notice = bool(re.search(r"\b(?:copyright|all rights reserved)\b|©|\(c\)", text))
    return codes, copyright_notice


def _publication_titles_match(actual: str, expected: str) -> bool:
    stop = {"the", "and", "for", "with", "from", "into", "of", "in", "to", "a", "an"}

    def tokens(value: str) -> set[str]:
        return {
            token
            for token in _TOKEN.findall(value.casefold())
            if len(token) > 2 and token not in stop
        }

    actual_tokens = tokens(actual)
    expected_tokens = tokens(expected)
    return bool(actual_tokens and expected_tokens) and (
        len(actual_tokens & expected_tokens) / len(actual_tokens) >= 0.45
    )


class _SiteLinks(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list[tuple[str, str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        rel = " ".join((values.get("rel") or "").casefold().split())
        for attribute in ("href", "src"):
            value = values.get(attribute)
            if isinstance(value, str) and value.strip():
                self.links.append((value.strip(), tag.casefold(), rel))
                if len(self.links) >= 20_000:
                    return


def build_official_site_query(question: str) -> str:
    """Create a short catalog query from the question, not an organization list.

    A concise subject anchor and the last hyphenated topic term avoid sending a
    long decision narrative to catalogs that treat every token as mandatory.
    The full question remains persisted separately in Veda's research plan.
    """
    if not isinstance(question, str) or not question.strip():
        return ""
    raw = _TOKEN.findall(question.casefold())
    terms: list[str] = []
    for token in raw:
        for part in token.split("-"):
            if len(part) < 2 or part in _QUERY_STOPWORDS or part.isdigit() or part in terms:
                continue
            terms.append(part)
    if not terms:
        return ""
    selected = terms[:2]
    compound_tail = next(
        (
            token.split("-")[-1]
            for token in reversed(raw)
            if "-" in token and token.split("-")[-1] not in _QUERY_STOPWORDS
        ),
        None,
    )
    if compound_tail and compound_tail not in selected:
        selected.append(compound_tail)
    for term in terms[2:]:
        if len(selected) >= 3:
            break
        if term not in selected:
            selected.append(term)
    return " ".join(selected)[:MAX_QUERY_CHARS]


def _safe_https_url(value: object) -> str | None:
    if (
        not isinstance(value, str)
        or not value.strip()
        or len(value) > 2000
        or _CONTROL.search(value)
    ):
        return None
    try:
        parsed = urlsplit(value.strip())
        port = parsed.port
    except ValueError:
        return None
    if (
        parsed.scheme.casefold() != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or port not in {None, 443}
    ):
        return None
    return value.strip()


def _redirect_key(value: str) -> str:
    parsed = urlsplit(value)
    host = (parsed.hostname or "").encode("idna").decode("ascii").casefold().rstrip(".")
    port = parsed.port
    authority = host if port in {None, 443} else f"{host}:{port}"
    path = parsed.path or "/"
    return f"https://{authority}{path}?{parsed.query}"


def _host_is_in_verified_domain(host: str, domains: list[str]) -> bool:
    normalized = host.casefold().rstrip(".")
    try:
        ipaddress.ip_address(normalized)
        return False
    except ValueError:
        pass
    if normalized in {"localhost", "localhost.localdomain"}:
        return False
    return any(
        normalized == domain.casefold().strip().rstrip(".")
        or normalized.endswith("." + domain.casefold().strip().rstrip("."))
        for domain in domains
    )


def _public_addresses(host: str, port: int) -> list[str]:
    future = _DNS_POOL.submit(socket.getaddrinfo, host, port, socket.AF_UNSPEC, socket.SOCK_STREAM)
    try:
        results = future.result(timeout=MAX_DNS_SECONDS)
    except FutureTimeout:
        future.cancel()
        raise OfficialSitePublicationSearchError("dns_timeout") from None
    except OSError:
        raise OfficialSitePublicationSearchError("dns_failure") from None
    addresses: list[str] = []
    for result in results:
        try:
            address = ipaddress.ip_address(result[4][0].split("%", 1)[0])
        except (ValueError, TypeError, IndexError):
            raise OfficialSitePublicationSearchError("dns_failure") from None
        if not address.is_global:
            raise OfficialSitePublicationSearchError("non_public_address")
        addresses.append(str(address))
    if not addresses:
        raise OfficialSitePublicationSearchError("dns_failure")
    return list(dict.fromkeys(addresses))


def _validate_public_addresses(values: Any) -> list[str]:
    if not isinstance(values, (list, tuple)):
        raise OfficialSitePublicationSearchError("dns_failure")
    addresses: list[str] = []
    for value in values:
        if isinstance(value, str):
            raw_address = value
        elif isinstance(value, tuple) and len(value) >= 5:
            raw_address = value[4][0]
        else:
            raise OfficialSitePublicationSearchError("dns_failure")
        try:
            address = ipaddress.ip_address(raw_address.split("%", 1)[0])
        except (ValueError, AttributeError):
            raise OfficialSitePublicationSearchError("dns_failure") from None
        if not address.is_global:
            raise OfficialSitePublicationSearchError("non_public_address")
        addresses.append(str(address))
    if not addresses:
        raise OfficialSitePublicationSearchError("dns_failure")
    return list(dict.fromkeys(addresses))


def _domain_values(organization: dict[str, Any]) -> list[str]:
    raw = organization.get("official_domains")
    if not isinstance(raw, list):
        raw = []
    domains: list[str] = []
    for item in raw[:8]:
        if not isinstance(item, str) or len(item) > 253 or "/" in item or ":" in item:
            continue
        host = item.strip().casefold().rstrip(".")
        if host and re.fullmatch(r"[a-z0-9.-]+", host) and ".." not in host:
            domains.append(host)
    official_urls = organization.get("official_urls")
    if isinstance(official_urls, list):
        for value in official_urls[:8]:
            safe = _safe_https_url(value)
            if safe is None:
                continue
            host = (urlsplit(safe).hostname or "").casefold()
            if host and host not in domains:
                domains.append(host)
    return domains


class WordPressPublicationSearchProvider:
    """Search a bounded WordPress REST catalog discovered on a verified site."""

    provider_name = "Official site WordPress search"

    def __init__(
        self,
        client: httpx.Client | None = None,
        *,
        before_request: Callable[[str], None] | None = None,
        public_resolver: Callable[..., Any] | None = None,
    ) -> None:
        self._owns_client = client is None
        self.client = client or httpx.Client(
            timeout=httpx.Timeout(8, connect=3),
            headers={
                "User-Agent": "VedaResearch/0.1 (official-site metadata discovery)",
                "Accept-Encoding": "identity",
            },
            follow_redirects=False,
        )
        if client is not None:
            self.client.follow_redirects = False
        self.before_request = before_request
        self.public_resolver = public_resolver or _public_addresses

    def close(self) -> None:
        if self._owns_client:
            self.client.close()

    def _get(
        self,
        url: str,
        *,
        params: dict[str, str | int] | None,
        maximum: int,
        expected: str,
        verified_domains: list[str],
        allow_http_4xx: bool = False,
    ) -> tuple[bytes, int, int]:
        safe = _safe_https_url(url)
        if safe is None:
            raise OfficialSitePublicationSearchError("invalid_official_site_url")
        current_url = safe
        current_params = params
        requests_attempted = 0
        redirects_followed = 0
        visited_urls = {_redirect_key(safe)}
        while True:
            parsed = urlsplit(current_url)
            host = (parsed.hostname or "").casefold()
            if not _host_is_in_verified_domain(host, verified_domains):
                raise OfficialSitePublicationSearchError(
                    "redirect_rejected",
                    request_dispatched=requests_attempted > 0,
                    requests_attempted=requests_attempted,
                )
            try:
                _validate_public_addresses(self.public_resolver(host, parsed.port or 443))
            except OfficialSitePublicationSearchError as exc:
                exc.request_dispatched = requests_attempted > 0
                exc.requests_attempted = requests_attempted
                raise
            except Exception:
                raise OfficialSitePublicationSearchError(
                    "dns_failure",
                    request_dispatched=requests_attempted > 0,
                    requests_attempted=requests_attempted,
                ) from None
            origin = f"https://{host}"
            if self.before_request is not None:
                try:
                    self.before_request(origin)
                except Exception:
                    raise OfficialSitePublicationSearchError(
                        "origin_request_deferred",
                        request_dispatched=requests_attempted > 0,
                        requests_attempted=requests_attempted,
                    ) from None
            try:
                requests_attempted += 1
                with self.client.stream(
                    "GET",
                    current_url,
                    params=current_params,
                    follow_redirects=False,
                    headers={"Accept": expected, "Accept-Encoding": "identity"},
                ) as response:
                    if 300 <= response.status_code < 400:
                        location = response.headers.get("location")
                        if not location or redirects_followed >= MAX_VERIFIED_DOMAIN_REDIRECTS:
                            raise OfficialSitePublicationSearchError(
                                "redirect_rejected", request_dispatched=True
                            )
                        redirect_url = _safe_https_url(urljoin(current_url, location))
                        redirect_host = (
                            (urlsplit(redirect_url).hostname or "").casefold()
                            if redirect_url is not None
                            else ""
                        )
                        if redirect_url is None or not _host_is_in_verified_domain(
                            redirect_host, verified_domains
                        ):
                            raise OfficialSitePublicationSearchError(
                                "redirect_rejected", request_dispatched=True
                            )
                        redirect_key = _redirect_key(redirect_url)
                        if redirect_key in visited_urls:
                            raise OfficialSitePublicationSearchError(
                                "redirect_loop",
                                request_dispatched=True,
                                requests_attempted=requests_attempted,
                            )
                        visited_urls.add(redirect_key)
                        current_url = redirect_url
                        current_params = None
                        redirects_followed += 1
                        continue
                    if response.status_code == 429:
                        raise OfficialSitePublicationSearchError(
                            "rate_limited", request_dispatched=True
                        )
                    if 400 <= response.status_code <= 499 and allow_http_4xx:
                        return b"", requests_attempted, response.status_code
                    if response.status_code != 200:
                        if response.status_code == 401:
                            code = "authentication_required"
                        elif response.status_code == 403:
                            code = "access_denied"
                        elif response.status_code == 404:
                            code = "not_found"
                        elif response.status_code == 429:
                            code = "rate_limited"
                        elif 500 <= response.status_code <= 599:
                            code = "upstream_server_error"
                        elif 400 <= response.status_code <= 499:
                            code = "upstream_client_error"
                        else:
                            code = "unexpected_http_status"
                        raise OfficialSitePublicationSearchError(code, request_dispatched=True)
                    content_type = (
                        response.headers.get("content-type", "").split(";", 1)[0].strip().casefold()
                    )
                    accepted_types = {
                        "text/html": {"text/html", "application/xhtml+xml"},
                        "application/json": {"application/json"},
                        "text/plain": {"text/plain"},
                    }.get(expected)
                    if accepted_types is None or content_type not in accepted_types:
                        raise OfficialSitePublicationSearchError(
                            "unexpected_content_type", request_dispatched=True
                        )
                    encoding = response.headers.get("content-encoding", "identity").casefold()
                    if encoding not in {"", "identity"}:
                        raise OfficialSitePublicationSearchError(
                            "unsupported_content_encoding", request_dispatched=True
                        )
                    declared_size = response.headers.get("content-length")
                    if declared_size:
                        try:
                            if int(declared_size) > maximum or int(declared_size) < 0:
                                raise ValueError
                        except ValueError:
                            raise OfficialSitePublicationSearchError(
                                "response_too_large", request_dispatched=True
                            ) from None
                    body = bytearray()
                    for chunk in response.iter_bytes():
                        body.extend(chunk)
                        if len(body) > maximum:
                            raise OfficialSitePublicationSearchError(
                                "response_too_large", request_dispatched=True
                            )
                    return bytes(body), requests_attempted, response.status_code
            except OfficialSitePublicationSearchError as exc:
                exc.request_dispatched = requests_attempted > 0
                exc.requests_attempted = requests_attempted
                raise
            except httpx.TimeoutException:
                raise OfficialSitePublicationSearchError(
                    "request_timeout",
                    request_dispatched=requests_attempted > 0,
                    requests_attempted=requests_attempted,
                ) from None
            except httpx.HTTPError:
                raise OfficialSitePublicationSearchError(
                    "provider_transport_error",
                    request_dispatched=requests_attempted > 0,
                    requests_attempted=requests_attempted,
                ) from None

    def verify_publication_page(
        self,
        organization: dict[str, Any],
        publication_url: str,
        *,
        expected_title: str,
    ) -> OfficialPublicationPageMetadata:
        """Verify an HTML publication page on an independently verified domain.

        This is a metadata-only request. It checks robots.txt, validates every
        host and redirect, requires HTML plus publication metadata, and returns
        only title/date/canonical provenance. Page body text is discarded and
        this method never fetches a PDF or treats a search snippet as evidence.
        """
        status = organization.get("identity_status")
        if status not in {"VERIFIED_ESTABLISHED", "VERIFIED_DOMAIN_SPECIALIST"}:
            raise OfficialSitePublicationSearchError("identity_not_verified")
        domains = _domain_values(organization)
        safe_url = _safe_https_url(publication_url)
        if not domains or safe_url is None:
            raise OfficialSitePublicationSearchError("invalid_official_site_url")
        if not isinstance(expected_title, str) or not expected_title.strip():
            raise OfficialSitePublicationSearchError("publication_title_unavailable")
        parsed = urlsplit(safe_url)
        host = (parsed.hostname or "").casefold()
        if not _host_is_in_verified_domain(host, domains) or parsed.path in {"", "/"}:
            raise OfficialSitePublicationSearchError("unverified_publication_host")

        try:
            robots_body, robots_requests, robots_http_status = self._get(
                f"https://{host}/robots.txt",
                params=None,
                maximum=64_000,
                expected="text/plain",
                verified_domains=domains,
                allow_http_4xx=True,
            )
        except OfficialSitePublicationSearchError as exc:
            if exc.code == "unexpected_content_type":
                exc.code = "robots_invalid_media_type"
            raise
        robots = None
        if robots_body:
            robots = RobotFileParser()
            robots.set_url(f"https://{host}/robots.txt")
            try:
                robots.parse(robots_body.decode("utf-8", errors="replace").splitlines())
            except (UnicodeError, ValueError):
                raise OfficialSitePublicationSearchError(
                    "robots_unavailable", request_dispatched=True
                ) from None
            if not robots.can_fetch("VedaResearch", safe_url):
                raise OfficialSitePublicationSearchError(
                    "robots_disallowed", request_dispatched=True
                )

        try:
            body, page_requests, _page_status = self._get(
                safe_url,
                params=None,
                maximum=MAX_HOME_PAGE_BYTES,
                expected="text/html",
                verified_domains=domains,
            )
        except OfficialSitePublicationSearchError as exc:
            exc.requests_attempted += robots_requests
            raise
        try:
            parser = _PublicationMetadata()
            parser.feed(body.decode("utf-8", errors="replace"))
            parser.close()
        except (UnicodeError, ValueError):
            raise OfficialSitePublicationSearchError(
                "publication_metadata_malformed", request_dispatched=True
            ) from None

        metadata = parser.metadata
        citation_title = metadata.get("citation_title")
        dc_title = metadata.get("dc.title") or metadata.get("dcterms.title")
        open_graph_title = metadata.get("og:title")
        title = citation_title or dc_title or open_graph_title or parser.document_title
        metadata_kind = (
            "citation_metadata"
            if citation_title
            else "dublin_core_metadata"
            if dc_title
            else "open_graph_article_metadata"
            if metadata.get("og:type", "").casefold() == "article"
            and (metadata.get("article:published_time") or metadata.get("article:modified_time"))
            else "page_title_only"
        )
        if not title or metadata_kind == "page_title_only":
            raise OfficialSitePublicationSearchError(
                "publication_metadata_unavailable", request_dispatched=True
            )
        if not _publication_titles_match(title, expected_title):
            raise OfficialSitePublicationSearchError(
                "search_page_title_mismatch", request_dispatched=True
            )
        canonical = urljoin(safe_url, parser.canonical or safe_url)
        safe_canonical = _safe_https_url(canonical)
        canonical_host = (
            (urlsplit(safe_canonical).hostname or "").casefold()
            if safe_canonical is not None
            else ""
        )
        if safe_canonical is None or not _host_is_in_verified_domain(canonical_host, domains):
            raise OfficialSitePublicationSearchError(
                "canonical_domain_mismatch", request_dispatched=True
            )
        if not _publication_titles_match(title, parser.document_title or title):
            raise OfficialSitePublicationSearchError(
                "page_title_metadata_mismatch", request_dispatched=True
            )
        license_code, license_url, license_evidence, license_status = parser.reuse_license()
        item_specific_restriction_codes, copyright_notice_detected = _publication_rights_signals(
            body
        )
        linked_pdf_url = None
        for raw_pdf_url in parser.pdf_urls:
            candidate_pdf_url = _safe_https_url(urljoin(safe_url, raw_pdf_url))
            if candidate_pdf_url is None:
                continue
            candidate_pdf_host = (urlsplit(candidate_pdf_url).hostname or "").casefold()
            if _host_is_in_verified_domain(candidate_pdf_host, domains):
                linked_pdf_url = candidate_pdf_url
                break
        site_terms_status = "not_checked"
        site_terms_url: str | None = None
        site_terms_sha256: str | None = None
        site_terms_restriction_codes: tuple[str, ...] = ()
        terms_requests = 0
        if license_status == "not_declared":
            candidate_terms_urls: list[str] = []
            for raw_url in parser.terms_urls[:16]:
                normalized = _safe_https_url(urljoin(safe_url, raw_url))
                if normalized is None:
                    continue
                terms_host = (urlsplit(normalized).hostname or "").casefold()
                if terms_host != host or not _host_is_in_verified_domain(terms_host, domains):
                    continue
                if normalized not in candidate_terms_urls:
                    candidate_terms_urls.append(normalized)
            origin = f"https://{host}"
            for path in ("/terms-of-use", "/terms"):
                fallback = _safe_https_url(origin + path)
                if fallback and fallback not in candidate_terms_urls:
                    candidate_terms_urls.append(fallback)
            found_terms_page = False
            terms_requests_attempted = 0
            terms_not_found_count = 0
            terms_robots_blocked = False
            for candidate_terms_url in candidate_terms_urls[:2]:
                if robots is not None and not robots.can_fetch("VedaResearch", candidate_terms_url):
                    terms_robots_blocked = True
                    continue
                site_terms_url = candidate_terms_url
                try:
                    terms_body, attempted, terms_http_status = self._get(
                        candidate_terms_url,
                        params=None,
                        maximum=64_000,
                        expected="text/html",
                        verified_domains=domains,
                        allow_http_4xx=True,
                    )
                except OfficialSitePublicationSearchError as exc:
                    terms_requests += exc.requests_attempted
                    site_terms_status = (
                        "access_denied"
                        if exc.code in {"access_denied", "authentication_required"}
                        else "parsing_inconclusive"
                        if exc.code == "unexpected_content_type"
                        else "lookup_failed"
                    )
                    break
                terms_requests += attempted
                terms_requests_attempted += 1
                if terms_http_status == 404:
                    terms_not_found_count += 1
                    continue
                if terms_http_status in {401, 403}:
                    site_terms_status = "access_denied"
                    break
                if terms_http_status >= 400:
                    site_terms_status = "lookup_failed"
                    break
                site_terms_sha256 = hashlib.sha256(terms_body).hexdigest()
                visible_text, site_terms_restriction_codes = _site_terms_signals(terms_body)
                if visible_text is None:
                    site_terms_status = "parsing_inconclusive"
                    break
                if site_terms_restriction_codes:
                    site_terms_status = "restriction_signal"
                elif terms_robots_blocked:
                    site_terms_status = "robots_disallowed"
                else:
                    site_terms_status = "checked_no_restriction_signal"
                found_terms_page = True
                break
            if not found_terms_page and site_terms_status == "not_checked":
                if terms_robots_blocked:
                    site_terms_status = "robots_disallowed"
                elif (
                    terms_requests_attempted > 0
                    and terms_not_found_count == terms_requests_attempted
                ):
                    site_terms_status = "not_found"
                elif terms_requests_attempted > 0:
                    site_terms_status = "lookup_failed"

        return OfficialPublicationPageMetadata(
            requested_url=safe_url,
            canonical_url=safe_canonical,
            title=title[:500],
            publication_date=(
                metadata.get("citation_publication_date")
                or metadata.get("citation_date")
                or metadata.get("dc.date")
                or metadata.get("article:published_time")
            ),
            metadata_kind=metadata_kind,
            retrieved_at=datetime.now(UTC).isoformat(),
            request_count=robots_requests + page_requests + terms_requests,
            license_code=license_code,
            license_url=license_url,
            license_evidence=license_evidence,
            license_status=license_status,
            robots_status="rules_checked" if robots is not None else "unavailable_4xx",
            robots_http_status=robots_http_status,
            site_terms_status=site_terms_status,
            site_terms_url=site_terms_url,
            site_terms_sha256=site_terms_sha256,
            site_terms_restriction_codes=site_terms_restriction_codes,
            linked_pdf_url=linked_pdf_url,
            item_specific_restriction_codes=item_specific_restriction_codes,
            copyright_notice_detected=copyright_notice_detected,
        )

    @staticmethod
    def _endpoint_from_homepage(
        body: bytes, *, homepage_host: str, verified_domains: list[str]
    ) -> tuple[str, str] | None:
        try:
            parser = _SiteLinks()
            parser.feed(body.decode("utf-8", errors="strict"))
        except (UnicodeDecodeError, ValueError):
            raise OfficialSitePublicationSearchError("invalid_homepage") from None
        api_links: list[str] = []
        wordpress_hosts: list[str] = []
        for href, _tag, rel in parser.links:
            safe = _safe_https_url(href)
            if safe is None:
                continue
            parsed = urlsplit(safe)
            host = (parsed.hostname or "").casefold()
            if not _host_is_in_verified_domain(host, verified_domains):
                continue
            if rel == "https://api.w.org/" and parsed.path.endswith("/wp-json/"):
                api_links.append(safe)
            query = parse_qs(parsed.query)
            if parsed.path.casefold().startswith("/wp-content/") or (
                host.startswith("cms.") and "p" in query
            ):
                wordpress_hosts.append(host)
        if api_links:
            parsed = urlsplit(api_links[0])
            return f"https://{parsed.hostname}{parsed.path}wp/v2/search", "wordpress_api_link"
        for host in dict.fromkeys(wordpress_hosts):
            if host != homepage_host and _host_is_in_verified_domain(host, verified_domains):
                return (
                    f"https://{host}/wp-json/wp/v2/search",
                    "official_homepage_linked_wordpress_host",
                )
        if homepage_host in wordpress_hosts:
            return (
                f"https://{homepage_host}/wp-json/wp/v2/search",
                "official_homepage_wordpress_assets",
            )
        return None

    @staticmethod
    def _publication_url(value: Any, verified_domains: list[str]) -> str | None:
        safe = _safe_https_url(value)
        if safe is None:
            return None
        host = (urlsplit(safe).hostname or "").casefold()
        return safe if _host_is_in_verified_domain(host, verified_domains) else None

    @staticmethod
    def _records(
        payload: Any,
        *,
        organization: dict[str, Any],
        query: str,
        api_url: str,
        homepage_url: str,
        domains: list[str],
    ) -> list[ScholarlyWork]:
        if not isinstance(payload, list):
            raise OfficialSitePublicationSearchError(
                "invalid_search_response", request_dispatched=True
            )
        records: list[ScholarlyWork] = []
        organization_id = organization.get("organization_id") or organization.get("ror_id")
        if not isinstance(organization_id, str) or not organization_id.strip():
            raise OfficialSitePublicationSearchError(
                "invalid_organization", request_dispatched=True
            )
        organization_id = organization_id.strip()
        organization_name = str(organization["canonical_name"])
        for item in payload[:MAX_RESULTS]:
            if not isinstance(item, dict):
                continue
            title_data = item.get("title")
            title_value = title_data.get("rendered") if isinstance(title_data, dict) else title_data
            if not isinstance(title_value, str):
                continue
            title = " ".join(re.sub(r"<[^>]*>", " ", html.unescape(title_value)).split())[:1000]
            subtype = item.get("subtype")
            if (
                not title
                or not isinstance(subtype, str)
                or subtype.casefold() not in _RESEARCH_SUBTYPES
                or item.get("type") != "post"
            ):
                continue
            publication_url = WordPressPublicationSearchProvider._publication_url(
                item.get("url"), domains
            )
            identifier = item.get("id")
            if (
                publication_url is None
                or isinstance(identifier, bool)
                or not isinstance(identifier, int)
                or identifier < 1
            ):
                continue
            parsed_publication = urlsplit(publication_url)
            verification_method = organization.get("verification_method")
            if verification_method == "crossref_publisher_doi_title_and_link_domain_match":
                publisher_verification = "crossref_doi_title_publisher_and_link_domain_match"
            elif (
                verification_method == "crawl4ai_search_result_domain_plus_ror_exact_domain"
                or str(organization.get("verification_source", ""))
                .casefold()
                .startswith("https://api.ror.org/")
                or str(organization.get("organization_id", ""))
                .casefold()
                .startswith("https://ror.org/")
            ):
                publisher_verification = "official_domain_linked_from_ror_verified_site"
            else:
                publisher_verification = "verified_organization_domain_and_catalog_record_match"
            provider_meta = {
                "official_site_discovery": {
                    "organization_id": organization_id,
                    "organization_name": organization_name,
                    "identity_status": organization["identity_status"],
                    "verification_source": organization.get("verification_source"),
                    "official_domain": next(
                        (
                            domain
                            for domain in domains
                            if _host_is_in_verified_domain(
                                parsed_publication.hostname or "", [domain]
                            )
                        ),
                        None,
                    ),
                    "homepage_url": homepage_url,
                    "api_url": api_url,
                    "discovery_query": query,
                    "wordpress_record_id": identifier,
                    "result_type": "post",
                    "result_subtype": subtype.casefold(),
                    "metadata_access": "public_official_site_search_api",
                    "content_fetched": False,
                    "rights_status": "not_assessed",
                    "quality_assessment": "not_assessed",
                    "publisher_verification": publisher_verification,
                }
            }
            records.append(
                ScholarlyWork(
                    external_id=f"official-site:{parsed_publication.hostname}:{identifier}",
                    title=title,
                    doi=None,
                    url=publication_url,
                    authors=[],
                    published_year=None,
                    publisher=organization_name,
                    abstract_excerpt=None,
                    query=query,
                    provider=WordPressPublicationSearchProvider.provider_name,
                    provider_metadata=provider_meta,
                    source_type="institutional_report",
                )
            )
            if len(records) >= MAX_ACCEPTED_RECORDS:
                break
        return records

    def search(
        self,
        organization: dict[str, Any],
        *,
        question: str,
        query: str | None = None,
        limit: int = 5,
    ) -> OfficialSitePublicationSearchResult:
        status = organization.get("identity_status")
        name = organization.get("canonical_name")
        organization_id = organization.get("organization_id") or organization.get("ror_id")
        domains = _domain_values(organization)
        if status not in {"VERIFIED_ESTABLISHED", "VERIFIED_DOMAIN_SPECIALIST"}:
            raise OfficialSitePublicationSearchError("identity_not_verified")
        if not isinstance(name, str) or not name.strip() or not isinstance(organization_id, str):
            raise OfficialSitePublicationSearchError("invalid_organization")
        if not domains:
            raise OfficialSitePublicationSearchError("verified_domain_unavailable")
        search_query = " ".join((query or build_official_site_query(question)).split())
        if not search_query or len(search_query) > MAX_QUERY_CHARS or _CONTROL.search(search_query):
            raise OfficialSitePublicationSearchError("invalid_query")
        if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
            raise OfficialSitePublicationSearchError("invalid_limit")
        domain = domains[0]
        homepage_url = f"https://{domain}/"
        official_urls = organization.get("official_urls")
        if isinstance(official_urls, list):
            for official_url in official_urls[:8]:
                safe_official_url = _safe_https_url(official_url)
                if safe_official_url is not None:
                    official_host = (urlsplit(safe_official_url).hostname or "").casefold()
                    if official_host in domains:
                        homepage_url = f"https://{official_host}/"
                        break
        homepage_host = (urlsplit(homepage_url).hostname or "").casefold()
        if not _host_is_in_verified_domain(homepage_host, domains):
            raise OfficialSitePublicationSearchError("unverified_homepage_host")
        try:
            home_body, requests, _home_status = self._get(
                homepage_url,
                params=None,
                maximum=MAX_HOME_PAGE_BYTES,
                expected="text/html",
                verified_domains=domains,
            )
        except OfficialSitePublicationSearchError as exc:
            exc.requests_attempted = max(exc.requests_attempted, int(exc.request_dispatched))
            raise
        discovered = self._endpoint_from_homepage(
            home_body, homepage_host=homepage_host, verified_domains=domains
        )
        if discovered is None:
            return OfficialSitePublicationSearchResult(
                "no_catalog_discovered",
                organization_id,
                name,
                homepage_url,
                None,
                search_query,
                [],
                requests,
                None,
            )
        api_url, discovery_link_source = discovered
        api_host = (urlsplit(api_url).hostname or "").casefold()
        if not _host_is_in_verified_domain(api_host, domains):
            raise OfficialSitePublicationSearchError("unverified_catalog_host")
        try:
            body, api_requests, _api_status = self._get(
                api_url,
                params={
                    "search": search_query,
                    # The caller only keeps `limit` records; requesting four times
                    # that amount needlessly inflates public CMS responses and can
                    # exceed the bounded response size on large institutional sites.
                    "per_page": min(limit, MAX_RESULTS),
                    # WordPress REST can return rich objects by default. Restrict
                    # the catalog lookup to the fields this metadata-only adapter
                    # actually validates and persists.
                    "_fields": "id,title,url,type,subtype",
                    "type": "post",
                },
                maximum=MAX_SEARCH_RESPONSE_BYTES,
                expected="application/json",
                verified_domains=domains,
            )
        except OfficialSitePublicationSearchError as exc:
            exc.requests_attempted = requests + max(
                exc.requests_attempted, int(exc.request_dispatched)
            )
            raise
        try:
            payload = json.loads(body)
        except (ValueError, TypeError):
            raise OfficialSitePublicationSearchError(
                "invalid_search_response", request_dispatched=True
            ) from None
        records = self._records(
            payload,
            organization=organization,
            query=search_query,
            api_url=api_url,
            homepage_url=homepage_url,
            domains=domains,
        )[:limit]
        return OfficialSitePublicationSearchResult(
            "completed",
            organization_id,
            name,
            homepage_url,
            api_url,
            search_query,
            records,
            requests + api_requests,
            discovery_link_source,
        )
