"""Bounded, global employment observations from the ILOSTAT SDMX service.

This adapter intentionally requests one documented dataflow and one complete
series key. It is a descriptive-statistics source, never a study or causal
estimate. The API response is subject to a strict byte and row cap.
"""

import csv
import io
import re
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any
from urllib.parse import urlencode

import httpx

from app.providers.scholarly import ScholarlyWork

API_ROOT = "https://sdmx.ilo.org/rest"
DATAFLOW_ID = "DF_EMP_TEMP_SEX_AGE_NB"
INDICATOR_ID = "EMP_TEMP_SEX_AGE_NB"
# Dimension order and codes follow the ILOSTAT SDMX guide's employment/sex/age
# flow. X01 is ILOSTAT's World area. All dimensions are pinned to one series.
SERIES_KEY = "X01.A.EMP_TEMP_NB.SEX_T.AGE_5YRBANDS_TOTAL"
DATA_URL = f"{API_ROOT}/data/ILO,{DATAFLOW_ID}/{SERIES_KEY}"
DATASET_URL = "https://ilostat.ilo.org/data/"
DATASET_TERMS_URL = "https://www.ilo.org/rights-and-permissions"
LICENSE_URL = "https://creativecommons.org/licenses/by/4.0/"
MAX_RESPONSE_BYTES = 512_000
MAX_CSV_ROWS = 10
MAX_TEXT = 1_000
EMPLOYMENT_TERMS = {
    "employment",
    "employed",
    "workforce",
    "labour force",
    "labor force",
    "employment rate",
    "employment level",
    "employment levels",
    "job creation",
    "jobs",
}
WORLD_SCOPE_TERMS = {"global", "world", "worldwide", "international", "all countries"}
NUMERIC = re.compile(r"^-?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?$")


class ILOSTATError(Exception):
    """Sanitized service, payload, or bounded-response failure."""


def supports_query(query: str) -> bool:
    """Run this single series only for questions explicitly about employment."""
    normalized = " ".join(query.casefold().split())
    return any(
        re.search(rf"(?<![a-z]){re.escape(term)}(?![a-z])", normalized) for term in EMPLOYMENT_TERMS
    )


def supports_geography(geography: str | None) -> bool:
    """This initial adapter supports an explicitly requested world aggregate only."""
    normalized = " ".join((geography or "").casefold().split())
    return normalized in WORLD_SCOPE_TERMS


def _short(value: Any, limit: int = MAX_TEXT) -> str | None:
    return " ".join(value.split())[:limit] if isinstance(value, str) and value.strip() else None


def _numeric_string(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text or len(text) > 64 or not NUMERIC.fullmatch(text):
        return None
    try:
        return text if Decimal(text).is_finite() else None
    except InvalidOperation:
        return None


def parse_observations(body: bytes) -> list[dict[str, Any]]:
    """Validate the SDMX CSV contract and accept one exact latest observation."""
    if not body or len(body) > MAX_RESPONSE_BYTES:
        raise ILOSTATError("ILOSTAT returned an empty or oversized response")
    try:
        text = body.decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(text, newline=""))
        headers = set(reader.fieldnames or [])
        required = {
            "REF_AREA",
            "FREQ",
            "MEASURE",
            "CLASSIF_SEX",
            "CLASSIF_AGE",
            "TIME_PERIOD",
            "OBS_VALUE",
        }
        if not required.issubset(headers):
            raise ILOSTATError("ILOSTAT CSV omitted required series dimensions")
        rows: list[dict[str, str | None]] = []
        for row in reader:
            if len(rows) == MAX_CSV_ROWS:
                raise ILOSTATError("ILOSTAT returned more rows than the series bound")
            rows.append(row)
    except (UnicodeDecodeError, csv.Error) as exc:
        raise ILOSTATError("ILOSTAT returned malformed CSV") from exc

    accepted: list[dict[str, Any]] = []
    for row in rows:
        if (
            row.get("REF_AREA") != "X01"
            or row.get("FREQ") != "A"
            or row.get("MEASURE") != "EMP_TEMP_NB"
            or row.get("CLASSIF_SEX") != "SEX_T"
            or row.get("CLASSIF_AGE") != "AGE_5YRBANDS_TOTAL"
        ):
            continue
        value = _numeric_string(row.get("OBS_VALUE"))
        period = _short(row.get("TIME_PERIOD"), 32)
        if value is None or not period:
            continue
        try:
            unit_multiplier = int(row["UNIT_MULT"]) if row.get("UNIT_MULT") else None
        except (TypeError, ValueError):
            unit_multiplier = None
        source_name = _short(row.get("SOURCE"), 200)
        source_note = _short(row.get("SOURCE_NOTE"), 500)
        accepted.append(
            {
                "value": value,
                "period": period,
                "geography_code": "X01",
                "geography_name": "World",
                "unit_measure": _short(row.get("UNIT_MEASURE"), 100),
                "unit_type": _short(row.get("UNIT_TYPE"), 100),
                "unit_multiplier": unit_multiplier,
                "observation_status": _short(row.get("OBS_STATUS"), 40),
                "source_name": source_name,
                "source_note": source_note,
                "indicator_note": _short(row.get("INDICATOR_NOTE"), 700),
                "classification_note": _short(row.get("CLASSIFICATION_NOTE"), 500),
            }
        )
    # The adapter pins all series dimensions and asks for one observation. If
    # the service returns multiple matching records, do not silently select one.
    if len(accepted) > 1:
        raise ILOSTATError("ILOSTAT returned an ambiguous exact-series response")
    return accepted


class ILOSTATProvider:
    """Fetch one latest world employment-total observation from ILOSTAT."""

    provider_name = "ILOSTAT"

    def __init__(self, client: httpx.Client | None = None) -> None:
        self._owns_client = client is None
        self.client = client or httpx.Client(
            timeout=httpx.Timeout(5, connect=2),
            headers={
                "User-Agent": "VedaResearch/0.1 (bounded official statistics client)",
                "Accept": "application/vnd.sdmx.data+csv;version=1.0.0",
                "Range": "values=1-10",
            },
            follow_redirects=False,
        )
        if client is not None:
            self.client.headers.update(
                {
                    "User-Agent": "VedaResearch/0.1 (bounded official statistics client)",
                    "Accept": "application/vnd.sdmx.data+csv;version=1.0.0",
                    "Range": "values=1-10",
                }
            )

    def close(self) -> None:
        if self._owns_client:
            self.client.close()

    def _csv(self) -> bytes:
        try:
            with self.client.stream(
                "GET",
                DATA_URL,
                params={
                    "lastNObservations": "1",
                    "detail": "full",
                    "format": "csv",
                },
            ) as response:
                response.raise_for_status()
                content_type = response.headers.get("content-type", "").casefold()
                if "csv" not in content_type and "text/plain" not in content_type:
                    raise ILOSTATError("ILOSTAT returned an unexpected media type")
                body = bytearray()
                for chunk in response.iter_bytes():
                    body.extend(chunk)
                    if len(body) > MAX_RESPONSE_BYTES:
                        raise ILOSTATError("ILOSTAT response exceeded the 512 KB limit")
            return bytes(body)
        except ILOSTATError:
            raise
        except httpx.HTTPError as exc:
            # Keep upstream response bodies, query strings and error details out
            # of user-visible events and durable research records.
            raise ILOSTATError("ILOSTAT request failed; scholarly discovery can continue") from exc

    def search(
        self,
        query: str,
        *,
        limit: int = 1,
        geography: str | None = None,
    ) -> list[ScholarlyWork]:
        if not supports_query(query) or not supports_geography(geography) or limit < 1:
            return []
        observations = parse_observations(self._csv())
        if not observations:
            return []
        observation = observations[0]
        source_name = observation.pop("source_name")
        source_note = observation.pop("source_note")
        indicator_note = observation.pop("indicator_note")
        classification_note = observation.pop("classification_note")
        retrieved_at = datetime.now(UTC).isoformat()
        statistics: dict[str, Any] = {
            "indicator_id": INDICATOR_ID,
            "indicator_name": "Employment by sex and age (total employment, number)",
            "database_id": "ILOSTAT",
            "dataset_name": "ILOSTAT labour statistics database",
            "dataset_url": DATASET_URL,
            "dataset_terms_url": DATASET_TERMS_URL,
            "license": (
                "CC BY 4.0 under the ILO Open Access policy for datasets published or made "
                "available from 2023-05-03; third-party exceptions apply"
            ),
            "license_url": LICENSE_URL,
            "attribution": (
                "International Labour Organization (ILO), ILOSTAT, Employment by sex and age; "
                "source note as returned by ILOSTAT."
            ),
            "definition": indicator_note,
            "statistical_concept": classification_note,
            "methodology": source_note,
            "limitations": (
                "This is one descriptive world aggregate, not a causal estimate. ILO's policy "
                "covers ILO datasets published or made available on or after 2023-05-03; it "
                "does not cover third-party materials or restricted constituent microdata. "
                "Review the ILOSTAT source note and rights policy before reuse."
            ),
            "periodicity": "Annual",
            "source_update_date": None,
            "measurement_unit": observation.get("unit_measure"),
            "retrieved_at": retrieved_at,
            "data_sources": (
                [
                    {
                        "name": source_name,
                        "organization": "As reported in ILOSTAT",
                        "publisher": "International Labour Organization",
                        "url": None,
                    }
                ]
                if source_name
                else []
            ),
            "observations": [{key: value for key, value in observation.items()}],
        }
        url_params = urlencode({"lastNObservations": "1", "detail": "full", "format": "csv"})
        url = f"{DATA_URL}?{url_params}"
        return [
            ScholarlyWork(
                external_id=f"ilostat:{DATAFLOW_ID}:X01:{observation['period']}",
                title=f"{statistics['indicator_name']} — ILOSTAT (World)",
                doi=None,
                url=url,
                authors=[],
                published_year=None,
                publisher="International Labour Organization",
                abstract_excerpt=None,
                query=" ".join(query.split())[:300],
                provider=self.provider_name,
                provider_metadata={"statistics": statistics},
                source_type="official_statistics",
            )
        ]
