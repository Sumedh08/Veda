"""Bounded HTML retrieval behind separate document-rights and host-policy gates.

The transport resolves the host itself and connects to the checked IP address,
so the HTTP request cannot silently perform a second DNS lookup after validation.
"""

import hashlib
import http.client
import ipaddress
import math
import re
import socket
import ssl
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from dataclasses import dataclass
from datetime import UTC, date, datetime
from html.parser import HTMLParser
from threading import BoundedSemaphore
from urllib.parse import quote, urljoin, urlsplit, urlunsplit

from app.research.origin_rate_limit import (
    DatabaseOriginRequestLimiter,
    OriginRateLimitUnavailable,
    OriginRequestDeferred,
)
from app.research.retrieval_rights import (
    PERMITTED_LICENSES,
    ReviewedHostPolicy,
    reviewed_host_policy,
)
from app.research.rights_policy import RightsDecision

MAX_DOCUMENT_BYTES = 2_000_000
MAX_ROBOTS_BYTES = 512 * 1024
MAX_REDIRECTS = 3
MAX_ROBOTS_REDIRECTS = 5
MAX_TOTAL_SECONDS = 8.0
MAX_DNS_SECONDS = 2.0
MAX_EXTRACTED_CHARACTERS = 100_000
ALLOWED_MEDIA_TYPES = {"text/html", "application/xhtml+xml"}
REDIRECT_STATUSES = {301, 302, 303, 307, 308}
ROBOTS_CACHE_SECONDS = 24 * 60 * 60
_DNS_POOL = ThreadPoolExecutor(max_workers=4, thread_name_prefix="veda-dns")
_DNS_SLOTS = BoundedSemaphore(4)


def _is_private_research_decision(value: RightsDecision | None) -> bool:
    return bool(
        isinstance(value, RightsDecision)
        and value.basis == "india_private_research_exception_candidate"
        and value.access == "PERMITTED"
        and value.analysis == "PERMITTED_WITH_LIMITATIONS"
        and value.retention == "LIMITED_EXCERPTS"
        and value.sharing == "CITATION_ONLY"
        and value.max_retained_passages is not None
        and value.max_retained_verbatim_characters is not None
    )


def _host_within_domains(host: str, domains: tuple[str, ...]) -> bool:
    try:
        normalized_host = host.encode("idna").decode("ascii").casefold().rstrip(".")
        normalized_domains = [
            domain.encode("idna").decode("ascii").casefold().rstrip(".")
            for domain in domains
            if isinstance(domain, str) and domain.strip() and "*" not in domain
        ]
    except UnicodeError:
        return False
    return any(
        normalized_host == domain or normalized_host.endswith("." + domain)
        for domain in normalized_domains
    )


def _system_resolve(host: str, port: int, socktype: int):
    """Resolve host addresses with an explicit family and socket type."""
    return socket.getaddrinfo(
        host,
        port,
        family=socket.AF_UNSPEC,
        type=socktype,
    )


@dataclass(frozen=True)
class SafeHTMLAccessContext:
    """Host and robots checks completed before a document request failed."""

    final_host: str
    host_policy_id: str
    host_terms_url: str
    robots_status: str
    robots_http_status: int | None = None


class SafeFetchError(Exception):
    """Sanitized retrieval error safe to persist or return to a client."""

    def __init__(self, code: str, message: str, *, retry_after_seconds: float | None = None):
        super().__init__(message)
        self.code = code
        self.retry_after_seconds = retry_after_seconds
        self.access_context: SafeHTMLAccessContext | None = None


@dataclass(frozen=True)
class SafeHTMLDocument:
    text: str
    sha256: str
    media_type: str
    final_host: str
    retrieved_at: datetime
    truncated: bool
    host_policy_id: str
    host_terms_url: str
    robots_status: str
    robots_http_status: int | None = None


@dataclass(frozen=True)
class _RobotsRule:
    allowed: bool
    pattern: str


@dataclass(frozen=True)
class _RobotsGroup:
    agents: tuple[str, ...]
    rules: tuple[_RobotsRule, ...]
    crawl_delay_seconds: float | None = None


@dataclass(frozen=True)
class _RobotsCacheEntry:
    groups: tuple[_RobotsGroup, ...]
    status: str
    expires_at: float
    http_status_code: int | None = None

    @property
    def crawl_delay_seconds(self) -> float:
        return robots_crawl_delay(self.groups)


def parse_robots_txt(content: bytes) -> tuple[_RobotsGroup, ...]:
    """Parse the RFC 9309 user-agent and Allow/Disallow subset Veda needs."""
    try:
        text = content.decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        raise SafeFetchError(
            "robots_invalid_encoding", "The host access policy is invalid."
        ) from None
    if any(ord(character) < 32 and character not in "\r\n\t" for character in text):
        raise SafeFetchError("robots_invalid_content", "The host access policy is invalid.")

    groups: list[_RobotsGroup] = []
    agents: list[str] = []
    rules: list[_RobotsRule] = []
    crawl_delay_seconds: float | None = None

    def finish_group() -> None:
        nonlocal agents, rules, crawl_delay_seconds
        if agents:
            groups.append(_RobotsGroup(tuple(agents), tuple(rules), crawl_delay_seconds))
        agents = []
        rules = []
        crawl_delay_seconds = None

    for raw_line in text.splitlines():
        line = raw_line.split("#", 1)[0].strip()
        if not line or ":" not in line:
            continue
        key, value = (part.strip() for part in line.split(":", 1))
        normalized_key = key.casefold()
        if normalized_key == "user-agent":
            if rules:
                finish_group()
            if value and re.fullmatch(r"[A-Za-z0-9_-]+|\*", value):
                agents.append(value)
            continue
        if normalized_key in {"allow", "disallow"} and agents:
            # An empty pattern carries no restriction under RFC 9309.
            if value:
                rules.append(_RobotsRule(normalized_key == "allow", value))
        elif normalized_key == "crawl-delay" and agents:
            try:
                delay = float(value)
                if not math.isfinite(delay) or delay < 0 or delay > 86_400:
                    raise ValueError
                crawl_delay_seconds = max(crawl_delay_seconds or 0, delay)
            except ValueError:
                # An unparseable delay in a matching group cannot safely be ignored.
                crawl_delay_seconds = math.inf
    finish_group()
    return tuple(groups)


def robots_allows(
    groups: tuple[_RobotsGroup, ...], path_and_query: str, *, product_token: str = "VedaResearch"
) -> bool:
    """Apply case-insensitive agent selection and longest matching path rule."""
    exact_groups = [
        group
        for group in groups
        if any(agent.casefold() == product_token.casefold() for agent in group.agents)
    ]
    selected = exact_groups or [group for group in groups if "*" in group.agents]
    candidates: list[tuple[int, bool]] = []
    for group in selected:
        for rule in group.rules:
            pattern = rule.pattern
            terminal = pattern.endswith("$")
            if terminal:
                pattern = pattern[:-1]
            expression = "^" + "".join(
                ".*" if character == "*" else re.escape(character) for character in pattern
            )
            expression += "$" if terminal else ".*"
            if re.match(expression, path_and_query):
                specificity = len(pattern.replace("*", "").encode("utf-8"))
                candidates.append((specificity, rule.allowed))
    if not candidates:
        return True
    specificity = max(length for length, _allowed in candidates)
    # RFC 9309 recommends Allow on equivalent matches.
    return any(allowed for length, allowed in candidates if length == specificity)


def robots_crawl_delay(
    groups: tuple[_RobotsGroup, ...], *, product_token: str = "VedaResearch"
) -> float:
    exact_groups = [
        group
        for group in groups
        if any(agent.casefold() == product_token.casefold() for agent in group.agents)
    ]
    selected = exact_groups or [group for group in groups if "*" in group.agents]
    return max((group.crawl_delay_seconds or 0 for group in selected), default=0)


class _VisibleTextParser(HTMLParser):
    _hidden = {"script", "style", "noscript", "svg", "template", "iframe", "object"}
    _excluded = {"nav", "footer", "aside", "form", "dialog"}
    _primary = {"main", "article"}
    _void = {
        "area",
        "base",
        "br",
        "col",
        "embed",
        "hr",
        "img",
        "input",
        "link",
        "meta",
        "param",
        "source",
        "track",
        "wbr",
    }
    _blocks = {
        "address",
        "article",
        "blockquote",
        "br",
        "dd",
        "div",
        "dl",
        "dt",
        "figcaption",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "li",
        "main",
        "ol",
        "p",
        "pre",
        "section",
        "table",
        "td",
        "th",
        "tr",
        "ul",
    }

    def __init__(self, max_characters: int):
        super().__init__(convert_charrefs=True)
        self.max_characters = max_characters
        self.parts: list[str] = []
        self.primary_parts: list[str] = []
        self.character_count = 0
        self.primary_character_count = 0
        self.hidden_depth = 0
        self.primary_depth = 0
        self.suppressed_depth = 0
        self.frames: list[tuple[str, bool, bool, bool]] = []
        self.fallback_truncated = False
        self.primary_truncated = False
        self.truncated = False

    def handle_starttag(self, tag: str, attrs) -> None:
        normalized = tag.lower()
        suppressed = (
            self.suppressed_depth > 0
            or normalized in self._hidden
            or normalized in self._excluded
            or (normalized == "header" and self.primary_depth == 0)
        )
        hidden = normalized in self._hidden or self.hidden_depth > 0
        primary = not suppressed and normalized in self._primary
        if normalized not in self._void:
            self.frames.append((normalized, suppressed, hidden, primary))
        if suppressed:
            self.suppressed_depth += 1
        if hidden:
            self.hidden_depth += 1
        if primary:
            self.primary_depth += 1
        if not self.suppressed_depth and normalized in self._blocks:
            self._append("\n")

    def handle_endtag(self, tag: str) -> None:
        normalized = tag.lower()
        matching_index = next(
            (
                index
                for index in range(len(self.frames) - 1, -1, -1)
                if self.frames[index][0] == normalized
            ),
            None,
        )
        if matching_index is not None:
            closing_frames = self.frames[matching_index:]
            del self.frames[matching_index:]
            for _name, suppressed, hidden, primary in reversed(closing_frames):
                if suppressed:
                    self.suppressed_depth = max(0, self.suppressed_depth - 1)
                if hidden:
                    self.hidden_depth = max(0, self.hidden_depth - 1)
                if primary:
                    self.primary_depth = max(0, self.primary_depth - 1)
        if not self.suppressed_depth and normalized in self._blocks:
            self._append("\n")

    def handle_data(self, data: str) -> None:
        if not self.suppressed_depth:
            self._append(data)

    def _append(self, value: str) -> None:
        primary = self.primary_depth > 0
        parts = self.primary_parts if primary else self.parts
        count = self.primary_character_count if primary else self.character_count
        if count >= self.max_characters:
            if primary:
                self.primary_truncated = True
            else:
                self.fallback_truncated = True
            return
        remaining = self.max_characters - count
        if len(value) > remaining:
            value = value[:remaining]
            if primary:
                self.primary_truncated = True
            else:
                self.fallback_truncated = True
        parts.append(value)
        if primary:
            self.primary_character_count += len(value)
        else:
            self.character_count += len(value)

    def paragraphs(self) -> list[str]:
        primary_text = "".join(self.primary_parts).strip()
        selected_parts = self.primary_parts if primary_text else self.parts
        self.truncated = self.primary_truncated if primary_text else self.fallback_truncated
        text = "".join(selected_parts)
        return [
            normalized
            for line in text.splitlines()
            if (normalized := re.sub(r"\s+", " ", line).strip())
        ]


def extract_html_paragraphs(
    html_text: str, *, max_characters: int = MAX_EXTRACTED_CHARACTERS
) -> tuple[list[str], bool]:
    parser = _VisibleTextParser(max_characters=max_characters)
    try:
        parser.feed(html_text)
        parser.close()
    except Exception:
        raise SafeFetchError(
            "invalid_html", "The retrieved HTML could not be parsed safely."
        ) from None
    return parser.paragraphs(), parser.truncated


class SafeHTMLFetcher:
    document_byte_limit = MAX_DOCUMENT_BYTES

    def __init__(
        self,
        *,
        resolver: Callable | None = None,
        connector: Callable = socket.create_connection,
        ssl_context: ssl.SSLContext | None = None,
        max_bytes: int = MAX_DOCUMENT_BYTES,
        max_redirects: int = MAX_REDIRECTS,
        timeout_seconds: float = MAX_TOTAL_SECONDS,
        host_policy_checker: Callable[[str, str], ReviewedHostPolicy] = reviewed_host_policy,
        origin_request_limiter: DatabaseOriginRequestLimiter | None = None,
    ):
        self.resolver = _system_resolve if resolver is None else resolver
        self.connector = connector
        self.ssl_context = ssl_context or ssl.create_default_context()
        self.max_bytes = min(max(1, max_bytes), self.document_byte_limit)
        self.max_redirects = min(max(0, max_redirects), MAX_REDIRECTS)
        self.timeout_seconds = min(max(0.0, timeout_seconds), MAX_TOTAL_SECONDS)
        self.host_policy_checker = host_policy_checker
        self.origin_request_limiter = origin_request_limiter
        self._robots_cache: dict[str, _RobotsCacheEntry] = {}

    def fetch_html(
        self,
        url: str,
        *,
        license_name: str | None,
        rights_decision: RightsDecision | None = None,
    ) -> SafeHTMLDocument:
        license_code = (license_name or "").strip().casefold()
        private_research = license_code not in PERMITTED_LICENSES
        if private_research and not _is_private_research_decision(rights_decision):
            raise SafeFetchError(
                "rights_basis_unresolved",
                "Unlicensed HTML requires a verified, applicable private-research decision.",
            )
        if not isinstance(url, str) or not url or len(url) > 2000:
            raise SafeFetchError("invalid_url", "The source URL is invalid.")

        deadline = time.monotonic() + self.timeout_seconds
        current_url = url
        original_scheme = ""
        visited: set[str] = set()
        host_policy: ReviewedHostPolicy | None = None
        robots_status = ""
        for redirect_count in range(self.max_redirects + 1):
            target = self._target(current_url)
            host_policy = self._check_host_policy(
                target, license_code, rights_decision=rights_decision if private_research else None
            )
            robots_status = ""
            robots_policy = self._check_robots(
                target,
                deadline,
                license_code,
                host_policy,
                rights_decision=rights_decision if private_research else None,
            )
            robots_status = robots_policy.status
            if not original_scheme:
                original_scheme = target.scheme
            canonical = urlunsplit((target.scheme, target.netloc, target.path, target.query, ""))
            if canonical in visited:
                raise SafeFetchError("redirect_loop", "The source redirected repeatedly.")
            visited.add(canonical)

            try:
                response, sock = self._request(
                    target,
                    deadline,
                    minimum_interval_seconds=max(
                        host_policy.minimum_interval_seconds,
                        robots_policy.crawl_delay_seconds,
                    ),
                )
            except SafeFetchError as exc:
                self._attach_access_context(
                    exc, target, host_policy, robots_status, robots_policy.http_status_code
                )
                raise
            try:
                if response.status in REDIRECT_STATUSES:
                    location = response.getheader("Location")
                    if not location or redirect_count >= self.max_redirects:
                        raise SafeFetchError(
                            "redirect_limit", "The source exceeded the redirect limit."
                        )
                    next_url = urljoin(canonical, location)
                    next_target = self._target(next_url)
                    if original_scheme == "https" and next_target.scheme != "https":
                        raise SafeFetchError(
                            "redirect_downgrade", "HTTPS redirects cannot downgrade to HTTP."
                        )
                    current_url = next_url
                    continue
                if response.status != 200:
                    status_codes = {
                        401: "authentication_required",
                        403: "access_denied",
                        404: "not_found",
                        429: "rate_limited",
                    }
                    raise SafeFetchError(
                        status_codes.get(response.status, "http_status"),
                        "The source did not return a successful response.",
                    )

                media_type = response.headers.get_content_type().lower()
                if media_type not in ALLOWED_MEDIA_TYPES:
                    raise SafeFetchError(
                        "unsupported_media_type",
                        "Only HTML documents are accepted by this retrieval path.",
                    )
                content_encoding = (
                    response.getheader("Content-Encoding", "identity") or "identity"
                ).lower()
                if content_encoding not in {"", "identity"}:
                    raise SafeFetchError(
                        "unsupported_content_encoding",
                        "Compressed source responses are not accepted.",
                    )
                content_length = response.getheader("Content-Length")
                if content_length:
                    try:
                        parsed_length = int(content_length)
                        if parsed_length < 0:
                            raise ValueError
                        if parsed_length > self.max_bytes:
                            raise SafeFetchError(
                                "response_too_large", "The source exceeds the byte limit."
                            )
                    except ValueError:
                        raise SafeFetchError(
                            "invalid_response", "The source response is malformed."
                        ) from None

                try:
                    body = self._read_body(response, sock, deadline)
                except TimeoutError:
                    raise SafeFetchError(
                        "timeout", "Source retrieval exceeded the time limit."
                    ) from None
                except OSError:
                    raise SafeFetchError(
                        "network_error", "The public source could not be retrieved safely."
                    ) from None
                charset = response.headers.get_content_charset() or "utf-8"
                try:
                    html_text = body.decode(charset, errors="replace")
                except LookupError:
                    html_text = body.decode("utf-8", errors="replace")
                paragraphs, truncated = extract_html_paragraphs(html_text)
                text = "\n\n".join(paragraphs).strip()
                if not text:
                    raise SafeFetchError(
                        "empty_document", "The source contained no readable HTML text."
                    )
                return SafeHTMLDocument(
                    text=text,
                    sha256=hashlib.sha256(body).hexdigest(),
                    media_type=media_type,
                    final_host=target.host,
                    retrieved_at=datetime.now(UTC),
                    truncated=truncated,
                    host_policy_id=host_policy.policy_id,
                    host_terms_url=host_policy.terms_url,
                    robots_status=robots_status,
                    robots_http_status=robots_policy.http_status_code,
                )
            except SafeFetchError as exc:
                self._attach_access_context(
                    exc, target, host_policy, robots_status, robots_policy.http_status_code
                )
                raise
            finally:
                response.close()
                sock.close()
        raise SafeFetchError("redirect_limit", "The source exceeded the redirect limit.")

    def _check_host_policy(
        self,
        target: "_Target",
        license_code: str,
        *,
        rights_decision: RightsDecision | None = None,
    ) -> ReviewedHostPolicy:
        if rights_decision is not None:
            if not _is_private_research_decision(rights_decision):
                raise SafeFetchError(
                    "rights_basis_unresolved", "The private-research rights decision is not usable."
                )
            if target.scheme != "https" or target.port not in {None, 443}:
                raise SafeFetchError(
                    "private_research_requires_https", "Private-research retrieval requires HTTPS."
                )
            if not _host_within_domains(target.host, rights_decision.verified_domains):
                raise SafeFetchError(
                    "verified_domain_boundary",
                    "The URL is outside the verified organization domain.",
                )
            return ReviewedHostPolicy(
                host=target.host,
                policy_id=rights_decision.policy_version,
                terms_url=rights_decision.terms_url or "",
                reviewed_at=date.today(),
                licenses=frozenset(),
                minimum_interval_seconds=1.0,
            )
        try:
            return self.host_policy_checker(target.host, license_code)
        except ValueError as exc:
            code = str(exc)
            if code not in {
                "host_policy_registry_invalid",
                "host_policy_unknown",
                "host_policy_stale",
                "host_license_not_reviewed",
            }:
                code = "host_policy_unknown"
            messages = {
                "host_policy_registry_invalid": "The reviewed retrieval-host registry is invalid.",
                "host_policy_unknown": "The source host has no reviewed retrieval policy.",
                "host_policy_stale": "The source host retrieval-policy review has expired.",
                "host_license_not_reviewed": "This license is not covered by the source-host review.",
            }
            raise SafeFetchError(code, messages[code]) from None
        except Exception:
            raise SafeFetchError(
                "host_policy_unknown", "The source host has no reviewed retrieval policy."
            ) from None

    @staticmethod
    def _attach_access_context(
        error: SafeFetchError,
        target: "_Target",
        host_policy: ReviewedHostPolicy,
        robots_status: str,
        robots_http_status: int | None,
    ) -> None:
        if robots_status in {"rules_checked", "unavailable_4xx"}:
            error.access_context = SafeHTMLAccessContext(
                final_host=target.host,
                host_policy_id=host_policy.policy_id,
                host_terms_url=host_policy.terms_url,
                robots_status=robots_status,
                robots_http_status=robots_http_status,
            )

    def _check_robots(
        self,
        target: "_Target",
        deadline: float,
        license_code: str,
        initial_policy: ReviewedHostPolicy,
        *,
        rights_decision: RightsDecision | None = None,
    ) -> _RobotsCacheEntry:
        origin = f"{target.scheme}://{target.netloc}"
        cached = self._robots_cache.get(origin)
        if cached is None or cached.expires_at <= time.monotonic():
            cached = self._load_robots_policy(
                target,
                origin,
                deadline,
                license_code,
                initial_policy,
                rights_decision=rights_decision,
            )
            self._robots_cache[origin] = cached
        if not robots_allows(cached.groups, _robots_path_and_query(target)):
            raise SafeFetchError(
                "robots_disallowed", "The host robots policy disallows this source path."
            )
        if not math.isfinite(cached.crawl_delay_seconds):
            raise SafeFetchError(
                "robots_invalid_crawl_delay",
                "The host access policy contains an invalid crawl delay.",
            )
        return cached

    def _load_robots_policy(
        self,
        initial_target: "_Target",
        origin: str,
        deadline: float,
        license_code: str,
        initial_policy: ReviewedHostPolicy,
        *,
        rights_decision: RightsDecision | None = None,
    ) -> _RobotsCacheEntry:
        current_url = f"{origin}/robots.txt"
        visited: set[str] = set()
        try:
            for redirect_count in range(MAX_ROBOTS_REDIRECTS + 1):
                target = self._target(current_url)
                target_policy = (
                    initial_policy
                    if target.origin == initial_target.origin
                    else self._check_host_policy(
                        target, license_code, rights_decision=rights_decision
                    )
                )
                canonical = urlunsplit(
                    (target.scheme, target.netloc, target.path, target.query, "")
                )
                if canonical in visited:
                    raise SafeFetchError(
                        "robots_redirect_loop", "The host access policy is unavailable."
                    )
                visited.add(canonical)
                response, sock = self._request(
                    target,
                    deadline,
                    accept_header="text/plain",
                    minimum_interval_seconds=target_policy.minimum_interval_seconds,
                )
                try:
                    if response.status in REDIRECT_STATUSES:
                        location = response.getheader("Location")
                        if not location or redirect_count >= MAX_ROBOTS_REDIRECTS:
                            raise SafeFetchError(
                                "robots_redirect_limit", "The host access policy is unavailable."
                            )
                        next_url = urljoin(canonical, location)
                        next_target = self._target(next_url)
                        if initial_target.scheme == "https" and next_target.scheme != "https":
                            raise SafeFetchError(
                                "robots_redirect_downgrade",
                                "The host access policy is unavailable.",
                            )
                        current_url = next_url
                        continue
                    # RFC 9309 classifies HTTP 4xx as unavailable, for which a
                    # crawler MAY access resources. 429 is a rate-limit defer;
                    # 5xx and network failures remain complete-disallow.
                    if response.status == 429:
                        raise SafeFetchError(
                            "robots_rate_limited", "The host robots policy is rate limited."
                        )
                    if 400 <= response.status <= 499:
                        return _RobotsCacheEntry(
                            groups=(),
                            status="unavailable_4xx",
                            expires_at=time.monotonic() + ROBOTS_CACHE_SECONDS,
                            http_status_code=response.status,
                        )
                    if 500 <= response.status <= 599:
                        raise SafeFetchError(
                            "robots_unreachable", "The host access policy is unavailable."
                        )
                    if response.status != 200:
                        raise SafeFetchError(
                            "robots_unavailable", "The host access policy is unavailable."
                        )
                    if response.headers.get_content_type().lower() != "text/plain":
                        raise SafeFetchError(
                            "robots_invalid_media_type", "The host access policy is invalid."
                        )
                    encoding = (
                        response.getheader("Content-Encoding", "identity") or "identity"
                    ).lower()
                    if encoding not in {"", "identity"}:
                        raise SafeFetchError(
                            "robots_invalid_encoding", "The host access policy is invalid."
                        )
                    content_length = response.getheader("Content-Length")
                    if content_length:
                        try:
                            parsed_length = int(content_length)
                            if parsed_length < 0:
                                raise ValueError
                            if parsed_length > MAX_ROBOTS_BYTES:
                                raise SafeFetchError(
                                    "robots_too_large", "The host access policy is too large."
                                )
                        except ValueError:
                            raise SafeFetchError(
                                "robots_invalid_response", "The host access policy is invalid."
                            ) from None
                    body = self._read_body(response, sock, deadline, byte_limit=MAX_ROBOTS_BYTES)
                    groups = parse_robots_txt(body)
                    return _RobotsCacheEntry(
                        groups=groups,
                        status="rules_checked",
                        expires_at=time.monotonic() + ROBOTS_CACHE_SECONDS,
                        http_status_code=200,
                    )
                finally:
                    response.close()
                    sock.close()
        except SafeFetchError as exc:
            if exc.code.startswith("robots_"):
                code = exc.code
            elif exc.code in {
                "private_address",
                "dns_failure",
                "timeout",
                "origin_rate_limit_unavailable",
                "origin_request_deferred",
            }:
                raise exc
            elif exc.code == "response_too_large":
                code = "robots_too_large"
            else:
                code = "robots_unreachable"
            raise SafeFetchError(
                code, "The host access policy could not be verified safely."
            ) from None
        except (TimeoutError, OSError, http.client.HTTPException):
            raise SafeFetchError(
                "robots_unreachable", "The host access policy could not be verified safely."
            ) from None
        raise SafeFetchError("robots_redirect_limit", "The host access policy is unavailable.")

    def _target(self, url: str):
        if (
            not isinstance(url, str)
            or len(url) > 2000
            or any(ord(character) < 32 for character in url)
        ):
            raise SafeFetchError("invalid_url", "The source URL is invalid.")
        try:
            parsed = urlsplit(url)
            port = parsed.port
        except ValueError:
            raise SafeFetchError("invalid_url", "The source URL is invalid.") from None
        scheme = parsed.scheme.lower()
        if scheme not in {"http", "https"}:
            raise SafeFetchError("unsupported_scheme", "Only HTTP and HTTPS sources are accepted.")
        if parsed.username is not None or parsed.password is not None or not parsed.hostname:
            raise SafeFetchError("invalid_url", "Credentials and missing hosts are not accepted.")
        if "%" in parsed.hostname:
            raise SafeFetchError("invalid_url", "Scoped or encoded host names are not accepted.")
        try:
            host = str(ipaddress.ip_address(parsed.hostname))
        except ValueError:
            try:
                host = parsed.hostname.encode("idna").decode("ascii").lower()
            except UnicodeError:
                raise SafeFetchError("invalid_url", "The source host name is invalid.") from None
        default_port = 443 if scheme == "https" else 80
        port = default_port if port is None else port
        if not 1 <= port <= 65535:
            raise SafeFetchError("invalid_url", "The source port is invalid.")
        if port != default_port:
            # Host review and the checked-in policy registry are scoped to a
            # hostname, not a service endpoint. Until reviews bind policies to
            # explicit ports, allow only the standard HTTP(S) service port.
            raise SafeFetchError(
                "unreviewed_port",
                "Only the standard HTTP or HTTPS service port is accepted.",
            )
        path = quote(parsed.path or "/", safe="/%:@!$&'()*+,;=-._~")
        query = quote(parsed.query, safe="/?@!$&'()*+,;=:-._~%")
        return _Target(scheme, host, port, path, query)

    def _resolve_public_ips(self, host: str, port: int, deadline: float) -> list[str]:
        remaining = deadline - time.monotonic()
        if remaining <= 0 or not _DNS_SLOTS.acquire(timeout=min(MAX_DNS_SECONDS, remaining)):
            raise SafeFetchError("timeout", "Source host lookup exceeded the time limit.")
        future = _DNS_POOL.submit(self.resolver, host, port, socket.SOCK_STREAM)
        future.add_done_callback(lambda _completed: _DNS_SLOTS.release())
        try:
            records = future.result(timeout=min(MAX_DNS_SECONDS, remaining))
        except FutureTimeout:
            raise SafeFetchError("timeout", "Source host lookup exceeded the time limit.") from None
        except OSError:
            raise SafeFetchError("dns_failure", "The source host could not be resolved.") from None
        except Exception:
            raise SafeFetchError("dns_failure", "The source host could not be resolved.") from None

        addresses: list[str] = []
        for record in records:
            family, socktype, _protocol, _canonical_name, address = record
            if family not in {socket.AF_INET, socket.AF_INET6} or socktype != socket.SOCK_STREAM:
                continue
            ip_text = address[0].split("%", 1)[0]
            try:
                parsed_address = ipaddress.ip_address(ip_text)
            except ValueError:
                raise SafeFetchError(
                    "dns_failure", "The source host resolved to an invalid address."
                ) from None
            if not parsed_address.is_global:
                raise SafeFetchError(
                    "private_address", "The source host resolved to a non-public address."
                )
            addresses.append(str(parsed_address))
        if not addresses:
            raise SafeFetchError("dns_failure", "The source host has no public network address.")
        return list(dict.fromkeys(addresses))

    def _request(
        self,
        target: "_Target",
        deadline: float,
        *,
        accept_header: str = "text/html, application/xhtml+xml",
        minimum_interval_seconds: float = 0.0,
    ):
        if minimum_interval_seconds > 0 and self.origin_request_limiter is None:
            raise SafeFetchError(
                "origin_rate_limit_unavailable",
                "The host request interval cannot be enforced safely.",
            )
        addresses = self._resolve_public_ips(target.host, target.port, deadline)
        last_error: OSError | None = None
        for address in addresses:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise SafeFetchError("timeout", "Source retrieval exceeded the time limit.")
            sock = None
            try:
                sock = self.connector((address, target.port), timeout=remaining)
                sock.settimeout(max(0.1, deadline - time.monotonic()))
                if target.scheme == "https":
                    sock = self.ssl_context.wrap_socket(sock, server_hostname=target.host)
                    sock.settimeout(max(0.1, deadline - time.monotonic()))
                host_header = f"[{target.host}]" if ":" in target.host else target.host
                if target.port != (443 if target.scheme == "https" else 80):
                    host_header = f"{host_header}:{target.port}"
                request_path = target.path + (f"?{target.query}" if target.query else "")
                request_bytes = (
                    f"GET {request_path} HTTP/1.1\r\n"
                    f"Host: {host_header}\r\n"
                    "User-Agent: VedaResearch/0.1 (licensed scholarly retrieval)\r\n"
                    f"Accept: {accept_header}\r\n"
                    "Accept-Encoding: identity\r\n"
                    "Connection: close\r\n\r\n"
                ).encode("ascii")
                if self.origin_request_limiter is not None:
                    try:
                        self.origin_request_limiter.acquire(
                            target.origin,
                            minimum_interval_seconds,
                            deadline=deadline,
                        )
                    except OriginRequestDeferred as exc:
                        raise SafeFetchError(
                            "origin_request_deferred",
                            "The host request interval exceeds this retrieval step's time limit.",
                            retry_after_seconds=exc.retry_after_seconds,
                        ) from None
                    except OriginRateLimitUnavailable:
                        raise SafeFetchError(
                            "origin_rate_limit_unavailable",
                            "The host request interval cannot be enforced safely.",
                        ) from None
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise SafeFetchError("timeout", "Source retrieval exceeded the time limit.")
                sock.settimeout(remaining)
                sock.sendall(request_bytes)
                response = http.client.HTTPResponse(sock, method="GET")
                response.begin()
                return response, sock
            except (OSError, ssl.SSLError, http.client.HTTPException) as exc:
                if sock is not None:
                    sock.close()
                last_error = exc
            except SafeFetchError:
                if sock is not None:
                    sock.close()
                raise
        if time.monotonic() >= deadline:
            raise SafeFetchError("timeout", "Source retrieval exceeded the time limit.") from None
        raise SafeFetchError(
            "network_error", "The public source could not be retrieved safely."
        ) from last_error

    def _read_body(
        self,
        response: http.client.HTTPResponse,
        sock,
        deadline: float,
        *,
        byte_limit: int | None = None,
    ) -> bytes:
        maximum = self.max_bytes if byte_limit is None else min(byte_limit, MAX_ROBOTS_BYTES)
        body = bytearray()
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise SafeFetchError("timeout", "Source retrieval exceeded the time limit.")
            sock.settimeout(remaining)
            chunk = response.read(min(64_000, maximum - len(body) + 1))
            if not chunk:
                return bytes(body)
            body.extend(chunk)
            if len(body) > maximum:
                raise SafeFetchError("response_too_large", "The source exceeds the byte limit.")


@dataclass(frozen=True)
class _Target:
    scheme: str
    host: str
    port: int
    path: str
    query: str

    @property
    def netloc(self) -> str:
        host = f"[{self.host}]" if ":" in self.host else self.host
        default_port = 443 if self.scheme == "https" else 80
        return host if self.port == default_port else f"{host}:{self.port}"

    @property
    def origin(self) -> str:
        return f"{self.scheme}://{self.netloc}"


def _robots_path_and_query(target: _Target) -> str:
    path = target.path + (f"?{target.query}" if target.query else "")
    unreserved = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~"

    def normalize(match: re.Match[str]) -> str:
        character = chr(int(match.group(1), 16))
        return character if character in unreserved else f"%{match.group(1).upper()}"

    return re.sub(r"%([0-9A-Fa-f]{2})", normalize, path)
