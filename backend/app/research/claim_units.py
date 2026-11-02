"""Conservative, exact-span atomization for retrieved source sentences."""

import re
from dataclasses import dataclass

CLAIM_ATOMIZATION_VERSION = 1


@dataclass(frozen=True)
class ClaimUnitSpan:
    text: str
    start: int
    end: int
    status: str


# Only clear clause boundaries are candidates. Conjunctions such as "and" are
# not split automatically because they often join a single subject or outcome.
_CLAUSE_BOUNDARY = re.compile(r";|,\s+(?:but|while|whereas)\s+|\s+(?:while|whereas)\s+", re.I)
_PREDICATE = re.compile(
    r"\b(?:"
    r"is|are|was|were|be|been|being|has|have|had|do|does|did|"
    r"increase[sd]?|decrease[sd]?|rise[sd]?|rose|fall[sd]?|fell|"
    r"grow[ns]?|grew|expand(?:ed|s)?|decline[sd]?|improve[sd]?|worsen(?:ed|s)?|"
    r"reduce[sd]?|raise[sd]?|lower[sd]?|remain(?:ed|s)?|"
    r"report(?:ed|s)?|find|found|show(?:ed|s|n)?|indicat(?:e|ed|es)|"
    r"associate[sd]?|correlat(?:e|ed|es)|link(?:ed|s)?|"
    r"lead|led|result(?:ed|s)?|cause[sd]?|affect(?:ed|s)?|"
    r"influence[sd]?|experience[sd]?|demonstrat(?:e|ed|es)|"
    r"produce[sd]?|adopt(?:ed|s)?|invest(?:ed|s)?|"
    r"increase|decrease|improve|reduce|"
    r"predict(?:ed|s)?|estimate[sd]?|"
    r"may|might|can|could|would|should"
    r")\b",
    re.I,
)
_WORD = re.compile(r"[\w%]+", re.UNICODE)


def _clause_is_explicit(text: str) -> bool:
    # A leading attribution phrase does not supply the grammatical subject of
    # the empirical proposition that follows it.
    proposition = re.sub(r"^\s*according\s+to\b[^,]+,\s*", "", text, flags=re.I)
    words = _WORD.findall(proposition)
    if len(words) < 2:
        return False
    predicate = _PREDICATE.search(proposition)
    if predicate is None:
        return False
    # A candidate predicate at the very beginning has no explicit subject in
    # this clause. We prefer an unatomized source sentence to filling it in.
    return bool(_WORD.findall(proposition[: predicate.start()]))


def _trimmed_span(text: str, start: int, end: int) -> tuple[int, int]:
    while start < end and text[start].isspace():
        start += 1
    while end > start and text[end - 1].isspace():
        end -= 1
    return start, end


def atomize_source_sentence(sentence: str) -> tuple[ClaimUnitSpan, ...]:
    """Split only explicit, self-contained clauses while preserving exact spans.

    Semicolons and contrast/temporal clause boundaries are candidates, not proof
    of independent propositions. Every resulting clause must contain an
    explicit subject token before a conservative finite-predicate vocabulary.
    Any uncertain or overlapping case remains one whole-sentence claim and is
    marked `compound_unatomized` when a compound boundary was detected.
    Offsets count Unicode code points and use an exclusive end index.
    """
    matches = list(_CLAUSE_BOUNDARY.finditer(sentence))
    if 0 < len(matches) <= 3:
        segments: list[tuple[int, int]] = []
        cursor = 0
        for match in matches:
            segments.append(_trimmed_span(sentence, cursor, match.start()))
            cursor = match.end()
        segments.append(_trimmed_span(sentence, cursor, len(sentence)))
        texts = [sentence[start:end] for start, end in segments]
        if (
            len(texts) <= 4
            and all(_clause_is_explicit(text) for text in texts)
            and all(start < end for start, end in segments)
            and all(
                segments[index][1] <= segments[index + 1][0] for index in range(len(segments) - 1)
            )
        ):
            return tuple(
                ClaimUnitSpan(text, start, end, "atomized_exact_span")
                for text, (start, end) in zip(texts, segments, strict=True)
            )

    compound_hint = bool(matches) or (
        re.search(r"\band\b", sentence, re.I) is not None and len(_PREDICATE.findall(sentence)) >= 2
    )
    status = "compound_unatomized" if compound_hint else "whole_sentence"
    return (ClaimUnitSpan(sentence, 0, len(sentence), status),)
