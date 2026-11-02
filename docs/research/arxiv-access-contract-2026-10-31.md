# arXiv access contract screen: METR developer-productivity study

**Checked:** 2026-10-31  
**Purpose:** Determine whether Veda's existing rights-gated acquisition path can safely use the METR study `arXiv:2507.09089v2` as its target-domain full-text example. This is a narrow source/access check, not a new literature review or legal opinion.

## Verified source identity and access facts

- The arXiv v2 page identifies Becker, Rush, Barnes, and Rein's *Measuring the Impact of Early-2025 AI on Experienced Open-Source Developer Productivity*, dated 2025-07-25, with a CC BY 4.0 license. The paper reports an RCT involving 16 experienced open-source developers and 246 tasks. [arXiv v2 HTML](https://arxiv.org/html/2507.09089v2)
- The page's Methods section describes developers, repositories, task construction, random assignment, AI-allowed/disallowed conditions, and self-reported completion time. It states that tasks were real repository issues, contributors had on average five years with their repositories, and the total completion-time outcome included pre- and post-PR review time. These are statements in the versioned paper, not independently replicated results. [arXiv v2 HTML](https://arxiv.org/html/2507.09089v2)
- OpenAlex's public metadata record returned HTTP 200 for DOI `10.48550/arXiv.2507.09089`, work `W4414690271`. It marks the work OA, but its `best_oa_location` is submittedVersion, has `license: null`, and points to an arXiv PDF. A separate DOI-level location carries `cc-by` but no PDF URL. These fields do not establish that the PDF route and CC-BY license refer to the same version.

## Official access constraints

- arXiv says versions can have different licenses; the assigned license appears on each abstract page. Its license page describes CC BY 4.0 as permitting redistribution, adaptation, and commercial use with attribution. [arXiv license information](https://info.arxiv.org/help/license/index.html)
- arXiv API terms say metadata is CC0, content may be retrieved/stored/used for personal or research purposes, and content must not be stored and served from another server unless the copyright holder's permission or the specific submission license permits it. The legacy APIs have a limit of one request every three seconds and one connection at a time. [arXiv API Terms of Use](https://info.arxiv.org/help/api/tou.html)
- arXiv's reuse FAQ says the legacy search API schema does not include full-text license; the license is available in OAI-PMH `arXiv` or `arXivRaw` records. [arXiv permissions and reuse](https://info.arxiv.org/help/license/reuse.html)
- arXiv's bulk-access documentation directs programmatic full-text harvesting to `export.arxiv.org`; its published S3 full-text buckets are requester-pays. [arXiv bulk access](https://info.arxiv.org/help/bulk_data.html) [arXiv S3 full text](https://info.arxiv.org/help/bulk_data_s3.html)

## Engineering decision and remaining validation

Veda's policy cannot combine a license from one OpenAlex location with the PDF URL from another location or infer a per-version license from a generic OA flag. No arXiv host was added to the generic HTML/PDF allowlist. A future adapter should retrieve the exact version/license from the documented OAI-PMH format, use a permitted version-specific content route, enforce the one-request-per-three-seconds aggregate limit, and store/display only what that version's license authorizes. The exact per-article export-service contract and a real target-paper acquisition have not yet been exercised by Veda.

This is a scoped integration gap, not evidence that the paper is inaccessible to Veda in principle. The live Europe PMC smoke recorded separately demonstrates the current JATS path only for a different CC-BY paper.
