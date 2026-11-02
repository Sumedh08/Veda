# Veda Research Context

Veda organizes evidence work into linked research runs. Each run keeps its own source and claim records and a saved report version so researchers can inspect how a conclusion was assembled.

## Research lineage

**Research run**:
A bounded question together with the plan, discovered sources, evidence, analysis, and report saved for that run.

**Follow-up run**:
A new question-led research run linked to an earlier run. Earlier claims can frame the follow-up search; the follow-up report cites evidence collected for that run.

**Retrieval continuation**:
A new run linked to a completed run that carries forward its saved evidence with lineage and retries only host-rate-deferred requests whose due time has arrived. Its report is a separate version in the research lineage.

**Deferred retrieval**:
A permitted source request that could not be sent within the active time window because the shared host interval was not yet available. It remains pending until its persisted due time and an owner starts a continuation.

## Evidence records

**Source record**:
The bibliographic identity and evidence access class for a scholarly work or official statistical series. The access class describes evidence available to Veda (for example abstract-only or bounded licensed HTML); it is not the result of a particular transport attempt.

**Retrieval outcome**:
The versioned result for one optional HTML or PDF attempt: not attempted, retrieved, partial, unavailable, error, or deferred. A retrieval error does not erase an abstract or metadata already available for the source.

**Conditional statistics route outcome**:
The versioned record of whether an optional official-statistics provider applied to a research question and geography, whether its request was attempted, and what the request returned. It does not establish that the returned observations are relevant or suitable evidence.

**Evidence snapshot**:
A versioned description of the exact document or bounded provider excerpt from which a passage was captured.

**Rights decision**:
A versioned, evidence-backed set of separate decisions for source metadata discovery, automated access, research analysis, text retention, and sharing. A private-research decision may allow bounded internal analysis and excerpts while limiting sharing to bibliographic citations; it is not a legal opinion or a public redistribution license.

**Source-reported claim**:
A short, exact statement linked to a stored passage. It records what the source says; it does not establish that the statement is true.

## Model-assisted analysis

**Model-assisted assessment**:
A generated judgment about stored evidence whose provenance and passage links are recorded. The label says how the judgment was produced; it does not establish independent verification or correctness.

**Model-authored synthesis**:
A report synthesis generated from the run's saved evidence and checked against its citation records. Its authorship does not make its conclusions scientifically reliable without review.

**Provider completion ceiling**:
The largest completion allocation supported by the selected provider/model endpoint. It is a route capability, not the number of tokens Veda should request for a task.

**Task completion allocation**:
The maximum tokens reserved for one structured research operation. It includes both reasoning and visible output when the provider charges or counts reasoning against the completion limit.

**Job output budget**:
The total task completion allocations a research run may reserve across its model operations. It is distinct from the run's monetary ceiling and from the provider's completion ceiling.

**Reported provider usage**:
Token counts and cost fields returned by the provider for one inference request. Missing fields remain unknown; an estimated reservation is not reported usage or confirmed account billing.
