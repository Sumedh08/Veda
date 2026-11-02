# Crossref record fields used for non-ROR publisher corroboration

## Primary contract

Crossref's official REST API schema documents work-level `publisher` metadata and a `link` array containing full-text locations, including URL and content-type metadata. See the [Crossref REST API metadata format](https://github.com/CrossRef/rest-api-doc/blob/master/api_format.md) and [Crossref REST API documentation](https://api.crossref.org/swagger-ui/index.html).

## Veda's bounded use

For a DOI-bearing public-web lead, Veda resolves the exact DOI when available, otherwise performs a bounded title lookup. It requires a title-overlap threshold, a non-empty Crossref publisher field, and an HTTPS Crossref full-text link whose host matches an eligible observed domain or a subdomain. This verifies a publisher-linked publication lead, not official-domain ownership. Official-site catalog or content access still requires a separately verified official domain. Search snippets are not persisted as findings or evidence passages.

This is corroboration of a publication/publisher/link relationship. Crossref metadata does **not** establish organization-wide authority, official-domain ownership, publication quality, research methodology, truth, copyright ownership, or Veda's permission to fetch or retain content. Rights-gated retrieval remains separate.

## 2026-11-02 WRI question-only provenance audit

The question-only run `21b901d6-c97d-4abc-acad-fd993ee6a7cc` found the WRI India climate-vulnerability report DOI `10.46830/wrirpt.22.00055` without a user-supplied organization. Crossref matched its title and publisher and deposited a PDF URL on `wri-india.org`; a search result on that host contained the report citation. ROR resolved the exact organization name to `https://ror.org/047ktk903`, but the saved ROR identity record had no official domains or official URLs. This combination supports the organization identity and a publisher-linked publication host; it does **not** independently verify `wri-india.org` as WRI's official domain.

That distinction exposed an overstatement in the saved report metadata. The workflow now keeps a Crossref-linked host in `publisher_linked_domains`, leaves `official_domains` to ROR-attested domains, records `official_domain_verified=false` when no ROR domain match exists, and does not launch official-site search from that unverified host. The API and source inspector render legacy records as “Publisher-linked domain · official site not independently verified” without rewriting historical report data. A focused persisted-workflow regression covers the boundary.

The Crossref record has no license metadata and its PDF link says `intended_application=similarity-checking`; that is not Veda retrieval or retention permission. The live job's official-site page-metadata attempt was rejected during redirect validation, and its official-site search returned no verified publication. No PDF, publisher body, Crawl4AI scrape, or model inference was fetched. The linked PDF's previously observed size exceeds Veda's 8 MiB cap. The actual Veda report therefore remains metadata-only and has no evidence passages; the domain/link and rights questions are still unresolved, not a blanket prohibition on WRI content.
