"""Build bounded keyword queries from an unchanged research question and scope."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from dataclasses import replace as dataclass_replace
from urllib.parse import urlsplit

MAX_QUERY_CHARS = 300
MAX_QUERY_TERMS = 32
MAX_INSTITUTIONAL_CATALOG_TERMS = 5
MAX_OPENAIRE_ORGANIZATION_TOPIC_TERMS = 2
MAX_GENERAL_WEB_DISCOVERY_QUERIES = 3
MAX_GENERAL_WEB_DOMAIN_CANDIDATES = 6

_TOKEN = re.compile(r"[a-z]+(?:[''][a-z]+)?|[0-9]+", re.IGNORECASE)
_STOPWORDS = frozenset(
    "a about across all an and are as at be been by can could did do does for from had has "
    "have how if in into is it its may might more most of on or our should than that the their "
    "them then there these they this those through to under using was were what when where which "
    "while who why will with would evidence study studies research question assess assessed "
    "evaluate evaluation effect effects impact impacts whether show shows shown based result "
    "results decision objective consider considering improve improves increase increased "
    "increasing reduce reduced reducing determine establish report reported findings outcome "
    "outcomes employee employees person people team teams company companies organization "
    "organizations rollout pilot hypothetical current existing workflow process versus compared "
    "compare without against across us usa united states one two three four five six seven eight "
    "nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen twenty "
    "thirty forty fifty hundred thousand monthly annually yearly week weeks month months year "
    "years quarter quarters day days per sometimes different synthesize synthesizing synthesis".split()
)
_OPENAIRE_ORGANIZATION_STOPWORDS = frozenset(
    "uk united kingdom address balancing balance costs cost delivery".split()
)
_NON_ORIGINAL_PUBLICATION_HOSTS = frozenset(
    {
        "academia.edu",
        "bing.com",
        "google.com",
        "linkedin.com",
        "researchgate.net",
        "semanticscholar.org",
        "scribd.com",
        "twitter.com",
        "x.com",
        "yahoo.com",
    }
)
_PUBLICATION_CUES = frozenset(
    "analysis article assessment evidence findings impact journal paper policy publication "
    "research review study studies working report whitepaper pdf thesis dataset data".split()
)
_OFFICIAL_DOCUMENT_PATHS = (
    "/publications/",
    "/publication/",
    "/reports/",
    "/report/",
    "/research/",
    "/working-papers/",
    "/working-paper/",
    "/papers/",
    "/uploads/",
    "/documents/",
    "/sites/default/files/",
)
_EDITORIAL_PATHS = ("/article/", "/news/", "/blog/", "/press-release/")
_DATED_EDITORIAL_PATH = re.compile(r"/(?:[a-z0-9-]+/)?20[0-9]{2}/[a-z]{3,9}/[0-9]{1,2}/")
_DIRECT_PUBLICATION_CUES = frozenset(
    "data dataset paper papers publication publications report reports study studies thesis "
    "whitepaper working methodology".split()
)
_TOPIC_SYNONYMS = {
    "indian": frozenset({"india", "indian"}),
    "india": frozenset({"india", "indian"}),
    "worker": frozenset({"worker", "workers", "laborer", "laborers", "labourer", "labourers"}),
    "workers": frozenset({"worker", "workers", "laborer", "laborers", "labourer", "labourers"}),
    "labor": frozenset({"labor", "labour", "laborer", "laborers", "labourer", "labourers"}),
    "labour": frozenset({"labor", "labour", "laborer", "laborers", "labourer", "labourers"}),
    "productivity": frozenset({"productivity", "productive", "output"}),
}


@dataclass(frozen=True)
class GeneralWebDomainCandidate:
    """A bounded organization-verification lead, not a verified organization."""

    domain: str
    title: str
    url: str
    rank: int
    matched_topic_terms: tuple[str, ...]
    relevance_score: int
    status: str
    reason: str


def _discovery_tokens(value: object) -> set[str]:
    if not isinstance(value, str):
        return set()
    normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    tokens: set[str] = set()
    for raw in _TOKEN.findall(normalized.casefold()):
        token = raw.removesuffix("'s")
        if len(token) < 2 or token in _STOPWORDS:
            continue
        if token.endswith("ies") and len(token) > 4:
            token = token[:-3] + "y"
        elif token.endswith("s") and len(token) > 4 and not token.endswith("ss"):
            token = token[:-1]
        tokens.add(token)
    return tokens


def rank_general_web_domain_candidates(
    hits: Iterable[Mapping[str, object]],
    question: str,
    *,
    limit: int = MAX_GENERAL_WEB_DOMAIN_CANDIDATES,
) -> list[GeneralWebDomainCandidate]:
    """Rank distinct, topic-relevant result domains for bounded identity checks.

    Search titles, paths, and snippets are used only to prioritize verification
    leads. They are not accepted as organization identity or research evidence.
    The return value includes excluded candidates and reasons for an auditable
    routing decision. Ranking uses broad query overlap and publication cues,
    rather than requiring one of a short list of words in a title or URL.
    """
    if not 1 <= limit <= MAX_GENERAL_WEB_DOMAIN_CANDIDATES:
        raise ValueError("general web domain candidate cap is outside its configured boundary")
    query_terms = _discovery_tokens(
        compact_bibliographic_query(
            [question], max_terms=MAX_QUERY_TERMS, max_chars=MAX_QUERY_CHARS
        )
    )
    if not query_terms:
        return []

    best_by_domain: dict[str, tuple[int, int, GeneralWebDomainCandidate]] = {}
    for position, hit in enumerate(hits, start=1):
        raw_url = hit.get("url")
        raw_domain = hit.get("domain")
        if not isinstance(raw_url, str) or not isinstance(raw_domain, str):
            continue
        try:
            parsed = urlsplit(raw_url)
            host = (parsed.hostname or "").casefold().rstrip(".").removeprefix("www.")
        except ValueError:
            continue
        domain = raw_domain.casefold().strip().rstrip(".").removeprefix("www.")
        if (
            parsed.scheme.casefold() != "https"
            or parsed.username is not None
            or parsed.password is not None
            or not domain
            or (host != domain and not host.endswith("." + domain))
            or not re.fullmatch(r"[a-z0-9.-]{3,253}", domain)
            or ".." in domain
        ):
            continue
        title = str(hit.get("title") or "")[:1000]
        rank_value = hit.get("rank")
        rank = rank_value if isinstance(rank_value, int) and rank_value > 0 else position
        path = parsed.path.casefold()
        full_text = _discovery_tokens(f"{title} {path}")
        snippet_text = _discovery_tokens(hit.get("snippet"))
        all_text = full_text | snippet_text
        matched: list[str] = []
        title_path_matches = 0
        for term in sorted(query_terms):
            variants = _TOPIC_SYNONYMS.get(term, frozenset({term}))
            if variants & all_text:
                matched.append(term)
            if variants & full_text:
                title_path_matches += 1
        publication_signal = bool(_PUBLICATION_CUES & (full_text | snippet_text))
        official_document_path = any(marker in path for marker in _OFFICIAL_DOCUMENT_PATHS)
        editorial_path = any(marker in path for marker in _EDITORIAL_PATHS)
        dated_editorial_path = bool(_DATED_EDITORIAL_PATH.search(path))
        direct_publication_signal = bool(_DIRECT_PUBLICATION_CUES & full_text)
        dated_news_lead = (
            not official_document_path and dated_editorial_path and not direct_publication_signal
        )
        score = title_path_matches * 3 + max(0, len(matched) - title_path_matches)
        if publication_signal:
            score += 2
        if official_document_path:
            score += 5
        elif dated_news_lead:
            score -= 12
        elif editorial_path:
            score -= 8
        if domain in _NON_ORIGINAL_PUBLICATION_HOSTS or any(
            domain.endswith("." + item) for item in _NON_ORIGINAL_PUBLICATION_HOSTS
        ):
            status = "excluded_aggregator_or_search_host"
            reason = "This host aggregates or routes to third-party publications."
        elif dated_news_lead:
            status = "excluded_editorial_content_lead"
            reason = (
                "The result looks like dated or general editorial coverage, without an official "
                "document path or direct research-publication signal."
            )
        elif len(matched) < 2 or (
            title_path_matches == 0 and not (len(matched) >= 4 and publication_signal)
        ):
            status = "excluded_low_topic_overlap"
            reason = "The lead has insufficient question-term overlap for identity verification."
        else:
            status = "eligible_for_identity_verification"
            reason = (
                "Question-term overlap and publication cues prioritize this lead; "
                "identity, relevance, and quality remain unverified."
            )
        candidate = GeneralWebDomainCandidate(
            domain=domain,
            title=title,
            url=raw_url[:2000],
            rank=rank,
            matched_topic_terms=tuple(matched),
            relevance_score=score,
            status=status,
            reason=reason,
        )
        previous = best_by_domain.get(domain)
        ordering = (score, -rank)
        if previous is None or ordering > previous[:2]:
            best_by_domain[domain] = (score, -rank, candidate)

    ordered = sorted(
        (item[2] for item in best_by_domain.values()),
        key=lambda item: (-item.relevance_score, item.rank, item.domain),
    )
    selected = 0
    result: list[GeneralWebDomainCandidate] = []
    for candidate in ordered:
        if candidate.status == "eligible_for_identity_verification":
            if selected < limit:
                selected += 1
            else:
                candidate = dataclass_replace(
                    candidate,
                    status="excluded_candidate_capacity",
                    reason="The bounded organization-verification candidate limit was reached.",
                )
        result.append(candidate)
    return result


def compact_bibliographic_query(
    fields: Iterable[str | None],
    *,
    max_terms: int = MAX_QUERY_TERMS,
    max_chars: int = MAX_QUERY_CHARS,
) -> str:
    """Return an ordered, deduplicated keyword query without rewriting the question.

    Field order is priority order (the question first, then scope and query lens). Numerical
    case-size/time quantities and generic question grammar are omitted. The full question is
    separately preserved in the plan and subquestions.
    """
    if not 1 <= max_terms <= MAX_QUERY_TERMS:
        raise ValueError("bibliographic query term cap is outside its configured boundary")
    if not 1 <= max_chars <= MAX_QUERY_CHARS:
        raise ValueError("bibliographic query character cap is outside its configured boundary")

    values = list(fields)
    selected: list[str] = []
    seen: set[str] = set()
    for field in values:
        if not isinstance(field, str) or not field.strip():
            continue
        normalized = unicodedata.normalize("NFKD", field).encode("ascii", "ignore").decode()
        for token in _TOKEN.findall(normalized.casefold()):
            is_year = token.isdigit() and len(token) == 4 and "1900" <= token <= "2100"
            if (
                (token.isdigit() and not is_year)
                or len(token) < 2
                or token in _STOPWORDS
                or token in seen
            ):
                continue
            candidate = " ".join((*selected, token))
            if len(selected) >= max_terms or len(candidate) > max_chars:
                return " ".join(selected)
            selected.append(token)
            seen.add(token)
    if selected:
        return " ".join(selected)

    # Preserve a bounded search anchor for unusually short or generic questions.
    fallback = " ".join(" ".join(value for value in values if isinstance(value, str)).split())[
        :max_chars
    ].strip()
    return fallback or "research evidence"


def institutional_catalog_query(
    question: str,
    scope_fields: Iterable[str | None] = (),
) -> str:
    """Build a compact topic anchor for official institution publication catalogs.

    Catalogs commonly rank a short sequence of topic terms better than a long
    decision narrative. The complete question and scope remain in Veda's plan;
    this bounded query is only a discovery input, and its exact value is logged.
    """
    return compact_bibliographic_query(
        [question, *scope_fields],
        max_terms=MAX_INSTITUTIONAL_CATALOG_TERMS,
        max_chars=180,
    )


def build_general_web_discovery_queries(
    question: str,
    *,
    geography: str | None = None,
    max_queries: int = 2,
) -> list[str]:
    """Build a small, name-agnostic web search set for organizations and publications.

    Queries use only question and scope terms; no publisher list is injected. The
    organization/publication query is first because this route's purpose is to expand
    beyond the scholarly indexes. Search results remain discovery leads, not answers.
    """
    if not isinstance(question, str) or not question.strip():
        return []
    if not 1 <= max_queries <= MAX_GENERAL_WEB_DISCOVERY_QUERIES:
        raise ValueError("general web discovery query cap is outside its configured boundary")
    topic = compact_bibliographic_query(
        [question, geography],
        max_terms=12,
        max_chars=200,
    )
    candidates = (
        f"{topic} research institutes publications",
        f"{topic} research report",
        f"{topic} independent study findings",
    )
    queries: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        normalized = " ".join(candidate.split())[:MAX_QUERY_CHARS]
        key = normalized.casefold()
        if key and key not in seen:
            queries.append(normalized)
            seen.add(key)
        if len(queries) >= max_queries:
            break
    return queries


def build_verified_domain_publication_query(domain: str, question: str) -> str:
    """Build one bounded site-restricted search after a domain is independently verified."""
    normalized_domain = domain.strip().casefold().rstrip(".") if isinstance(domain, str) else ""
    if (
        not normalized_domain
        or len(normalized_domain) > 253
        or not re.fullmatch(r"(?=.{1,253}$)[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?", normalized_domain)
        or ".." in normalized_domain
    ):
        raise ValueError("verified publication domain is invalid")
    labels = normalized_domain.split(".")
    if len(labels) < 2 or any(
        not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label) for label in labels
    ):
        raise ValueError("verified publication domain is invalid")
    topic = compact_bibliographic_query([question], max_terms=8, max_chars=140)
    query = f"site:{normalized_domain} {topic} research report publication"
    if len(query) > 512:
        query = query[:512].rstrip()
    return query


def openaire_organization_discovery_query(question: str) -> str:
    """Build a bounded, research-focused OpenAIRE organization query.

    Organization search ranks domain organizations better when the topic is
    combined with the research-intent term. Two topic anchors bound the query and
    avoid both long-question overconstraint and broad OR results dominated by
    commercial entities that merely mention one keyword. The complete question
    remains in the persisted plan; this expression is only a discovery input.
    """
    compact = compact_bibliographic_query([question], max_terms=20, max_chars=MAX_QUERY_CHARS)
    terms = [
        term for term in compact.split() if term.casefold() not in _OPENAIRE_ORGANIZATION_STOPWORDS
    ][:MAX_OPENAIRE_ORGANIZATION_TOPIC_TERMS]
    if not terms:
        fallback_tokens = [
            token.casefold()
            for token in _TOKEN.findall(
                unicodedata.normalize("NFKD", question).encode("ascii", "ignore").decode()
            )
            if len(token) >= 2 and token.casefold() not in _STOPWORDS
        ]
        terms = list(dict.fromkeys(fallback_tokens))[:4]
    if not terms:
        terms = ["research"]
    if "research" not in terms:
        terms.append("research")
    return " AND ".join(f'"{term}"' for term in terms)
