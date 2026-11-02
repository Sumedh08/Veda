"""Bounded, metadata-only access to Crawl4AI Cloud web search."""

from __future__ import annotations

import ipaddress
import json
import math
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import httpx

BASE_URL = "https://api.crawl4ai.com"
MAX_QUERY_CHARS = 512
MAX_SEARCH_RESULTS = 10
MAX_RESPONSE_BYTES = 1_000_000
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")


class Crawl4AICloudError(Exception):
    """Sanitized outcome for one Crawl4AI Cloud request."""

    def __init__(
        self,
        code: str,
        *,
        request_dispatched: bool = False,
        retry_after_seconds: int | None = None,
        http_status: int | None = None,
        provider_charge_status: str | None = None,
    ) -> None:
        super().__init__("Crawl4AI Cloud request failed.")
        self.code = code
        self.request_dispatched = request_dispatched
        self.retry_after_seconds = retry_after_seconds
        self.http_status = http_status
        self.provider_charge_status = provider_charge_status or (
            "unknown" if request_dispatched else "not_dispatched"
        )


@dataclass(frozen=True)
class Crawl4AIWebHit:
    title: str
    url: str
    snippet: str | None
    source: str | None
    rank: int
    normalized_domain: str


@dataclass(frozen=True)
class Crawl4AIWebSearchResult:
    query: str
    provider: str
    searched_at: str
    hits: tuple[Crawl4AIWebHit, ...]
    reported_cost_credits: float | None
    balance_credits: float | None
    allowance_left_credits: float | None
    usage_status: str


@dataclass(frozen=True)
class Crawl4AIBalance:
    plan: str | None
    balance_credits: float | None
    allowance_left_credits: float | None
    raw_status: str


@dataclass(frozen=True)
class Crawl4AIScrapeEstimate:
    minimum_credits: float
    maximum_credits: float
    reported_cost_credits: float | None
    usage_status: str


@dataclass(frozen=True)
class Crawl4AICloudScrapeResult:
    requested_url: str
    markdown: str
    reported_cost_credits: float | None
    balance_credits: float | None
    allowance_left_credits: float | None
    usage_status: str


def _safe_public_url(value: object) -> tuple[str, str] | None:
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
        host = (parsed.hostname or "").casefold().rstrip(".")
    except ValueError:
        return None
    if (
        parsed.scheme.casefold() != "https"
        or not host
        or parsed.username is not None
        or parsed.password is not None
        or port not in {None, 443}
        or host in {"localhost", "localhost.localdomain"}
        or "." not in host
    ):
        return None
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        return None
    # Strip fragments and credentials/query tracking is handled separately by source identity.
    normalized = urlunsplit(
        ("https", parsed.netloc.casefold(), parsed.path or "/", parsed.query, "")
    )
    return normalized[:2000], host.removeprefix("www.")[:253]


def _reported_number(headers: httpx.Headers, name: str) -> float | None:
    value = headers.get(name)
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) and number >= 0 else None


class Crawl4AICloudSearchProvider:
    """Bounded, single-attempt Crawl4AI Cloud search and page extraction client.

    The adapter contacts only the fixed HTTPS API host. It never follows redirects,
    retries a request, calls answer/payment endpoints, or logs credentials. Search
    snippets remain discovery metadata only; scraped Markdown is returned with
    provider provenance for the caller to rights-gate and hash before persistence.
    """

    def __init__(self, *, api_key: str, client: httpx.Client | None = None) -> None:
        if not isinstance(api_key, str) or not api_key.strip():
            raise Crawl4AICloudError("credential_missing")
        self._api_key = api_key.strip()
        self._owns_client = client is None
        self.client = client or httpx.Client(
            timeout=httpx.Timeout(12, connect=4),
            follow_redirects=False,
            headers={"Accept": "application/json", "User-Agent": "VedaResearch/0.1"},
        )
        if client is not None:
            self.client.follow_redirects = False

    def close(self) -> None:
        if self._owns_client:
            self.client.close()

    def _get(
        self, path: str, *, params: dict[str, str] | None = None
    ) -> tuple[int, httpx.Headers, bytes]:
        try:
            with self.client.stream(
                "GET",
                f"{BASE_URL}{path}",
                params=params,
                headers={"Authorization": f"Bearer {self._api_key}"},
            ) as response:
                if response.status_code in {401, 403}:
                    raise Crawl4AICloudError(
                        "authentication_failed",
                        request_dispatched=True,
                        http_status=response.status_code,
                    )
                if response.status_code == 402:
                    raise Crawl4AICloudError(
                        "credit_exhausted", request_dispatched=True, http_status=402
                    )
                if response.status_code == 429:
                    raw_retry_after = response.headers.get("retry-after")
                    retry_after = (
                        int(raw_retry_after)
                        if raw_retry_after and raw_retry_after.isdigit()
                        else None
                    )
                    raise Crawl4AICloudError(
                        "rate_limited",
                        request_dispatched=True,
                        retry_after_seconds=retry_after,
                        http_status=429,
                    )
                if response.status_code >= 500:
                    raise Crawl4AICloudError(
                        "provider_unavailable",
                        request_dispatched=True,
                        http_status=response.status_code,
                        provider_charge_status="not_charged_provider_5xx",
                    )
                if response.status_code >= 400:
                    raise Crawl4AICloudError(
                        "provider_rejected_request",
                        request_dispatched=True,
                        http_status=response.status_code,
                    )
                body = bytearray()
                for chunk in response.iter_bytes():
                    body.extend(chunk)
                    if len(body) > MAX_RESPONSE_BYTES:
                        raise Crawl4AICloudError("response_too_large", request_dispatched=True)
                return response.status_code, httpx.Headers(response.headers), bytes(body)
        except httpx.TimeoutException:
            raise Crawl4AICloudError("request_timeout", request_dispatched=True) from None
        except httpx.HTTPError:
            raise Crawl4AICloudError("provider_unavailable", request_dispatched=True) from None

    def _post(
        self,
        path: str,
        payload: dict[str, Any],
        *,
        timeout_seconds: float = 12,
    ) -> tuple[int, httpx.Headers, bytes]:
        try:
            with self.client.stream(
                "POST",
                f"{BASE_URL}{path}",
                json=payload,
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                timeout=httpx.Timeout(timeout_seconds, connect=4),
            ) as response:
                if response.status_code == 401:
                    raise Crawl4AICloudError(
                        "authentication_failed", request_dispatched=True, http_status=401
                    )
                if response.status_code == 402:
                    raise Crawl4AICloudError(
                        "credit_exhausted", request_dispatched=True, http_status=402
                    )
                if response.status_code == 429:
                    raw_retry_after = response.headers.get("retry-after")
                    retry_after = (
                        int(raw_retry_after)
                        if raw_retry_after and raw_retry_after.isdigit()
                        else None
                    )
                    raise Crawl4AICloudError(
                        "rate_limited",
                        request_dispatched=True,
                        retry_after_seconds=retry_after,
                        http_status=429,
                    )
                if response.status_code >= 500:
                    raise Crawl4AICloudError(
                        "provider_unavailable",
                        request_dispatched=True,
                        http_status=response.status_code,
                        provider_charge_status="not_charged_provider_5xx",
                    )
                if response.status_code >= 400:
                    # 403 can mean a provider-side page block/login wall, so do not
                    # misreport it as invalid API credentials or expose its body.
                    raise Crawl4AICloudError(
                        "provider_rejected_request",
                        request_dispatched=True,
                        http_status=response.status_code,
                    )
                body = bytearray()
                for chunk in response.iter_bytes():
                    body.extend(chunk)
                    if len(body) > MAX_RESPONSE_BYTES:
                        raise Crawl4AICloudError("response_too_large", request_dispatched=True)
                return response.status_code, httpx.Headers(response.headers), bytes(body)
        except httpx.TimeoutException:
            raise Crawl4AICloudError("request_timeout", request_dispatched=True) from None
        except httpx.HTTPError:
            raise Crawl4AICloudError("provider_unavailable", request_dispatched=True) from None

    @staticmethod
    def _verified_page_url(value: object, expected_domain: str) -> str:
        safe_url = _safe_public_url(value)
        normalized_expected = expected_domain.casefold().strip().rstrip(".").removeprefix("www.")
        if safe_url is None or not normalized_expected or safe_url[1] != normalized_expected:
            raise Crawl4AICloudError("invalid_url")
        return safe_url[0]

    @staticmethod
    def _estimate_payload_range(payload: dict[str, Any]) -> tuple[float, float]:
        minimum = _number(payload.get("min"))
        maximum = _number(payload.get("max"))
        if minimum is None or maximum is None or maximum < minimum:
            raise Crawl4AICloudError("invalid_response", request_dispatched=True)
        return minimum, maximum

    def estimate_scrape(self, url: str, *, expected_domain: str) -> Crawl4AIScrapeEstimate:
        """Estimate one Markdown scrape for an already verified publisher domain."""
        safe_url = self._verified_page_url(url, expected_domain)
        _status, headers, body = self._post("/v1/estimate", {"endpoint": "scrape", "url": safe_url})
        payload = self._json(body)
        minimum, maximum = self._estimate_payload_range(payload)
        cost = _reported_number(headers, "x-c4-cost")
        return Crawl4AIScrapeEstimate(
            minimum_credits=minimum,
            maximum_credits=maximum,
            reported_cost_credits=cost,
            usage_status="reported" if cost is not None else "cost_unknown",
        )

    def scrape_markdown(self, url: str, *, expected_domain: str) -> Crawl4AICloudScrapeResult:
        """Fetch one verified public publisher URL as Markdown without proxies."""
        safe_url = self._verified_page_url(url, expected_domain)
        _status, headers, body = self._post(
            "/scrape",
            {"url": safe_url, "format": "md", "proxy": "none", "engine": "auto"},
            timeout_seconds=120,
        )
        payload = self._json(body)
        markdown = payload.get("markdown")
        if not isinstance(markdown, str) or not markdown.strip():
            raise Crawl4AICloudError("invalid_response", request_dispatched=True)
        if len(markdown.encode("utf-8")) > MAX_RESPONSE_BYTES:
            raise Crawl4AICloudError("response_too_large", request_dispatched=True)
        final_url = payload.get("url")
        if final_url is not None:
            safe_final = _safe_public_url(final_url)
            expected = expected_domain.casefold().strip().rstrip(".").removeprefix("www.")
            if safe_final is None or safe_final[1] != expected:
                raise Crawl4AICloudError("publisher_domain_mismatch", request_dispatched=True)
        cost = _reported_number(headers, "x-c4-cost")
        return Crawl4AICloudScrapeResult(
            requested_url=safe_url,
            markdown=markdown[:MAX_RESPONSE_BYTES],
            reported_cost_credits=cost,
            balance_credits=_reported_number(headers, "x-c4-balance"),
            allowance_left_credits=_reported_number(headers, "x-c4-allowance-left"),
            usage_status="reported" if cost is not None else "cost_unknown",
        )

    @staticmethod
    def _json(body: bytes) -> dict[str, Any]:
        try:
            value = json.loads(body)
        except (json.JSONDecodeError, ValueError):
            raise Crawl4AICloudError("invalid_response", request_dispatched=True) from None
        if not isinstance(value, dict):
            raise Crawl4AICloudError("invalid_response", request_dispatched=True)
        return value

    def search(self, query: str, *, limit: int = MAX_SEARCH_RESULTS) -> Crawl4AIWebSearchResult:
        normalized_query = " ".join(query.split()) if isinstance(query, str) else ""
        if (
            not normalized_query
            or len(normalized_query) > MAX_QUERY_CHARS
            or _CONTROL.search(normalized_query)
        ):
            raise Crawl4AICloudError("invalid_query")
        if (
            isinstance(limit, bool)
            or not isinstance(limit, int)
            or not 1 <= limit <= MAX_SEARCH_RESULTS
        ):
            raise Crawl4AICloudError("invalid_limit")
        _status, headers, body = self._get("/search", params={"q": normalized_query, "rich": "0"})
        payload = self._json(body)
        rows = payload.get("results")
        if not isinstance(rows, list):
            raise Crawl4AICloudError("invalid_response", request_dispatched=True)
        hits: list[Crawl4AIWebHit] = []
        for row in rows[:limit]:
            if not isinstance(row, dict):
                continue
            safe_url = _safe_public_url(row.get("url"))
            title = row.get("title")
            if safe_url is None or not isinstance(title, str) or not title.strip():
                continue
            snippet = row.get("snippet")
            source = row.get("source")
            hits.append(
                Crawl4AIWebHit(
                    title=" ".join(title.split())[:1000],
                    url=safe_url[0],
                    snippet=" ".join(snippet.split())[:1200] if isinstance(snippet, str) else None,
                    source=source[:32] if isinstance(source, str) else None,
                    rank=len(hits) + 1,
                    normalized_domain=safe_url[1],
                )
            )
        cost = _reported_number(headers, "x-c4-cost")
        return Crawl4AIWebSearchResult(
            query=normalized_query,
            provider="Crawl4AI Cloud",
            searched_at=datetime.now(UTC).isoformat(),
            hits=tuple(hits),
            reported_cost_credits=cost,
            balance_credits=_reported_number(headers, "x-c4-balance"),
            allowance_left_credits=_reported_number(headers, "x-c4-allowance-left"),
            usage_status="reported" if cost is not None else "cost_unknown",
        )

    def balance(self) -> Crawl4AIBalance:
        """Read current account allowance. This method is GET-only and never changes billing."""
        _status, _headers, body = self._get("/v1/billing/balance")
        payload = self._json(body)
        plan = payload.get("plan_name") or payload.get("plan") or payload.get("tier")
        if isinstance(plan, dict):
            plan = plan.get("name") or plan.get("tier")
        # The balance endpoint exposes the free pool separately from the plan
        # allowance. Keep both values distinct: the latter may include more than
        # the user's remaining free credits and must not authorize dispatch alone.
        allowance_mc = _number(payload.get("allowance_mc"))
        free_mc = _number(payload.get("free_mc"))
        allowance = (
            allowance_mc / 1000
            if allowance_mc is not None
            else _number(payload.get("allowance_left", payload.get("credits_month")))
        )
        balance = _number(payload.get("free"))
        if balance is None and free_mc is not None:
            balance = free_mc / 1000
        if balance is not None and free_mc is not None:
            balance = min(balance, free_mc / 1000)
        if balance is not None and allowance is not None:
            balance = min(balance, allowance)
        return Crawl4AIBalance(
            plan=plan.strip().casefold() if isinstance(plan, str) and plan.strip() else None,
            balance_credits=balance,
            allowance_left_credits=allowance,
            raw_status=(
                "reported"
                if isinstance(plan, str) and balance is not None and allowance is not None
                else "unknown"
            ),
        )


def _number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        return None
    try:
        number = float(value)
    except ValueError:
        return None
    return number if math.isfinite(number) and number >= 0 else None
