"""Rights-aware retention policy for bibliographic abstract text snapshots."""

UNVERIFIED_ITEM_TEXT_STATUS = "not_retained_item_text_rights_unverified"
NOT_AVAILABLE_STATUS = "not_available"
LEGACY_NOT_RECORDED_STATUS = "legacy_not_recorded"


def snapshot_candidate_abstract(*, abstract_excerpt: str | None) -> tuple[None, str]:
    """Omit abstract text unless a future item/version rights record authorizes it.

    Provider dataset terms do not establish reuse rights for every third-party
    abstract. In particular, OpenAlex identifies abstracts as externally sourced
    text and says it reconstructs them from an inverted index for legal reasons.
    Until an acquisition record ties an explicit text license to this exact
    excerpt and source version, the candidate ledger stores only the omission
    status. Full-text rights remain a separate decision.
    """
    if abstract_excerpt is None or not abstract_excerpt.strip():
        return None, NOT_AVAILABLE_STATUS
    return None, UNVERIFIED_ITEM_TEXT_STATUS


def snapshot_source_abstract(*, abstract_excerpt: str | None) -> tuple[None, str]:
    """Do not turn a provider abstract into durable source evidence by default.

    Discovery can use provider text transiently for query alignment, but a
    selected source requires a separate item/version text-retention decision
    before its abstract can become a persisted passage or claim.
    """
    return snapshot_candidate_abstract(abstract_excerpt=abstract_excerpt)


def normalize_candidate_abstract_snapshot(
    *, abstract_excerpt: str | None, retention_status: str | None
) -> tuple[None, str]:
    """Fail closed for legacy or inconsistent candidate snapshot rows.

    A status string alone is not an auditable item/version rights record, so
    previously stored text is never copied or exposed by this policy.
    """
    if isinstance(abstract_excerpt, str) and abstract_excerpt.strip():
        return None, UNVERIFIED_ITEM_TEXT_STATUS
    if retention_status in {
        UNVERIFIED_ITEM_TEXT_STATUS,
        "not_retained_rights_unclear",
        "retained_openalex_metadata_cc0_v1",
    }:
        return None, UNVERIFIED_ITEM_TEXT_STATUS
    if retention_status in {None, NOT_AVAILABLE_STATUS, "retained_item_license_verified_v1"}:
        return None, NOT_AVAILABLE_STATUS if retention_status else LEGACY_NOT_RECORDED_STATUS
    return None, LEGACY_NOT_RECORDED_STATUS
