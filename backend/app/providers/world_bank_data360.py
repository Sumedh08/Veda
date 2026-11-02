"""Bounded metadata-first access to licensed World Bank Data360 observations."""

import json
import re
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any
from urllib.parse import urlencode, urlsplit

import httpx

from app.providers.scholarly import ScholarlyWork

API_ROOT = "https://data360api.worldbank.org"
WORLD_BANK_COUNTRIES_URL = "https://api.worldbank.org/v2/country"
SEARCH_URL = f"{API_ROOT}/data360/searchv2"
METADATA_URL = f"{API_ROOT}/data360/metadata"
DATA_URL = f"{API_ROOT}/data360/data"
DATASET_URL = (
    "https://datacatalog.worldbank.org/search/dataset/0037712/world-development-indicators"
)
DATASET_TERMS_URL = "https://www.worldbank.org/en/about/legal/terms-of-use-for-datasets"
LICENSE_URL = "https://creativecommons.org/licenses/by/4.0/"
MAX_RESPONSE_BYTES = 512_000
MAX_SEARCH_RESULTS = 1
MAX_STORED_OBSERVATIONS = 4
MAX_TEXT = 1_000
INDICATOR_ID = re.compile(r"^WB_WDI_[A-Z0-9_]{1,120}$")
WORLD_SCOPE_TERMS = {"global", "world", "worldwide", "international", "all countries"}
COUNTRY_CODE = re.compile(r"^[A-Z0-9]{3}$")
STATISTICS_TERMS = {
    "birth rate",
    "carbon emissions",
    "co2 emissions",
    "consumer price",
    "employment",
    "exports",
    "fertility",
    "gdp",
    "gross domestic product",
    "imports",
    "inflation",
    "internet users",
    "labor force",
    "labour force",
    "life expectancy",
    "literacy",
    "mortality",
    "population",
    "poverty",
    "renewable energy",
    "school enrollment",
    "school enrolment",
    "statistics",
    "trade",
    "unemployment",
}


class WorldBankData360Error(Exception):
    """Sanitized Data360 failure; response bodies and URLs are never persisted."""


def supports_geography(geography: str | None) -> bool:
    """Whether a user-supplied scope can be resolved to one geography.

    Exact country resolution is performed against the World Bank country API in
    ``search``; an arbitrary geography string is never treated as a valid code.
    An empty scope is not silently broadened to the world aggregate.
    """
    raw_geography = geography or ""
    if any(char in raw_geography for char in ";\n\r"):
        return False
    normalized = " ".join(raw_geography.casefold().split())
    return bool(normalized) and (
        normalized in WORLD_SCOPE_TERMS
        or (len(normalized) <= 100 and not any(char in normalized for char in ";\n\r"))
    )


def supports_query(query: str) -> bool:
    """Route only questions that explicitly ask about a WDI statistics topic."""
    normalized = " ".join(query.casefold().split())
    return any(
        re.search(rf"(?<![a-z]){re.escape(term)}(?![a-z])", normalized) for term in STATISTICS_TERMS
    )


def _country_catalog(payload: Any) -> dict[str, str]:
    """Read World Bank country/economy rows while excluding aggregate entries."""
    if not isinstance(payload, list) or len(payload) != 2 or not isinstance(payload[1], list):
        raise WorldBankData360Error("World Bank country API returned an invalid response")
    header, rows = payload
    if not isinstance(header, dict) or str(header.get("pages")) != "1":
        raise WorldBankData360Error("World Bank country API returned an incomplete catalog")
    try:
        total_rows = int(header.get("total"))
    except (TypeError, ValueError) as exc:
        raise WorldBankData360Error(
            "World Bank country API returned an invalid catalog size"
        ) from exc
    if len(rows) > 400 or total_rows != len(rows):
        raise WorldBankData360Error("World Bank country API exceeded the catalog limit")
    catalog: dict[str, str] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        code = row.get("id")
        name = _short(row.get("name"), 160)
        region = row.get("region")
        # The API includes aggregate entries; region.id == NA identifies them.
        if (
            isinstance(code, str)
            and COUNTRY_CODE.fullmatch(code.upper())
            and name
            and isinstance(region, dict)
            and region.get("id") not in {None, "", "NA"}
        ):
            normalized_code = code.upper()
            prior_name = catalog.get(normalized_code)
            if prior_name is not None and prior_name != name:
                raise WorldBankData360Error(
                    "World Bank country API returned conflicting country codes"
                )
            catalog[normalized_code] = name
    return catalog


def _resolve_country(geography: str, catalog: dict[str, str]) -> tuple[str, str] | None:
    """Resolve an exact country/economy code or name; ambiguous names fail closed."""
    query = " ".join(geography.split())
    by_name: dict[str, list[str]] = {}
    for code, name in catalog.items():
        by_name.setdefault(name.casefold(), []).append(code)
    matches = [query.upper()] if query.upper() in catalog else by_name.get(query.casefold(), [])
    if len(matches) != 1:
        return None
    code = matches[0]
    return code, catalog[code]


def _short(value: Any, limit: int = MAX_TEXT) -> str | None:
    return " ".join(value.split())[:limit] if isinstance(value, str) and value.strip() else None


def _safe_source_url(value: Any) -> str | None:
    text = _short(value, 500)
    if not text:
        return None
    try:
        parsed = urlsplit(text)
        _ = parsed.port
    except ValueError:
        return None
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        return None
    return text


def _allowed_license(series: dict[str, Any]) -> tuple[str, str] | None:
    licenses = series.get("license")
    if not isinstance(licenses, list):
        return None
    for item in licenses[:8]:
        if not isinstance(item, dict):
            continue
        name = _short(item.get("name"), 100)
        uri = _short(item.get("uri"), 300)
        normalized = (name or "").casefold().replace(" ", "").replace("_", "-")
        if normalized in {"ccby-4.0", "ccby4.0", "creativecommonsby4.0"} and uri == LICENSE_URL:
            return name or "CC BY 4.0", uri
    return None


def _numeric_string(value: Any) -> str | None:
    if not isinstance(value, (str, int)) or isinstance(value, bool):
        return None
    text = str(value).strip()
    if not text or len(text) > 64:
        return None
    try:
        number = Decimal(text)
    except InvalidOperation:
        return None
    return text if number.is_finite() else None


def _observation(
    row: Any, *, indicator_id: str, area: str, area_name: str
) -> dict[str, Any] | None:
    if not isinstance(row, dict) or row.get("INDICATOR") != indicator_id:
        return None
    if row.get("REF_AREA") != area:
        return None
    # This release will not silently mix unlabelled sex, age or other disaggregations.
    totals = {None, "", "_T"}
    if any(row.get(field) not in totals for field in ("SEX", "AGE", "URBANISATION")):
        return None
    if any(
        row.get(field) not in {None, "", "_Z"}
        for field in (
            "COMP_BREAKDOWN_1",
            "COMP_BREAKDOWN_2",
            "COMP_BREAKDOWN_3",
        )
    ):
        return None
    value = _numeric_string(row.get("OBS_VALUE"))
    period = _short(row.get("TIME_PERIOD"), 32)
    if value is None or period is None:
        return None
    multiplier = row.get("UNIT_MULT")
    if not isinstance(multiplier, int) or isinstance(multiplier, bool):
        multiplier = None
    return {
        "value": value,
        "period": period,
        "geography_code": area,
        "geography_name": area_name,
        "unit_measure": _short(row.get("UNIT_MEASURE"), 100),
        "unit_type": _short(row.get("UNIT_TYPE"), 100),
        "unit_multiplier": multiplier,
        "observation_status": _short(row.get("OBS_STATUS"), 40),
    }


class WorldBankData360Provider:
    """One bounded WDI indicator search with exact scope and license validation."""

    provider_name = "World Bank Data360"

    def __init__(self, client: httpx.Client | None = None) -> None:
        self._owns_client = client is None
        self.client = client or httpx.Client(
            timeout=httpx.Timeout(4, connect=2),
            headers={"User-Agent": "VedaResearch/0.1 (bounded official statistics client)"},
            follow_redirects=False,
        )
        if client is not None:
            self.client.headers.update(
                {"User-Agent": "VedaResearch/0.1 (bounded official statistics client)"}
            )

    def close(self) -> None:
        if self._owns_client:
            self.client.close()

    def _json(self, method: str, url: str, *, params=None, json_body=None) -> Any:
        try:
            with self.client.stream(method, url, params=params, json=json_body) as response:
                response.raise_for_status()
                body = bytearray()
                for chunk in response.iter_bytes():
                    body.extend(chunk)
                    if len(body) > MAX_RESPONSE_BYTES:
                        raise WorldBankData360Error("Data360 response exceeded the 512 KB limit")
            return json.loads(body)
        except WorldBankData360Error:
            raise
        except (httpx.HTTPError, ValueError) as exc:
            raise WorldBankData360Error(
                "World Bank Data360 request failed; scholarly discovery can continue"
            ) from exc

    def search(
        self, query: str, *, limit: int = MAX_SEARCH_RESULTS, geography: str | None = None
    ) -> list[ScholarlyWork]:
        bounded_query = " ".join(query.split())[:300]
        if (
            not bounded_query
            or not supports_query(bounded_query)
            or not supports_geography(geography)
        ):
            return []
        area_code = "WLD"
        area_name = "World"
        normalized_geography = " ".join((geography or "").casefold().split())
        if geography and normalized_geography not in WORLD_SCOPE_TERMS:
            country_response = self._json(
                "GET",
                WORLD_BANK_COUNTRIES_URL,
                params={"format": "json", "per_page": 400},
            )
            resolved = _resolve_country(geography, _country_catalog(country_response))
            if resolved is None:
                return []
            area_code, area_name = resolved
        search_payload = self._json(
            "POST",
            SEARCH_URL,
            json_body={
                "count": False,
                "search": bounded_query,
                "searchFields": "series_description/name",
                "select": "series_description/idno, series_description/name, series_description/database_id",
                "top": min(max(limit, 1), MAX_SEARCH_RESULTS),
                "skip": 0,
                "filter": "type eq 'indicator'",
            },
        )
        rows = search_payload.get("value", []) if isinstance(search_payload, dict) else []
        if not isinstance(rows, list):
            raise WorldBankData360Error("World Bank Data360 returned an invalid search response")
        works: list[ScholarlyWork] = []
        for result in rows[:MAX_SEARCH_RESULTS]:
            series_stub = result.get("series_description") if isinstance(result, dict) else None
            if not isinstance(series_stub, dict):
                continue
            indicator_id = series_stub.get("idno")
            title = _short(series_stub.get("name"), 500)
            if (
                not isinstance(indicator_id, str)
                or not INDICATOR_ID.fullmatch(indicator_id)
                or series_stub.get("database_id") != "WB_WDI"
                or not title
            ):
                continue
            works.append(
                self._load_indicator(
                    indicator_id,
                    title,
                    bounded_query,
                    area_code=area_code,
                    area_name=area_name,
                )
            )
        return works

    def _load_indicator(
        self,
        indicator_id: str,
        title: str,
        query: str,
        *,
        area_code: str,
        area_name: str,
    ) -> ScholarlyWork:
        # Indicator IDs are regex constrained before they are interpolated into the API query.
        metadata = self._json(
            "POST",
            METADATA_URL,
            json_body={"query": f"&$filter=series_description/idno eq '{indicator_id}'"},
        )
        values = metadata.get("value", []) if isinstance(metadata, dict) else []
        metadata_row = (
            next(
                (
                    row
                    for row in values[:4]
                    if isinstance(row, dict)
                    and isinstance(row.get("series_description"), dict)
                    and row["series_description"].get("idno") == indicator_id
                ),
                None,
            )
            if isinstance(values, list)
            else None
        )
        series = metadata_row.get("series_description", {}) if metadata_row else {}
        metadata_license = _allowed_license(series)
        reason: str | None = None
        observations: list[dict[str, Any]] = []
        api_url = f"{DATA_URL}?{urlencode({'DATABASE_ID': 'WB_WDI', 'INDICATOR': indicator_id, 'REF_AREA': area_code, 'isLatestData': 'true', 'format': 'json'})}"
        if metadata_license is None:
            reason = "license_not_verified"
        else:
            data = self._json(
                "GET",
                DATA_URL,
                params={
                    "DATABASE_ID": "WB_WDI",
                    "INDICATOR": indicator_id,
                    "REF_AREA": area_code,
                    "isLatestData": "true",
                    "format": "json",
                },
            )
            rows = data.get("value", []) if isinstance(data, dict) else []
            if isinstance(rows, list):
                for row in rows:
                    parsed = _observation(
                        row,
                        indicator_id=indicator_id,
                        area=area_code,
                        area_name=area_name,
                    )
                    if parsed is not None:
                        observations.append(parsed)
                    if len(observations) >= MAX_STORED_OBSERVATIONS:
                        break
            if not observations:
                reason = "no_requested_geography_observation"

        retrieved_at = datetime.now(UTC).isoformat()
        lic_name, lic_uri = metadata_license or (None, None)
        selected_metadata: dict[str, Any] = {
            "indicator_id": indicator_id,
            "indicator_name": _short(series.get("name"), 180) or title,
            "database_id": "WB_WDI",
            "dataset_name": "World Development Indicators",
            "dataset_url": DATASET_URL,
            "dataset_terms_url": DATASET_TERMS_URL,
            "license": lic_name,
            "license_url": lic_uri,
            "attribution": "World Bank: World Development Indicators (WDI): Data source as listed in the indicator metadata.",
            "definition": _short(series.get("definition_long")),
            "statistical_concept": _short(series.get("statistical_concept")),
            "methodology": _short(series.get("methodology")),
            "limitations": _short(series.get("limitation")),
            "periodicity": _short(series.get("periodicity"), 80),
            "source_update_date": _short(series.get("date_last_update"), 32),
            "measurement_unit": _short(series.get("measurement_unit"), 100),
            "data_sources": [
                {
                    "name": _short(source.get("name"), 200),
                    "organization": _short(source.get("organization"), 200),
                    "publisher": _short(source.get("publisher"), 200),
                    "url": _safe_source_url(source.get("uri")),
                }
                for source in (
                    series.get("sources", []) if isinstance(series.get("sources"), list) else []
                )[:6]
                if isinstance(source, dict) and _short(source.get("name"), 200)
            ],
            "retrieved_at": retrieved_at,
            "observations": observations,
            "source_type": "official_statistics",
        }
        return ScholarlyWork(
            external_id=f"data360:WB_WDI:{indicator_id}:{area_code}",
            title=f"{title} — World Development Indicators (World Bank; {area_name})",
            doi=None,
            url=api_url,
            authors=[],
            published_year=None,
            publisher="World Bank",
            abstract_excerpt=None,
            query=query,
            provider=self.provider_name,
            provider_metadata={
                "statistics": selected_metadata,
                **({"selection_block_reason": reason} if reason else {}),
            },
            source_type="official_statistics",
        )
