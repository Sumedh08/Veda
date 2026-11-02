"""Bounded GOV.UK Content API access to the official publication page body.

This adapter never downloads linked attachments. GOV.UK states that most site
content is published under OGL v3.0 unless otherwise stated; the returned
record is marked restricted/default-based because the Content API does not
expose a per-item licence field.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from urllib.parse import quote

import httpx

CONTENT_API_BASE = "https://www.gov.uk/api/content"
TERMS_URL = "https://www.gov.uk/help/terms-conditions"
REUSE_URL = "https://www.gov.uk/help/reuse-govuk-content"
OGL_URL = "https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/"
MAX_RESPONSE_BYTES = 1_000_000
MAX_BODY_CHARACTERS = 100_000
_PUBLICATION_PATH = re.compile(r"^/government/publications/[A-Za-z0-9][A-Za-z0-9-]{0,180}/?$")
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


class GovUKContentError(Exception):
    """Safe, redacted failure while retrieving a published GOV.UK page body."""

    def __init__(self, code: str, *, request_dispatched: bool = False):
        super().__init__("GOV.UK publication content could not be retrieved.")
        self.code = code
        self.request_dispatched = request_dispatched


@dataclass(frozen=True)
class GovUKPublicationBody:
    title: str
    base_path: str
    body_html: str
    api_url: str
    publication_url: str
    updated_at: str | None
    retrieved_at: datetime
    license_code: str
    license_url: str
    rights_status: str
    rights_limit: str


def _identity_name(value: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", value.casefold()))


class GovUKContentProvider:
    """Fetch one selected policy-paper page body from the fixed GOV.UK API."""

    def __init__(
        self,
        client: httpx.Client | None = None,
        *,
        before_request=None,
    ) -> None:
        self._owns_client = client is None
        self._client = client or httpx.Client(
            timeout=httpx.Timeout(8, connect=3),
            headers={
                "User-Agent": "VedaResearch/0.1 (bounded GOV.UK Content API access)",
                "Accept-Encoding": "identity",
            },
            follow_redirects=False,
        )
        if client is not None:
            self._client.follow_redirects = False
        self._before_request = before_request

    def fetch_publication_body(
        self, record_path: str, *, expected_title: str
    ) -> GovUKPublicationBody:
        if (
            not isinstance(record_path, str)
            or not _PUBLICATION_PATH.fullmatch(record_path)
            or not isinstance(expected_title, str)
            or not expected_title.strip()
            or len(expected_title) > 1000
            or _CONTROL.search(expected_title)
        ):
            raise GovUKContentError("invalid_publication_identity")

        path = record_path.rstrip("/")
        endpoint = f"{CONTENT_API_BASE}{quote(path, safe='/')}"
        if self._before_request is not None:
            try:
                self._before_request("https://www.gov.uk")
            except Exception:
                raise GovUKContentError("request_deferred") from None

        dispatched = False
        try:
            with self._client.stream(
                "GET",
                endpoint,
                follow_redirects=False,
                headers={"Accept": "application/json", "Accept-Encoding": "identity"},
            ) as response:
                dispatched = True
                if 300 <= response.status_code < 400:
                    raise GovUKContentError("redirect_rejected", request_dispatched=True)
                if response.status_code == 429:
                    raise GovUKContentError("rate_limited", request_dispatched=True)
                if response.status_code != 200:
                    raise GovUKContentError("provider_unavailable", request_dispatched=True)
                content_type = (
                    response.headers.get("content-type", "").split(";", 1)[0].strip().casefold()
                )
                if content_type != "application/json":
                    raise GovUKContentError("unexpected_content_type", request_dispatched=True)
                if response.headers.get("content-encoding", "identity").casefold() not in {
                    "",
                    "identity",
                }:
                    raise GovUKContentError("unsupported_content_encoding", request_dispatched=True)
                declared_size = response.headers.get("content-length")
                if declared_size:
                    try:
                        if not 0 <= int(declared_size) <= MAX_RESPONSE_BYTES:
                            raise ValueError
                    except ValueError:
                        raise GovUKContentError(
                            "response_too_large", request_dispatched=True
                        ) from None
                body = bytearray()
                for chunk in response.iter_bytes():
                    body.extend(chunk)
                    if len(body) > MAX_RESPONSE_BYTES:
                        raise GovUKContentError("response_too_large", request_dispatched=True)
        except GovUKContentError:
            raise
        except httpx.TimeoutException:
            raise GovUKContentError("timeout", request_dispatched=dispatched) from None
        except httpx.HTTPError:
            raise GovUKContentError("request_failed", request_dispatched=dispatched) from None

        try:
            payload = json.loads(bytes(body))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise GovUKContentError("invalid_response", request_dispatched=True) from None
        if not isinstance(payload, dict):
            raise GovUKContentError("invalid_response", request_dispatched=True)

        canonical_path = payload.get("base_path")
        title = payload.get("title")
        document_type = payload.get("document_type")
        schema_name = payload.get("schema_name")
        details = payload.get("details")
        body_html = details.get("body") if isinstance(details, dict) else None
        if (
            canonical_path != path
            or document_type != "policy_paper"
            or schema_name != "publication"
            or not isinstance(title, str)
            or _identity_name(title) != _identity_name(expected_title)
            or not isinstance(body_html, str)
            or not body_html.strip()
            or len(body_html) > MAX_BODY_CHARACTERS
            or _CONTROL.search(body_html)
        ):
            raise GovUKContentError(
                "publication_identity_or_body_mismatch", request_dispatched=True
            )

        # The public Content API exposes no item-level license field. Preserve
        # GOV.UK's default OGL basis and its exception caveat instead of calling
        # this a page-specific license verification.
        updated_at = payload.get("public_updated_at")
        if not isinstance(updated_at, str) or len(updated_at) > 80:
            updated_at = None
        return GovUKPublicationBody(
            title=" ".join(title.split()),
            base_path=path,
            body_html=body_html,
            api_url=endpoint,
            publication_url=f"https://www.gov.uk{path}",
            updated_at=updated_at,
            retrieved_at=datetime.now(UTC),
            license_code="ogl-3.0-default",
            license_url=OGL_URL,
            rights_status="PERMITTED_WITH_RESTRICTIONS",
            rights_limit=(
                "GOV.UK states most content is under OGL v3.0 except where otherwise stated; "
                "the Content API has no per-item licence field. Only the publication page body "
                "was retrieved; linked attachments and third-party material were not fetched."
            ),
        )

    def close(self) -> None:
        if self._owns_client:
            self._client.close()
