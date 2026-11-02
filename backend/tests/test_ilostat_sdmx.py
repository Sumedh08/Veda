import httpx
import pytest

from app.providers.ilostat_sdmx import (
    DATA_URL,
    DATAFLOW_ID,
    ILOSTATError,
    ILOSTATProvider,
    parse_observations,
    supports_geography,
    supports_query,
)

CSV = (
    b"DATAFLOW,REF_AREA,FREQ,MEASURE,CLASSIF_SEX,CLASSIF_AGE,TIME_PERIOD,OBS_VALUE,"
    b"UNIT_MEASURE,UNIT_MULT,OBS_STATUS,SOURCE,SOURCE_NOTE,INDICATOR_NOTE,CLASSIFICATION_NOTE\n"
    b"ILO:DF_EMP_TEMP_SEX_AGE_NB(1.0),X01,A,EMP_TEMP_NB,SEX_T,AGE_5YRBANDS_TOTAL,"
    b"2024,3500000000,PERSONS,0,A,Labour force survey,Household survey source,"
    b"Employment total,All sexes and ages\n"
)


def _provider(handler):
    return ILOSTATProvider(httpx.Client(transport=httpx.MockTransport(handler)))


def test_ilostat_requests_one_pinned_global_series_with_protocol_bounds():
    seen = []

    def handler(request):
        seen.append(request)
        assert request.method == "GET"
        assert str(request.url).startswith(DATA_URL)
        assert dict(request.url.params) == {
            "lastNObservations": "1",
            "detail": "full",
            "format": "csv",
        }
        assert request.headers["Range"] == "values=1-10"
        assert "application/vnd.sdmx.data+csv" in request.headers["Accept"]
        return httpx.Response(
            200,
            content=CSV,
            headers={"Content-Type": "application/vnd.sdmx.data+csv;version=1.0.0"},
        )

    provider = _provider(handler)
    works = provider.search("global employment levels", geography="World")
    provider.close()

    assert len(seen) == 1
    assert len(works) == 1
    work = works[0]
    assert work.external_id == f"ilostat:{DATAFLOW_ID}:X01:2024"
    assert work.provider == "ILOSTAT"
    assert work.source_type == "official_statistics"
    stats = work.provider_metadata["statistics"]
    assert stats["license"].startswith("CC BY 4.0")
    assert "third-party exceptions apply" in stats["license"]
    assert stats["data_sources"][0]["name"] == "Labour force survey"
    assert stats["definition"] == "Employment total"
    assert stats["methodology"] == "Household survey source"
    assert stats["observations"] == [
        {
            "value": "3500000000",
            "period": "2024",
            "geography_code": "X01",
            "geography_name": "World",
            "unit_measure": "PERSONS",
            "unit_type": None,
            "unit_multiplier": 0,
            "observation_status": "A",
        }
    ]


@pytest.mark.parametrize(
    ("query", "geography"),
    [
        ("global population trend", "World"),
        ("global employment levels", "India"),
        ("global employment levels", None),
    ],
)
def test_ilostat_does_not_request_unrelated_or_unsupported_scopes(query, geography):
    def handler(_request):
        raise AssertionError("Unsupported ILOSTAT requests must not reach the network")

    provider = _provider(handler)
    assert provider.search(query, geography=geography) == []
    provider.close()


def test_ilostat_scope_and_topic_predicates_are_narrow():
    assert supports_query("Employment levels and jobs")
    assert supports_query("labour force participation")
    assert not supports_query("unemployment only")
    assert not supports_geography(None)
    assert not supports_geography("India")
    assert supports_geography("worldwide")


def test_ilostat_parser_requires_exact_dimensions_and_rejects_ambiguous_series():
    body = CSV.decode().replace("X01,A,EMP_TEMP_NB", "USA,A,EMP_TEMP_NB").encode()
    assert parse_observations(body) == []
    duplicate = CSV + CSV.splitlines()[1] + b"\n"
    with pytest.raises(ILOSTATError, match="ambiguous"):
        parse_observations(duplicate)


@pytest.mark.parametrize(
    "body",
    [
        b"not csv",
        b"x" * (512_000 + 1),
    ],
    ids=["invalid_csv", "oversized_csv"],
)
def test_ilostat_parser_fails_closed_on_invalid_or_oversized_data(body):
    with pytest.raises(ILOSTATError):
        parse_observations(body)


def test_ilostat_parser_does_not_persist_non_numeric_observations():
    body = CSV.replace(b"3500000000", b"NaN")
    assert parse_observations(body) == []


def test_ilostat_rejects_unexpected_media_type_and_sanitizes_service_errors():
    provider = _provider(
        lambda _request: httpx.Response(
            200, text="upstream detail", headers={"Content-Type": "text/html"}
        )
    )
    with pytest.raises(ILOSTATError, match="unexpected media type"):
        provider.search("employment", geography="World")
    provider.close()

    provider = _provider(lambda _request: httpx.Response(403, text="private gateway detail"))
    with pytest.raises(ILOSTATError, match="request failed") as error:
        provider.search("employment", geography="World")
    assert "private gateway detail" not in str(error.value)
    provider.close()
