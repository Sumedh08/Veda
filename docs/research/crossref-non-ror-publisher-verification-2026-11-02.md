# Crossref record fields used for non-ROR publisher corroboration

## Primary contract

Crossref's official REST API schema documents work-level `publisher` metadata and a `link` array containing full-text locations, including URL and content-type metadata. See the [Crossref REST API metadata format](https://github.com/CrossRef/rest-api-doc/blob/master/api_format.md) and [Crossref REST API documentation](https://api.crossref.org/swagger-ui/index.html).

## Veda's bounded use

For a DOI-bearing public-web lead, Veda resolves the exact DOI when available, otherwise performs a bounded title lookup. It requires a title-overlap threshold, a non-empty Crossref publisher field, and an HTTPS Crossref full-text link whose host matches the observed domain or a subdomain. The linked work is then eligible for the existing bounded official-site publication catalog lookup. Search snippets are not persisted as findings or evidence passages.

This is corroboration of a publication/publisher/domain relationship. Crossref metadata does **not** establish organization-wide authority, publication quality, research methodology, truth, copyright ownership, or Veda's permission to fetch or retain content. Rights-gated retrieval remains separate. The path has offline tests only; a live non-ROR case remains unvalidated.
