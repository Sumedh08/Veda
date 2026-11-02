import httpx
import pytest

from app.providers.world_bank_data360 import (
    METADATA_URL,
    SEARCH_URL,
    WORLD_BANK_COUNTRIES_URL,
    WorldBankData360Error,
    WorldBankData360Provider,
    _country_catalog,
    _resolve_country,
    supports_geography,
    supports_query,
)

INDICATOR = "WB_WDI_SP_POP_TOTL"


def _metadata(license_name="CC BY-4.0"):
    return {
        "value": [
            {
                "series_description": {
                    "idno": INDICATOR,
                    "name": "Population, total",
                    "database_id": "WB_WDI",
                    "license": [
                        {
                            "name": license_name,
                            "uri": "https://creativecommons.org/licenses/by/4.0/",
                        }
                    ],
                    "definition_long": "Total population counts all residents.",
                    "methodology": "Population estimates use census and demographic components.",
                    "limitation": "Some population values are modeled estimates.",
                    "periodicity": "Annual",
                    "sources": [
                        {
                            "name": "World Population Prospects",
                            "organization": "United Nations",
                            "uri": "https://population.un.org/wpp/",
                        }
                    ],
                }
            }
        ]
    }


def _observation(**overrides):
    return {
        "OBS_VALUE": "8215424893",
        "TIME_FORMAT": "P1Y",
        "UNIT_MULT": 0,
        "OBS_STATUS": "A",
        "COMMENT_TS": None,
        "DATABASE_ID": "WB_WDI",
        "INDICATOR": INDICATOR,
        "REF_AREA": "WLD",
        "SEX": "_T",
        "AGE": "_T",
        "URBANISATION": "_T",
        "COMP_BREAKDOWN_1": "_Z",
        "COMP_BREAKDOWN_2": "_Z",
        "COMP_BREAKDOWN_3": "_Z",
        "TIME_PERIOD": "2025",
        "FREQ": "A",
        "UNIT_MEASURE": "PS",
        "UNIT_TYPE": None,
        **overrides,
    }


def _client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_data360_search_validates_indicator_license_before_loading_latest_data():
    seen = []

    def handler(request):
        seen.append(request)
        if request.url == httpx.URL(SEARCH_URL):
            body = request.read()
            assert b'"top":1' in body
            assert b'"search":"world population"' in body
            assert b'"filter":"type eq \'indicator\'"' in body
            return httpx.Response(
                200,
                json={
                    "value": [
                        {
                            "series_description": {
                                "idno": INDICATOR,
                                "name": "Population, total",
                                "database_id": "WB_WDI",
                            }
                        }
                    ]
                },
            )
        if request.url == httpx.URL(METADATA_URL):
            assert b"series_description/idno eq 'WB_WDI_SP_POP_TOTL'" in request.read()
            return httpx.Response(200, json=_metadata())
        if request.url.host == "data360api.worldbank.org" and request.url.path == "/data360/data":
            assert request.url.params["REF_AREA"] == "WLD"
            assert request.url.params["isLatestData"] == "true"
            assert request.url.params["INDICATOR"] == INDICATOR
            return httpx.Response(200, json={"count": 1, "value": [_observation()]})
        raise AssertionError(f"Unexpected request: {request.method} {request.url.path}")

    provider = WorldBankData360Provider(_client(handler))
    works = provider.search("world population", geography="World")
    provider.close()

    assert len(works) == 1
    work = works[0]
    assert work.source_type == "official_statistics"
    assert work.provider == "World Bank Data360"
    assert work.doi is None
    assert work.abstract_excerpt is None
    assert work.publisher == "World Bank"
    assert work.published_year is None
    assert work.provider_metadata["statistics"]["license"] == "CC BY-4.0"
    assert (
        work.provider_metadata["statistics"]["data_sources"][0]["organization"] == "United Nations"
    )
    assert work.provider_metadata["statistics"]["observations"] == [
        {
            "value": "8215424893",
            "period": "2025",
            "geography_code": "WLD",
            "geography_name": "World",
            "unit_measure": "PS",
            "unit_type": None,
            "unit_multiplier": 0,
            "observation_status": "A",
        }
    ]
    assert len(seen) == 3


def test_data360_does_not_fetch_observations_without_exact_cc_by_license():
    calls = []

    def handler(request):
        calls.append(request.url.path)
        if request.url.path.endswith("searchv2"):
            return httpx.Response(
                200,
                json={
                    "value": [
                        {
                            "series_description": {
                                "idno": INDICATOR,
                                "name": "Population, total",
                                "database_id": "WB_WDI",
                            }
                        }
                    ]
                },
            )
        if request.url.path.endswith("metadata"):
            return httpx.Response(200, json=_metadata("CC BY-NC 4.0"))
        raise AssertionError("Unlicensed statistics must not be fetched")

    provider = WorldBankData360Provider(_client(handler))
    work = provider.search("world population", geography="World")[0]
    provider.close()

    assert calls == ["/data360/searchv2", "/data360/metadata"]
    assert work.provider_metadata["selection_block_reason"] == "license_not_verified"
    assert work.provider_metadata["statistics"]["observations"] == []
    assert work.provider_metadata["statistics"]["license"] is None


def test_data360_query_router_requires_explicit_statistics_topic_and_geography():
    calls = []

    def handler(request):
        calls.append(request)
        raise AssertionError("irrelevant or unscoped statistics request was dispatched")

    provider = WorldBankData360Provider(_client(handler))
    assert supports_query("What are population trends in India?")
    assert supports_query("How has GDP changed?")
    assert not supports_query("How does workplace AI adoption affect worker productivity outcomes?")
    assert not supports_query("What evidence informs this technology policy decision?")
    assert supports_geography("India")
    assert supports_geography("World")
    assert not supports_geography(None)
    assert not supports_geography("   ")
    assert provider.search("How has GDP changed?") == []
    assert provider.search("How has GDP changed?", geography=None) == []
    assert provider.search("How does workplace AI affect productivity?", geography="World") == []
    provider.close()

    assert calls == []


def test_data360_resolves_exact_country_and_requests_only_matching_area():
    country_response = [
        {"page": 1, "pages": 1, "per_page": "400", "total": 3},
        [
            {"id": "IND", "name": "India", "region": {"id": "SAS", "value": "South Asia"}},
            {
                "id": "USA",
                "name": "United States",
                "region": {"id": "NAC", "value": "North America"},
            },
            {"id": "WLD", "name": "World", "region": {"id": "NA", "value": "Aggregates"}},
        ],
    ]
    seen = []

    def handler(request):
        seen.append(request)
        if (
            request.url.host == httpx.URL(WORLD_BANK_COUNTRIES_URL).host
            and request.url.path == "/v2/country"
        ):
            assert request.url.params["format"] == "json"
            assert request.url.params["per_page"] == "400"
            return httpx.Response(200, json=country_response)
        if request.url == httpx.URL(SEARCH_URL):
            return httpx.Response(
                200,
                json={
                    "value": [
                        {
                            "series_description": {
                                "idno": INDICATOR,
                                "name": "Population, total",
                                "database_id": "WB_WDI",
                            }
                        }
                    ]
                },
            )
        if request.url.path.endswith("metadata"):
            return httpx.Response(200, json=_metadata())
        if request.url.path.endswith("data"):
            assert request.url.params["REF_AREA"] == "IND"
            return httpx.Response(
                200,
                json={
                    "count": 2,
                    "value": [
                        _observation(REF_AREA="WLD"),
                        _observation(REF_AREA="IND", OBS_VALUE="1463865525"),
                    ],
                },
            )
        raise AssertionError(f"Unexpected request: {request.method} {request.url}")

    provider = WorldBankData360Provider(_client(handler))
    works = provider.search("population", geography="India")
    provider.close()

    assert len(works) == 1
    work = works[0]
    assert work.external_id.endswith(":IND")
    assert "India" in work.title
    assert "REF_AREA=IND" in work.url
    assert work.provider_metadata["statistics"]["observations"][0]["geography_code"] == "IND"
    assert work.provider_metadata["statistics"]["observations"][0]["geography_name"] == "India"
    assert len(seen) == 4


def test_data360_rejects_aggregate_and_ambiguous_geographies_before_indicator_search():
    country_response = [
        {"page": 1, "pages": 1, "per_page": "400", "total": 4},
        [
            {"id": "IND", "name": "India", "region": {"id": "SAS"}},
            {"id": "WLD", "name": "World", "region": {"id": "NA"}},
            {"id": "AAA", "name": "Duplicate", "region": {"id": "SAS"}},
            {"id": "BBB", "name": "Duplicate", "region": {"id": "EAS"}},
        ],
    ]
    seen = []

    def handler(request):
        seen.append(request.url.path)
        if (
            request.url.host == httpx.URL(WORLD_BANK_COUNTRIES_URL).host
            and request.url.path == "/v2/country"
        ):
            return httpx.Response(200, json=country_response)
        raise AssertionError("Unsupported locations must not search or retrieve indicators")

    provider = WorldBankData360Provider(_client(handler))
    assert provider.search("population", geography="South Asia") == []
    assert provider.search("population", geography="Duplicate") == []
    provider.close()
    assert seen.count("/v2/country") == 2
    assert seen.count("/data360/searchv2") == 0


def test_data360_rejects_multi_country_geography_without_network_request():
    client = _client(lambda _request: (_ for _ in ()).throw(AssertionError("No request expected")))
    provider = WorldBankData360Provider(client)
    assert provider.search("population", geography="India; China") == []
    assert provider.search("population", geography="\nIndia") == []
    provider.close()


def test_country_catalog_rejects_conflicting_codes_and_resolves_names_or_codes_exactly():
    catalog = _country_catalog(
        [
            {"page": 1, "pages": 1, "per_page": "400", "total": 2},
            [
                {"id": "IND", "name": "India", "region": {"id": "SAS"}},
                {"id": "WLD", "name": "World", "region": {"id": "NA"}},
            ],
        ]
    )
    assert _resolve_country("India", catalog) == ("IND", "India")
    assert _resolve_country(" india ", catalog) == ("IND", "India")
    assert _resolve_country("IND", catalog) == ("IND", "India")
    assert _resolve_country("World", catalog) is None
    assert _resolve_country("IN", catalog) is None

    with pytest.raises(WorldBankData360Error, match="conflicting country codes"):
        _country_catalog(
            [
                {"page": 1, "pages": 1, "per_page": "400", "total": 2},
                [
                    {"id": "IND", "name": "India", "region": {"id": "SAS"}},
                    {"id": "IND", "name": "Other", "region": {"id": "SAS"}},
                ],
            ]
        )
    with pytest.raises(WorldBankData360Error, match="incomplete catalog"):
        _country_catalog(
            [
                {"page": 1, "pages": 2, "per_page": "200", "total": 296},
                [{"id": "IND", "name": "India", "region": {"id": "SAS"}}],
            ]
        )


def test_country_catalog_failure_is_sanitized_and_does_not_use_response_body():
    provider = WorldBankData360Provider(
        _client(lambda _request: httpx.Response(503, text="private gateway detail"))
    )
    with pytest.raises(WorldBankData360Error) as error:
        provider.search("population", geography="India")
    provider.close()
    assert str(error.value) == "World Bank Data360 request failed; scholarly discovery can continue"
    assert "private gateway detail" not in str(error.value)


def test_data360_discards_disaggregated_rows_and_non_finite_values():
    rows = [
        _observation(SEX="F"),
        _observation(OBS_VALUE="NaN"),
        _observation(REF_AREA="IND"),
        _observation(),
    ]

    def handler(request):
        if request.url.path.endswith("searchv2"):
            return httpx.Response(
                200,
                json={
                    "value": [
                        {
                            "series_description": {
                                "idno": INDICATOR,
                                "name": "Population, total",
                                "database_id": "WB_WDI",
                            }
                        }
                    ]
                },
            )
        if request.url.path.endswith("metadata"):
            return httpx.Response(200, json=_metadata())
        if request.url.path.endswith("data"):
            return httpx.Response(200, json={"count": 4, "value": rows})
        raise AssertionError("Unexpected request")

    provider = WorldBankData360Provider(_client(handler))
    work = provider.search("world population", geography="World")[0]
    provider.close()

    assert len(work.provider_metadata["statistics"]["observations"]) == 1
    assert work.provider_metadata["statistics"]["observations"][0]["value"] == "8215424893"


def test_data360_response_body_is_bounded_and_errors_are_sanitized():
    def oversized(_request):
        return httpx.Response(200, content=b" " * 600_000)

    provider = WorldBankData360Provider(_client(oversized))
    try:
        provider.search("population", geography="World")
    except WorldBankData360Error as exc:
        assert "512 KB" in str(exc)
    else:
        raise AssertionError("oversized provider response should fail")
    finally:
        provider.close()

    def failed(_request):
        return httpx.Response(503, text="upstream request id and private body")

    provider = WorldBankData360Provider(_client(failed))
    try:
        provider.search("population", geography="World")
    except WorldBankData360Error as exc:
        assert str(exc) == "World Bank Data360 request failed; scholarly discovery can continue"
        assert "private body" not in str(exc)
    else:
        raise AssertionError("provider failure should be sanitized")
    finally:
        provider.close()
