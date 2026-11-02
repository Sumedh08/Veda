import httpx

from app.providers.crossref import CrossrefProvider, plain_text


def test_crossref_normalizes_metadata_and_bounds_abstract():
    payload = {
        "message": {
            "items": [
                {
                    "DOI": "10.1234/example",
                    "title": ["A study"],
                    "author": [{"given": "Ada", "family": "Lovelace"}],
                    "published": {"date-parts": [[2025, 4, 1]]},
                    "publisher": "Research Press",
                    "ISSN": ["1234-5679", "8765-4326"],
                    "abstract": "<jats:p>AI improved output in a controlled task.</jats:p>"
                    + "x" * 900,
                }
            ]
        }
    }

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "api.crossref.org"
        return httpx.Response(200, json=payload)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    provider = CrossrefProvider(client)
    record = provider.search("AI productivity", limit=8)[0]
    provider.close()

    assert record.external_id == "doi:10.1234/example"
    assert record.url == "https://doi.org/10.1234/example"
    assert record.published_year == 2025
    assert record.authors == [{"given": "Ada", "family": "Lovelace"}]
    assert len(record.abstract_excerpt or "") <= 560
    assert record.provider_metadata["abstract_excerpt_truncated"] is True
    assert record.provider_metadata["journal_issns"] == ["1234-5679", "8765-4326"]


def test_plain_text_strips_markup_and_decodes_entities():
    assert plain_text("<jats:p>Workers &amp; managers</jats:p>") == "Workers & managers"


def test_crossref_resolves_one_doi_without_querying_or_rewriting_the_identity():
    requests = []
    payload = {
        "message": {
            "DOI": "10.3389/fenrg.2025.1689106",
            "title": ["A grid integration planning approach"],
            "publisher": "Frontiers Media SA",
            "published": {"date-parts": [[2025, 1, 1]]},
            "license": [
                {
                    "URL": "https://creativecommons.org/licenses/by/4.0/",
                    "content-version": "vor",
                }
            ],
        }
    }

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=payload)

    provider = CrossrefProvider(httpx.Client(transport=httpx.MockTransport(handler)))
    try:
        work = provider.resolve_doi("10.3389/fenrg.2025.1689106")
    finally:
        provider.close()

    assert len(requests) == 1
    assert requests[0].url.host == "api.crossref.org"
    assert requests[0].url.path == "/works/10.3389/fenrg.2025.1689106"
    assert work.doi == "10.3389/fenrg.2025.1689106"
    assert work.publisher == "Frontiers Media SA"
    assert work.provider_metadata["crossref_full_text"]["license_code"] == "cc-by"


def test_crossref_doi_resolution_rejects_malformed_and_mismatched_dois():
    calls = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json={"message": {"DOI": "10.5555/other", "title": ["Other"]}})

    provider = CrossrefProvider(httpx.Client(transport=httpx.MockTransport(handler)))
    try:
        for value in ("https://doi.org/10.1234/example", "10.12/no"):
            try:
                provider.resolve_doi(value)
            except Exception:
                pass
            else:
                raise AssertionError("Malformed DOI should be rejected")
        assert calls == 0
        try:
            provider.resolve_doi("10.1234/example")
        except Exception:
            pass
        else:
            raise AssertionError("A response for a different DOI should be rejected")
        assert calls == 1
    finally:
        provider.close()


def test_crossref_affiliation_discovery_returns_only_records_with_matching_author_evidence():
    payload = {
        "message": {
            "items": [
                {
                    "DOI": "10.3390/en10070851",
                    "title": ["HVDC topology for offshore wind"],
                    "author": [
                        {
                            "given": "A",
                            "family": "Researcher",
                            "affiliation": [
                                {
                                    "name": "Research and Disruptive Innovation, Offshore Renewable Energy Catapult, UK"
                                }
                            ],
                        }
                    ],
                    "publisher": "MDPI AG",
                    "published": {"date-parts": [[2017, 6, 27]]},
                    "license": [
                        {
                            "URL": "https://creativecommons.org/licenses/by/4.0/",
                            "content-version": "vor",
                        }
                    ],
                    "link": [
                        {
                            "URL": "https://www.mdpi.com/1996-1073/10/7/851/pdf",
                            "content-type": "application/pdf",
                            "content-version": "vor",
                            "intended-application": "similarity-checking",
                        }
                    ],
                },
                {
                    "DOI": "10.5555/unrelated",
                    "title": ["Offshore wind policy overview"],
                    "author": [{"affiliation": [{"name": "Renewable Energy Institute, UK"}]}],
                    "publisher": "Research Press",
                },
            ]
        }
    }
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=payload)

    provider = CrossrefProvider(httpx.Client(transport=httpx.MockTransport(handler)))
    try:
        records = provider.search_for_organization(
            "offshore wind reliability cost",
            organization_names=["Offshore Renewable Energy Catapult", "ORE Catapult"],
            limit=3,
        )
    finally:
        provider.close()

    assert len(requests) == 1
    assert requests[0].url.params["query.affiliation"] == "Offshore Renewable Energy Catapult"
    assert requests[0].url.params["query.bibliographic"] == "offshore wind reliability cost"
    assert requests[0].url.params["rows"] == "3"
    assert [record.doi for record in records] == ["10.3390/en10070851"]
    metadata = records[0].provider_metadata
    assert metadata["matched_author_affiliation"] == (
        "Research and Disruptive Innovation, Offshore Renewable Energy Catapult, UK"
    )
    assert metadata["crossref_full_text"]["license_code"] == "cc-by"
    assert metadata["crossref_full_text"]["content_version"] == "vor"
    assert metadata["crossref_full_text"]["license_url"] == (
        "https://creativecommons.org/licenses/by/4.0/"
    )
    assert metadata["crossref_full_text"]["links"][0]["url"] == (
        "https://www.mdpi.com/1996-1073/10/7/851/pdf"
    )


def test_crossref_retries_one_transient_rate_limit_with_bounded_delay(monkeypatch):
    from app.providers import retry

    calls = 0
    waits = []
    monkeypatch.setattr(retry.time, "sleep", waits.append)

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(429, headers={"Retry-After": "0.5"})
        return httpx.Response(200, json={"message": {"items": []}})

    provider = CrossrefProvider(httpx.Client(transport=httpx.MockTransport(handler)))
    assert provider.search("AI productivity") == []
    provider.close()

    assert calls == 2
    assert waits == [0.5]


def test_crossref_defers_retry_when_server_delay_exceeds_local_bound():
    calls = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(429, headers={"Retry-After": "60"})

    provider = CrossrefProvider(httpx.Client(transport=httpx.MockTransport(handler)))
    try:
        provider.search("AI productivity")
    except Exception:
        pass
    else:
        raise AssertionError("Crossref rate limit should be surfaced")
    provider.close()
    assert calls == 1


def test_crossref_does_not_retry_non_transient_auth_failure():
    calls = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(403, text="private provider detail")

    provider = CrossrefProvider(httpx.Client(transport=httpx.MockTransport(handler)))
    try:
        provider.search("AI productivity")
    except Exception as exc:
        assert "private provider detail" not in str(exc)
    else:
        raise AssertionError("Crossref 403 should fail closed")
    provider.close()
    assert calls == 1
