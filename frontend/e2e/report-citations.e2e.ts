import AxeBuilder from '@axe-core/playwright';
import { expect, test, type Page, type Route } from '@playwright/test';

const projectId = 'project-browser-fixture';
const jobId = 'job-browser-fixture';
const conversationId = 'conversation-browser-fixture';
const followUpJobId = 'job-browser-follow-up-fixture';
const sourceId = 'source-browser-fixture';
const claimId = 'claim-browser-fixture';
const sourceSentence = 'The study reports a productivity association in its sampled firms; wage growth remained unchanged.';
const firstClaimUnit = 'The study reports a productivity association in its sampled firms';

const project = {
  id: projectId,
  title: 'AI adoption in small firms',
  description: 'Evidence for a local UI acceptance fixture.',
  domain: 'AI adoption economics',
  archived_at: null,
  purge_at: null,
  created_at: '2026-10-29T08:00:00Z',
  updated_at: '2026-10-29T08:00:00Z',
};

const profile = {
  name: 'standard',
  max_queries: 8,
  max_records_per_provider_query: 20,
  max_sources: 12,
  max_html_pages: 2,
  max_pdf_documents: 2,
  max_html_passages: 20,
  max_passages: 40,
  max_model_calls: 8,
  max_prompt_characters_per_call: 24_000,
  max_prompt_characters_total: 80_000,
  max_prompt_tokens_per_call: 6_000,
  max_prompt_token_budget_total: 20_000,
  max_output_tokens_per_call: 1_500,
  max_output_token_budget_total: 5_000,
  max_retries: 1,
  max_step_seconds: 20,
};

const job = {
  schema_version: 1,
  id: jobId,
  project_id: projectId,
  parent_job_id: null,
  conversation_id: conversationId,
  question: 'What does evidence say about AI adoption and small-firm productivity?',
  scope: { schema_version: 1, geography: 'India', population: 'Small firms', decision_objective: 'Whether to pilot AI adoption', extensions: {} },
  depth: 'standard',
  budget_ceiling_usd: 0,
  cost_spent_estimate_usd: 0,
  cost_reserved_usd: 0,
  model_calls_reserved: 0,
  prompt_characters_reserved: 0,
  prompt_token_budget_reserved: 0,
  output_token_budget_reserved: 0,
  resource_limits: profile,
  status: 'completed_with_limitations',
  current_stage: 'complete',
  version: 8,
  attempt: 1,
  error_class: null,
  error_message: null,
  created_at: '2026-10-29T08:10:00Z',
  updated_at: '2026-10-29T08:12:00Z',
};

const jobEvent = {
  schema_version: 1,
  id: 'job-event-browser-fixture',
  event_type: 'step_completed',
  stage: 'extraction',
  message: 'Extraction completed',
  data: { data_schema_version: 1, claim_count: 1, plan_version: 4, planning_mode: 'deterministic_fallback' },
  created_at: '2026-10-29T08:11:00Z',
};

const researchPlan = {
  schema_version: 4,
  version: 4,
  planning_mode: 'deterministic_fallback',
  planning_provenance: { status: 'deterministic_fallback', provider: null, model: null, fallback_reason: 'provider_disabled' },
  decision_context: {
    decision_objective: null,
    context: null,
    population: 'Small firms',
    geography: 'India',
    time_horizon: null,
  },
  scope_status: 'underspecified',
  missing_scope_fields: ['decision_objective', 'time_horizon'],
  scope_notice: 'Missing scope is not inferred. Results may not transfer to an unspecified population, geography, horizon, or decision objective.',
  planning_lenses: {
    comparator_or_counterfactual: { status: 'unspecified', user_statement: null, prompt: 'Inspect reported comparators; do not infer a causal counterfactual.' },
    outcomes: { status: 'unspecified', target_outcome: null, denominator: null, possible_outcomes_prompt: 'Record possible measured outcomes.', denominator_prompt: 'Record units and denominators or mark unknown.' },
    assumptions: { status: 'not_provided', user_supplied_text: null, system_inferred_assumptions: [] },
    confounding: { applicability: 'evaluate_if_nonrandomized_or_observational_evidence', considerations: ['confounding', 'selection_and_attrition', 'measurement_and_reporting', 'concurrent_changes_or_spillovers'], prompt: 'Assess risks conditionally; none are assumed.' },
    evidence_types: { types_to_consider: ['randomized_or_experimental', 'quasi_experimental', 'observational_or_panel'], mode: 'planning_lenses_only_not_provider_filters', provider_type_filter_applied: false },
  },
  queries: ['small-firm AI productivity', 'small-firm AI productivity counterevidence'],
  query_rationales: [
    { query: 'small-firm AI productivity', purpose: 'Find direct primary and scholarly evidence for the stated question.', focus: 'direct_evidence' },
    { query: 'small-firm AI productivity counterevidence', purpose: 'Search explicitly for null, negative, conflicting, and alternative findings.', focus: 'counterevidence' },
  ],
  subquestions: [{ text: 'What evidence informs productivity decisions?', purpose: 'Answer within the explicit question scope.' }],
  stopping_criteria: {
    execution: 'Attempt only saved queries within the depth and provider limits.',
    insufficient_evidence: 'If eligible evidence is absent, report the gap and abstain from a specific effect conclusion.',
    incomparability: 'Describe incompatible populations and outcomes separately.',
    counterevidence: 'A bounded search with no counterevidence does not show none exists.',
  },
};

const source = {
  id: sourceId,
  title: 'AI adoption and productivity in small firms',
  doi: '10.5555/veda-browser-fixture',
  url: 'https://example.org/research-paper',
  authors: [{ given: 'Asha', family: 'Researcher' }],
  published_year: 2025,
  publisher: 'Example Journal',
  provider: 'crossref',
  source_governance: {
    registry_version: 'fixture-registry-v1',
    source_classes: ['academic'],
    matched_registry_ids: [],
    matched_identity_provenance: [],
    matched_institution_identifiers: [],
    matched_organization_identifiers: [],
    identity_status: 'unregistered',
    quality_review_status: 'not_assessed',
    methodological_quality: 'not_assessed',
    methodology_review_required: true,
    academic_preference: 'NONE',
    quality_claim_is_truth_claim: false,
    matched_institution_rankings: [],
    matched_journal_classifications: [],
    unverified_classification_count: 0,
    discovery_status: 'not_integrated',
    selection_guidance: 'eligible_by_relevance_and_methodology_review',
    counterevidence_exception: false,
  },
  source_type: 'scholarly_article',
  retrieval_status: 'abstract_only',
  retrieval: {
    status: 'failed', scope: 'metadata', license: null, error_code: 'timeout',
    outcomes: { schema_version: 1, by_format: {
      html: { schema_version: 1, format: 'html', outcome: 'error', error_code: 'timeout', observed_at: '2026-10-29T08:11:00Z' },
    } },
  },
  abstract_excerpt: sourceSentence,
  abstract_text_available_at_discovery: true,
  abstract_text_retention_status: 'legacy_not_recorded',
  appraisal: { schema_version: 1, status: 'model_assessed_not_independently_verified', provider: 'openrouter', model: 'fixture/free', fields: {
    design_type: { value: 'Observational panel study', passage_ids: ['passage-browser-fixture'], status: 'model_assessed_not_independently_verified' },
    limitations: { value: 'Small sampled population limits generalization', passage_ids: ['passage-browser-fixture'], status: 'model_assessed_not_independently_verified' },
  } },
  passages: [{
    id: 'passage-browser-fixture',
    source_id: sourceId,
    ordinal: 0,
    locator: 'abstract sentence 1',
    content: sourceSentence,
    content_hash: 'fixture-sha256',
    access_level: 'abstract_excerpt',
    truncated: false,
    document_id: 'document-browser-fixture',
    identity_version: 1,
    document: {
      id: 'document-browser-fixture',
      schema_version: 1,
      source_version: 'fixture-v1',
      document_sha256: 'a'.repeat(64),
      retrieved_at: '2026-10-29T08:11:00Z',
      locator: 'provider abstract excerpt',
      media_type: 'text/plain',
      access_class: 'abstract_only',
      hash_scope: 'bounded_provider_excerpt',
    },
  }],
};

const officialStatisticsSource = {
  ...source,
  title: 'Employment by sex and age — ILOSTAT (World)',
  publisher: 'International Labour Organization',
  provider: 'ILOSTAT',
  source_governance: {
    ...source.source_governance,
    source_classes: ['official_statistics', 'multilateral'],
    matched_registry_ids: ['ilo'],
    identity_status: 'verified',
  },
  source_type: 'official_statistics',
  retrieval_status: 'official_statistics',
  appraisal: { status: 'not_applicable' },
  retrieval: { status: 'official_statistics', scope: 'global', license: 'CC BY-4.0' },
  statistics: {
    indicator_id: 'EMP_TEMP_SEX_AGE_NB',
    indicator_name: 'Employment by sex and age (total employment, number)',
    database_id: 'ILOSTAT',
    dataset_name: 'ILOSTAT labour statistics database',
    dataset_url: 'https://ilostat.ilo.org/data/',
    dataset_terms_url: 'https://www.ilo.org/rights-and-permissions',
    license: 'CC BY 4.0 under ILO Open Access policy for post-2023 datasets; third-party exceptions apply',
    license_url: 'https://creativecommons.org/licenses/by/4.0/',
    attribution: 'International Labour Organization (ILO), ILOSTAT.',
    definition: 'Employment total.',
    statistical_concept: 'All sexes and ages.',
    methodology: 'Labour force survey.',
    limitations: 'Descriptive aggregate; review source and rights notes.',
    periodicity: 'Annual',
    source_update_date: null,
    measurement_unit: 'PERSONS',
    retrieved_at: '2026-10-29T08:11:00Z',
    data_sources: [{ name: 'Labour force survey', organization: 'As reported in ILOSTAT', publisher: 'International Labour Organization', url: null }],
    observations: [{ value: '3500000000', period: '2024', geography_code: 'X01', geography_name: 'World', unit_measure: 'PERSONS', unit_type: null, unit_multiplier: 0, observation_status: 'A' }],
  },
};

const candidates = [
  {
    id: 'candidate-selected-fixture',
    provider: 'Crossref',
    provider_record_id: 'doi:10.5555/veda-browser-fixture',
    canonical_identity: 'doi:10.5555/veda-browser-fixture',
    title: source.title,
    doi: source.doi,
    url: source.url,
    published_year: source.published_year,
    query: 'small-firm AI productivity',
    disposition: 'selected',
    reason_code: 'selected_by_relevance',
    relevance_score: 0.85,
    source_governance: source.source_governance,
    planned_query_score: 0.72,
    selection_score: 0.85,
    relevance: {
      schema_version: 1, algorithm: 'lexical_overlap_v1', ranking_query_basis: 'user_research_question', score: 0.85, score_scale: '0_to_1',
      query_term_count: 4, query_terms: ['ai', 'firm', 'productivity', 'small'],
      query_terms_truncated: false,
      matched_title_terms: ['ai', 'firm', 'productivity', 'small'], matched_abstract_terms: ['ai', 'productivity'],
      title_coverage: 1, abstract_coverage: 0.5, weights: { title_coverage: 0.7, abstract_coverage: 0.3 },
      explanation: 'Matched 4 of 4 query terms in the title and 2 in the abstract excerpt.',
      planned_query_alignment: {
        schema_version: 1, algorithm: 'lexical_overlap_v1', ranking_query_basis: 'recorded_provider_query', score: 0.72,
        query_term_count: 5, query_terms: ['ai', 'firm', 'productivity', 'small', 'study'], query_terms_truncated: false,
        matched_title_terms: ['ai', 'firm', 'productivity', 'small'], matched_abstract_terms: ['ai', 'productivity'],
        title_coverage: 0.8, abstract_coverage: 0.4, weights: { title_coverage: 0.7, abstract_coverage: 0.3 },
        explanation: 'Matched 4 of 5 planned-query terms in the title and 2 in the abstract excerpt.',
        interpretation_limit: 'Retrieval relevance only; not source quality, study validity, claim support, or truth.',
      },
      selection_score: 0.85,
      selection_basis: 'user_question',
      interpretation_limit: 'Retrieval relevance only; not source quality, study validity, claim support, or truth.',
    },
    canonical_source_id: sourceId,
    discovered_at: '2026-10-29T08:11:00Z',
  },
  {
    id: 'candidate-excluded-fixture',
    provider: 'OpenAlex',
    provider_record_id: 'https://openalex.org/W-fixture',
    canonical_identity: 'openalex:w-fixture',
    title: 'A candidate excluded by the source cap',
    abstract_excerpt: null,
    abstract_excerpt_retention_status: 'not_retained_item_text_rights_unverified',
    doi: null,
    url: 'https://example.org/candidate',
    published_year: 2024,
    query: 'counterevidence and limitations',
    disposition: 'excluded',
    reason_code: 'source_limit',
    canonical_source_id: null,
    discovered_at: '2026-10-29T08:11:02Z',
  },
];

const report = {
  id: 'report-browser-fixture',
  job_id: jobId,
  status: 'limited',
  version: 2,
  citation_map_schema_version: 1,
  verification_schema_version: 1,
  body_markdown: '# Evidence map\n\nThe source reports a productivity association in its sampled firms [S1].\n\n## Limitations\n\nThis is a browser fixture, not a research finding.',
  citation_map: {
    S1: {
      source_id: sourceId,
      title: source.title,
      doi: source.doi,
      url: source.url,
      passages: [source.passages[0].id],
    },
  },
  verification: {
    status: 'passed',
    level: 'deterministic_link_integrity_only',
    claims_checked: 1,
    claims_with_valid_source_and_passage: 1,
    citation_link_integrity: {
      schema_version: 1,
      level: 'deterministic_link_integrity_only',
      status: 'passed',
      claims_checked: 1,
      claims_with_valid_source_and_passage: 1,
    },
    semantic_assessment: {
      schema_version: 1,
      method: 'not_performed',
      support_check: 'not_performed',
      uncited_material_claim_scan: 'not_performed',
      provider: null,
      model: null,
      audit_schema_version: null,
      items: [],
      uncited_claims: [],
      rejected_records: 0,
      input_truncated: false,
      skip_reason: null,
    },
    model_assisted_appraisal: 'not_performed',
    evidence_sufficiency_v2: {
      schema_version: 1,
      status: 'PRELIMINARY_EVIDENCE_MAP',
      covered_requirement_ids: ['Q1'],
      uncovered_requirement_ids: [],
      blocking_conditions: ['independent_corroboration_not_established'],
      question_plan: { question_kind: 'descriptive', scope_breadth: 'bounded', material_requirements: [{ requirement_id: 'Q1', text: 'Describe measured productivity outcomes.' }] },
      independence: { content_bearing_publication_groups: 1, independent_investigations_confirmed: 0, unknown_independence_publications: 1 },
      material_requirement_evidence: [{ requirement_id: 'Q1', linked_publication_identities: ['doi:10.0000/example'], supporting_publication_identities: [], confirmed_independent_investigation_ids: [], independence_unknown_publication_identities: ['doi:10.0000/example'], known_non_independent_publication_identities: [] }],
      human_review_status: 'not_performed',
      scientific_validation_status: 'not_independently_validated',
    },
    semantic_support_check: 'not_performed',
    uncited_material_claim_scan: 'not_performed',
    semantic_audit_items: [],
    uncited_material_claims: [],
    semantic_audit_batch_coverage: {
      schema_version: 1,
      method: 'bounded_item_batches_and_overlapped_report_text_v1',
      report_characters: 150,
      expected_batches: 2,
      attempted_batches: 2,
      completed_batches: 1,
      complete: false,
      expected_item_ids: ['F1'],
      assessed_item_ids: [],
      skipped_item_ids: [],
      scan_character_coverage: 90,
      scan_complete: false,
      output_limit_batch_ids: [],
      unresolved_batch_ids: ['SA002'],
      batches: [
        { batch_id: 'SA001', status: 'completed', scan_start: 0, scan_end: 90, provider: 'sarvam', model: 'glm5.3-flash', error_class: null },
        { batch_id: 'SA002', status: 'uncertain', scan_start: 0, scan_end: 150, provider: 'sarvam', model: 'glm5.3-flash', error_class: 'model_call_uncertain' },
      ],
    },
    claim_units: [{
      claim_id: claimId,
      text: firstClaimUnit,
      span_start: 0,
      span_end: firstClaimUnit.length,
      atomization_status: 'atomized_exact_span',
      atomization_version: 1,
      economic_facets: {
        status: 'model_assessed_not_independently_verified',
        evidence_kind: 'association',
        facets: { outcome: { value: 'Productivity', status: 'model_assessed_not_independently_verified' } },
      },
    }],
    decision_implication_status: 'accepted_with_deterministic_scope_and_evidence_gates',
    decision_implications: [{
      action: 'collect_more_evidence',
      condition: 'Before using the result to make a local implementation decision.',
      rationale: 'The retrieved passage covers sampled firms only.',
      assumptions: ['The sample may not match the intended workplace.'],
      unknowns: ['Local implementation costs are not reported.'],
      claim_ids: [claimId],
      passage_ids: [source.passages[0].id],
      citations: ['S1'],
      status: 'model_generated_conditional_not_independently_verified',
    }],
    search_coverage: {
      status: 'recorded',
      discovery_completed_at_utc: '2026-10-29T08:11:30Z',
      providers: ['Crossref', 'OpenAlex'],
      queries_planned: 2,
      provider_queries_attempted: 4,
      search_lens_counts: { planned: 2, completed: 1, partial: 1, failed: 0, not_attempted: 0 },
      counterevidence_search_status: 'completed',
      source_governance: {
        schema_version: 1,
        plan_status: 'persisted_at_discovery',
        policy_version: 'topic-cues-source-classes-v1',
        registry_version: 'fixture-registry-v1',
        planned_classes: ['academic', 'consulting', 'think_tank'],
        class_selection_reasons: {
          academic: ['default scholarly discovery route'],
          consulting: ['productivity'],
          think_tank: ['productivity'],
        },
        searched_classes: ['academic'],
        missing_classes: ['consulting', 'think_tank'],
        coverage_complete: false,
        class_status: {
          academic: { status: 'searched', candidate_count: 2, selected_count: 1 },
          consulting: { status: 'not_integrated', candidate_count: 0, selected_count: 0 },
          think_tank: { status: 'not_integrated', candidate_count: 0, selected_count: 0 },
        },
        interpretation_limit: 'identity does not establish source quality',
      },
      retrieval_stopping_reason: 'source_cap_excluded_candidates',
      selected_sources: 1,
      candidate_ledger_records: 2,
      duplicate_records_excluded: 1,
      records_excluded_by_source_cap: 1,
      candidate_exclusion_counts: { duplicate_canonical_identity: 1, source_limit: 1 },
      search_lenses: [
        {
          lens_id: 'L1', category: 'DIRECT_QUESTION', purpose: 'Find direct empirical evidence.', focus: 'direct_evidence',
          exact_query: 'small-firm AI productivity', status: 'completed', pagination_state: 'single_page_bounded',
          candidate_keys: ['candidate-selected-fixture'], selected_candidate_keys: ['candidate-selected-fixture'],
          providers: [{ provider: 'Crossref', status: 'completed', results: 1 }, { provider: 'OpenAlex', status: 'completed', results: 1 }],
        },
        {
          lens_id: 'L2', category: 'CONTRARY_OR_NULL_EVIDENCE', purpose: 'Search null and contrary results.', focus: 'counterevidence',
          exact_query: 'small-firm AI productivity counterevidence', status: 'partial', pagination_state: 'single_page_bounded',
          candidate_keys: ['candidate-excluded-fixture'], selected_candidate_keys: [],
          providers: [{ provider: 'Crossref', status: 'completed', results: 1 }, { provider: 'OpenAlex', status: 'failed', results: 0, error_code: 'rate_limited' }],
        },
      ],
      citation_expansion_status: 'partial',
      citation_expansion: {
        status: 'partial', method: 'openalex_one_hop_bounded_v1', requests_attempted: 3,
        seed_work_ids: ['W123'], omitted_backward_count: 14, reported_cost_status: 'unknown', reported_cost_usd: null,
        sampling_note: 'Bounded one-hop sample only; this is not complete citation coverage.',
        errors: [{ stage: 'forward_citations', error_code: 'rate_limited', retry_after_seconds: 45 }],
      },
    },
  },
  model_name: null,
  created_at: '2026-10-29T08:12:00Z',
};

function json(route: Route, body: unknown, status = 200) {
  return route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });
}

async function installApiFixtures(
  page: Page,
  options: {
    projectInitiallyStored?: boolean;
    emptyProjectHistory?: boolean;
    initialJobStatus?: string;
    officialStatistics?: boolean;
    unreviewedHost?: boolean;
    localSignInStatus?: number;
    archivedProjectInitiallyStored?: boolean;
    withComparisons?: boolean;
    seedConversation?: boolean;
    expiredProjectSession?: boolean;
    projectListFailureOnce?: boolean;
    projectListFailureRequestId?: string;
    projectListDelayMs?: number;
    projectListDelayAfterFirst?: boolean;
    projectHistoryFailures?: 'jobs' | 'conversations' | 'both';
    projectHistoryDelayMs?: number;
    deferredRetry?: boolean;
    modelAssistedPlan?: boolean;
    modelAssistedSynthesis?: boolean;
    modelExecutionPlan?: boolean;
    jatsFullText?: boolean;
    grobidFullText?: boolean;
    fullTextEvidence?: boolean;
    omitAdaptiveRequirementEvidence?: boolean;
    openAlexContentAvailability?: { pdf?: boolean; grobid_xml?: boolean };
    crossrefVerifiedPublisher?: boolean;
    openaireCatalogPublication?: boolean;
    privateResearchRights?: boolean;
    providerStatus?: { active_provider: string; provider_ready: boolean; model: string | null; paid_calls_allowed: boolean };
  } = {},
) {
  const hasPermittedFullText = Boolean(
    options.fullTextEvidence || options.grobidFullText || options.jatsFullText || options.officialStatistics,
  );
  const reportBeforeModelLabel = hasPermittedFullText
    ? report
    : {
        ...report,
        body_markdown: '# Historical report text withheld\n\nThis saved report cites abstract-only evidence whose item/version text reuse rights were not recorded. The stored report and evidence records are unchanged; their text is withheld from this view and export pending a rights decision.',
        evidence_content_withheld: true,
        content_withheld_reason: 'item_version_reuse_rights_not_recorded',
        verification: {
          ...report.verification,
          claim_units: [],
          decision_implications: [],
          uncited_material_claims: [],
          semantic_audit_items: [],
          semantic_assessment: {
            ...report.verification.semantic_assessment,
            items: [],
            uncited_claims: [],
            rejected_records: [],
          },
        },
      };
  const displayedReport = options.modelAssistedSynthesis
    ? {
        ...reportBeforeModelLabel,
        verification: {
          ...reportBeforeModelLabel.verification,
          model_assisted_synthesis: 'performed_not_independently_verified',
        },
      }
    : reportBeforeModelLabel;
  if (options.omitAdaptiveRequirementEvidence && displayedReport.verification.evidence_sufficiency_v2) {
    delete displayedReport.verification.evidence_sufficiency_v2.material_requirement_evidence;
  }
  const displayedResearchPlan = options.modelAssistedPlan
    ? {
        ...researchPlan,
        planning_mode: 'model_assisted_selection',
        planning_provenance: {
          status: 'model_selection_applied',
          provider: 'openrouter',
          model: 'openrouter/free',
          fallback_reason: null,
        },
      }
    : researchPlan;
  const displayedEvents = options.modelExecutionPlan
    ? [jobEvent, {
        schema_version: 1,
        id: 'job-event-model-resource-plan',
        event_type: 'resource_plan',
        stage: 'appraisal',
        message: 'Saved the model allocation before dispatch.',
        data: {
          data_schema_version: 1,
          plan_timing: 'before_first_appraisal_dispatch',
          model_execution_plan: {
            provider: 'sarvam', model: 'sarvam-105b', complete: false,
            required_calls: 7, planned_calls: 6, deferred_calls: 1,
            required_output_tokens: 28672, planned_output_tokens: 24576,
            reserved_calls_before_plan: 1,
            authorized_spend_ceiling: 3.5, authorized_spend_currency: 'INR',
            remaining_authorized_spend: 3.1, latency_estimate_ms: null,
            latency_estimate_status: 'unavailable_no_validated_provider_stage_baseline',
            daily_quota_snapshot: { global_remaining: 12, per_user_remaining: 5 },
            accepted: [{ operation: 'appraisal', stage: 'appraisal', batch: 1, completion_tokens: 4096 }],
            deferred: [{ operation: 'semantic', stage: 'semantic_audit', batch: 1, completion_tokens: 4096, deferred_reason: 'request_quota' }],
          },
        },
        created_at: '2026-10-29T08:10:30Z',
      }]
    : [jobEvent];
  const activeSourceBase = options.grobidFullText
    ? {
        ...source,
        retrieval_status: 'full_text_pdf',
        abstract_excerpt: null,
        retrieval: {
          status: 'retrieved',
          scope: 'openalex_best_oa_location',
          license: 'cc-by',
          parser_name: 'grobid',
          parser_version: '0.9.1-abc123',
          grobid: { status: 'parsed', parser_version: '0.9.1-abc123' },
          structured_document: {
            parser_name: 'grobid',
            parser_version: '0.9.1-abc123',
            representation_format: 'tei',
            sections_count: 2,
            passages_count: 2,
            extraction_status: 'complete',
            methods_results_usable: true,
            sections: [
              { section_id: 'tei-section-0001', original_heading: 'Methods', normalized_type: 'methods', section_path: ['Methods'], ordinal: 1, source_locator: 'TEI/text/body/div[1]' },
              { section_id: 'tei-section-0002', original_heading: 'Results', normalized_type: 'results', section_path: ['Results'], ordinal: 2, source_locator: 'TEI/text/body/div[2]' },
            ],
          },
          outcomes: { schema_version: 1, by_format: {} },
        },
        passages: [{
          ...source.passages[0],
          id: 'passage-grobid-browser-fixture',
          locator: 'TEI Methods [tei-section-0001] paragraph 1 sentence 1',
          content: 'Participants were randomized to the AI-assisted and control conditions.',
          access_level: 'full_text_pdf',
          document: {
            ...source.passages[0].document,
            id: 'document-grobid-browser-fixture',
            access_class: 'full_text_pdf',
            locator: 'PDF document parsed to GROBID TEI',
            media_type: 'application/pdf',
          },
        }],
      }
    : options.jatsFullText
    ? {
        ...source,
        retrieval_status: 'full_text_jats',
        abstract_excerpt: null,
        retrieval: {
          status: 'retrieved',
          scope: 'europe_pmc_full_text_xml',
          license: 'CC BY 4.0',
          jats: {
            status: 'retrieved',
            pmcid: 'PMC1234567',
            rights_decision: 'permitted',
            raw_license: 'CC BY 4.0',
            retrieved_at: '2026-10-31T08:00:00Z',
          },
          structured_document: {
            parser_name: 'veda_jats',
            parser_version: 'jats-v1',
            sections_count: 3,
            passages_count: 3,
            extraction_status: 'complete',
            methods_results_usable: true,
          },
          outcomes: { schema_version: 1, by_format: {} },
        },
        passages: [{
          ...source.passages[0],
          id: 'passage-jats-browser-fixture',
          locator: 'Methods > Study design · XML sec[1] p[1]',
          content: 'Methods: The authors randomized 48 participants to two task conditions.',
          access_level: 'full_text_jats',
          document: {
            ...source.passages[0].document,
            id: 'document-jats-browser-fixture',
            access_class: 'full_text_jats',
            locator: 'Europe PMC JATS XML',
            media_type: 'application/xml',
          },
        }],
      }
    : options.fullTextEvidence
    ? {
        ...source,
        retrieval_status: 'full_text_html',
        abstract_excerpt: null,
        abstract_text_retention_status: 'not_retained_item_text_rights_unverified',
        passages: [{
          ...source.passages[0],
          locator: 'Results · paragraph 1 sentence 1',
          access_level: 'full_text_html',
          document: {
            ...source.passages[0].document,
            locator: 'Licensed HTML source version',
            access_class: 'full_text_html',
            media_type: 'text/html',
          },
        }],
      }
    : options.deferredRetry
    ? {
        ...source,
        provider: 'OpenAlex',
        retrieval: {
          status: 'deferred',
          scope: 'openalex_best_oa_location',
          license: 'cc-by',
          deferred_retries: {
            html: {
              status: 'pending',
              due_at: new Date(Date.now() - 1000).toISOString(),
              retry_after_seconds: 0,
            },
          },
        },
      }
    : options.officialStatistics
    ? officialStatisticsSource
    : options.unreviewedHost
      ? {
          ...source,
          provider: 'OpenAlex',
          retrieval: {
            status: 'failed', scope: 'openalex_best_oa_location', license: 'cc-by',
            license_evidence: 'OpenAlex best_oa_location metadata assertion',
            site_policy_status: 'denied_or_unknown', error_code: 'host_policy_unknown',
          },
        }
      : {
          ...source,
          abstract_excerpt: null,
          passages: [{
            ...source.passages[0],
            content: '[Abstract text withheld: item/version reuse permission for storage and display was not recorded.]',
            content_withheld_reason: 'item_version_reuse_rights_not_recorded',
            access_level: 'abstract_only',
          }],
        };
  const sourceWithOrganization = options.crossrefVerifiedPublisher
    ? {
        ...activeSourceBase,
        organization_provenance: {
          organization_id: 'crossref-publisher:browser-fixture',
          organization_name: 'Unseeded Wind Systems Laboratory',
          identity_status: 'VERIFIED_DOMAIN_SPECIALIST',
          verification_method: 'crossref_publisher_doi_title_and_link_domain_match',
          verification_source: 'https://api.crossref.org/works/10.5555%2Fpublisher-report',
          openalex_institution_id: null,
          quality_assessment: 'not_assessed',
          publisher_verification: 'crossref_doi_title_publisher_and_link_domain_match',
          official_domain: 'example.org',
          official_publication_url: 'https://example.org/research-paper',
          publication_discovery_provider: 'Crawl4AI Cloud question search plus Crossref publisher record',
          publication_content_access: 'not_retrieved',
          publication_rights_status: 'metadata_only_not_assessed',
        },
      }
    : activeSourceBase;
  const sourceWithPublicationProvenance = options.openaireCatalogPublication
    ? {
        ...sourceWithOrganization,
        provider: 'OpenAIRE',
        source_type: 'institutional_report',
        publication_provenance: {
          schema_version: 1,
          provider: 'OpenAIRE',
          verification_status: 'catalog_corroborated',
          verification_method: 'exact_catalog_title_location_and_publisher_domain_match',
          catalog_record_id: 'openaire____::report-fixture',
          publisher_organization_id: 'openaire____::org-fixture',
          organization_identity_status: 'VERIFIED_DOMAIN_SPECIALIST',
          official_domain: 'example.org',
          discovery_lead_url: 'https://example.org/reports/urban-heat-adaptation',
          catalog_location_url: 'https://example.org/reports/urban-heat-adaptation',
          metadata_license: 'CC-BY',
          metadata_attribution: 'OpenAIRE Graph; attribution required under CC-BY',
          metadata_license_url: 'https://graph.openaire.eu/docs/apis/terms/',
          content_rights_status: 'not_assessed',
        },
      }
    : sourceWithOrganization;
  const sourceWithAvailability = options.openAlexContentAvailability
    ? {
        ...sourceWithPublicationProvenance,
        provider: 'OpenAlex',
        openalex_fulltext_availability: options.openAlexContentAvailability,
      }
    : sourceWithPublicationProvenance;
  const activeSource = options.privateResearchRights
    ? {
        ...sourceWithAvailability,
        retrieval: {
          ...sourceWithAvailability.retrieval,
          rights_assessment: {
            discovery: 'PERMITTED_METADATA',
            access: 'PERMITTED',
            analysis: 'PERMITTED_WITH_LIMITATIONS',
            retention: 'LIMITED_EXCERPTS',
            sharing: 'CITATION_ONLY',
            basis: 'india_private_research_exception_candidate',
            policy_version: 'private-research-v1',
            legal_review_required: false,
            max_retained_verbatim_characters: 1200,
            max_retained_passages: 4,
            robots_status: 'rules_checked',
            site_terms_status: 'checked_no_restriction_signal',
            verified_domains: ['example.org'],
            terms_url: 'https://example.org/terms',
            reason_codes: ['private_research_exception_candidate'],
            warnings: ['This is not a legal opinion or redistribution grant.'],
          },
        },
      }
    : sourceWithAvailability;
  const projectListRequestCounter = { count: 0 };
  let currentProject = project;
  let retentionDays: 30 | 90 | 365 | null = null;
  let projects = options.projectInitiallyStored === false ? [] : [currentProject];
  let archivedProjects = options.archivedProjectInitiallyStored ? [{ ...project, archived_at: '2026-10-29T08:20:00Z', purge_at: null }] : [];
  let jobs = options.projectInitiallyStored === false || options.emptyProjectHistory ? [] : [{
    ...job,
    status: options.initialJobStatus || job.status,
    current_stage: options.initialJobStatus === 'paused' ? 'plan' : job.current_stage,
  }];
  let currentJob = jobs[0] || null;
  const planForCurrentJob = () => ({
    ...displayedResearchPlan,
    decision_context: {
      ...displayedResearchPlan.decision_context,
      context: currentJob?.scope.context ?? displayedResearchPlan.decision_context.context,
    },
  });
  let conversations: Array<{ id: string; project_id: string; title: string; created_at: string }> = options.seedConversation
    ? [{ id: conversationId, project_id: projectId, title: job.question, created_at: job.created_at }]
    : [];
  let messages: Array<{ id: string; conversation_id: string; role: 'user' | 'assistant'; content: string; related_job_id: string | null; created_at: string }> = options.seedConversation ? [
    { id: 'message-browser-older', conversation_id: conversationId, role: 'assistant', content: 'Earlier update: discovery was bounded to the available scholarly providers.', related_job_id: jobId, created_at: '2026-10-29T08:09:00Z' },
    { id: 'message-browser-intermediate', conversation_id: conversationId, role: 'assistant', content: 'The saved evidence map keeps each finding linked to its source.', related_job_id: jobId, created_at: '2026-10-29T08:09:30Z' },
    { id: 'message-browser-question', conversation_id: conversationId, role: 'user', content: job.question, related_job_id: jobId, created_at: job.created_at },
  ] : [];
  let expiredSessionReturned = false;
  let projectListFailureCount = options.projectListFailureOnce ? 1 : 0;
  let jobsFailureCount = options.projectHistoryFailures === 'jobs' || options.projectHistoryFailures === 'both' ? 2 : 0;
  let conversationsFailureCount = options.projectHistoryFailures === 'conversations' || options.projectHistoryFailures === 'both' ? 2 : 0;
  let advanceCount = 0;
  await page.route('**/api/v1/**', async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname.replace('/api/v1', '');
    if (path === '/auth/dev-session' && request.method() === 'POST') {
      if (options.localSignInStatus) return json(route, { detail: 'Local development sign-in is disabled.' }, options.localSignInStatus);
      return json(route, { access_token: 'browser-fixture-token' });
    }
    if (path === '/projects' && request.method() === 'GET') {
      if (url.searchParams.get('archived_only') === 'true') return json(route, { items: archivedProjects, limit: 100, offset: 0 });
      projectListRequestCounter.count += 1;
      if (options.expiredProjectSession && !expiredSessionReturned) {
        expiredSessionReturned = true;
        return json(route, { detail: 'The local session has expired.' }, 401);
      }
      if (projectListFailureCount > 0) {
        projectListFailureCount -= 1;
        if (options.projectListFailureRequestId) {
          return json(route, { error: {
            code: 'storage_unavailable',
            message: 'Project service temporarily unavailable.',
            request_id: options.projectListFailureRequestId,
          } }, 503);
        }
        return json(route, { detail: 'Project service temporarily unavailable.' }, 503);
      }
      if (options.projectListDelayMs && (!options.projectListDelayAfterFirst || projectListRequestCounter.count > 1)) {
        await new Promise((resolve) => setTimeout(resolve, options.projectListDelayMs));
      }
      return json(route, { items: projects, limit: 100, offset: 0 });
    }
    if (path === '/projects' && request.method() === 'POST') {
      const payload = request.postDataJSON() as { title: string; description: string; domain: string };
      currentProject = { ...currentProject, ...payload };
      projects = [currentProject, ...projects];
      return json(route, currentProject, 201);
    }
    if (path === `/projects/${projectId}` && request.method() === 'PATCH') {
      const payload = request.postDataJSON() as { title: string; description: string; domain: string };
      currentProject = { ...currentProject, ...payload, updated_at: '2026-10-29T08:30:00Z' };
      projects = projects.map((item) => item.id === projectId ? currentProject : item);
      return json(route, currentProject);
    }
    if (path === `/projects/${projectId}` && request.method() === 'DELETE') {
      const archivedAt = '2026-10-29T08:31:00Z';
      const purgeAt = retentionDays ? new Date(Date.parse(archivedAt) + retentionDays * 86_400_000).toISOString() : null;
      archivedProjects = [{ ...currentProject, archived_at: archivedAt, purge_at: purgeAt }, ...archivedProjects];
      projects = projects.filter((item) => item.id !== projectId);
      return route.fulfill({ status: 204 });
    }
    if (path === `/projects/${projectId}/permanent` && request.method() === 'DELETE') {
      const payload = request.postDataJSON() as { confirmation: string; project_title: string };
      if (payload.confirmation !== 'DELETE' || payload.project_title !== currentProject.title) {
        return json(route, { detail: 'Type DELETE and the exact project title to permanently remove its Veda data.' }, 409);
      }
      archivedProjects = archivedProjects.filter((item) => item.id !== projectId);
      projects = projects.filter((item) => item.id !== projectId);
      currentJob = null;
      jobs = [];
      conversations = [];
      messages = [];
      return route.fulfill({ status: 204 });
    }
    if (path === `/projects/${projectId}/restore` && request.method() === 'POST') {
      currentProject = { ...currentProject, archived_at: null, purge_at: null };
      archivedProjects = archivedProjects.filter((item) => item.id !== projectId);
      projects = [currentProject, ...projects];
      return json(route, currentProject);
    }
    if (path === `/projects/${projectId}/research-jobs` && request.method() === 'GET') {
      if (jobsFailureCount > 0) {
        jobsFailureCount -= 1;
        return json(route, { detail: 'Research-run history is temporarily unavailable.' }, 503);
      }
      if (options.projectHistoryDelayMs) await new Promise((resolve) => setTimeout(resolve, options.projectHistoryDelayMs));
      return json(route, { items: jobs });
    }
    if (path === `/projects/${projectId}/research-jobs` && request.method() === 'POST') {
      const payload = request.postDataJSON() as { question: string; context?: string; geography?: string; population?: string; parent_job_id?: string | null };
      if (payload.parent_job_id === jobId) {
        currentJob = {
          ...job,
          id: followUpJobId,
          parent_job_id: jobId,
          question: payload.question,
          scope: { ...job.scope, context: payload.context || null },
          status: 'active',
          current_stage: 'plan',
        };
        jobs = [currentJob, ...jobs];
        messages = [...messages, { id: 'message-browser-follow-up', conversation_id: conversationId, role: 'user', content: payload.question, related_job_id: followUpJobId, created_at: '2026-10-29T08:32:00Z' }];
        return json(route, currentJob, 201);
      }
      currentJob = {
        ...job,
        question: payload.question,
        scope: { schema_version: 1, context: payload.context || null, geography: payload.geography || 'India', population: payload.population || 'Small firms', extensions: {} },
        status: 'active',
        current_stage: 'plan',
      };
      jobs = [currentJob];
      conversations = [{ id: conversationId, project_id: projectId, title: payload.question, created_at: job.created_at }];
      messages = [{ id: 'message-browser-question', conversation_id: conversationId, role: 'user', content: payload.question, related_job_id: currentJob.id, created_at: job.created_at }];
      return json(route, currentJob, 201);
    }
    if (path === `/projects/${projectId}/conversations`) {
      if (conversationsFailureCount > 0) {
        conversationsFailureCount -= 1;
        return json(route, { detail: 'Conversation history is temporarily unavailable.' }, 503);
      }
      if (options.projectHistoryDelayMs) await new Promise((resolve) => setTimeout(resolve, options.projectHistoryDelayMs));
      return json(route, { items: conversations });
    }
    if (path.startsWith(`/research-jobs/${followUpJobId}`)) {
      const suffix = path.slice(`/research-jobs/${followUpJobId}`.length);
      const childJob = jobs.find((item) => item.id === followUpJobId) || { ...job, id: followUpJobId, parent_job_id: jobId };
      if (!suffix) return json(route, childJob);
      if (suffix === '/events') return json(route, { items: [] });
      if (suffix === '/sources') return json(route, { items: [activeSource] });
      if (suffix === '/candidates') return json(route, { items: candidates, total: candidates.length, limit: 200, offset: 0 });
      if (suffix === '/claims') return json(route, { items: [{
        id: claimId, source_id: sourceId, passage_id: source.passages[0].id,
        text: firstClaimUnit,
        source_sentence: sourceSentence,
        span_start: 0,
        span_end: firstClaimUnit.length,
        span_offset_unit: 'unicode_codepoint_exclusive_end',
        atomization_status: 'atomized_exact_span',
        atomization_version: 1,
        claim_type: 'source_reported_result', evidence_status: 'source_reported_not_verified', appraisal: {},
      }] });
      if (suffix === '/relationships' || suffix === '/hypotheses') return json(route, { items: [], status: 'not_assessed', message: 'Model review was not performed.' });
      if (suffix === '/plan') return json(route, planForCurrentJob());
      if (suffix === '/report') return json(route, { ...report, job_id: followUpJobId });
      if (suffix === '/follow-up-context') return json(route, {
        status: options.deferredRetry ? 'retrieval_continuation' : 'available',
        parent: { job_id: jobId, question: job.question, report_id: report.id, report_status: report.status },
        reuse_method: options.deferredRetry ? 'source_snapshot_copy_and_deferred_fetch_retry' : 'lexical_overlap',
        reuse_boundary: options.deferredRetry
          ? 'Previously saved evidence snapshots were copied with lineage IDs.'
          : 'Parent claims frame the search but are not automatically carried into this run citations.',
        claims: options.deferredRetry ? [] : [{
          claim: { id: claimId, source_id: sourceId, passage_id: source.passages[0].id, text: firstClaimUnit, source_sentence: sourceSentence, span_start: 0, span_end: firstClaimUnit.length, atomization_status: 'atomized_exact_span', atomization_version: 1, claim_type: 'source_reported_result', evidence_status: 'source_reported_not_verified', appraisal: {} },
          source: { id: sourceId, title: source.title, retrieval_status: source.retrieval_status },
          passage: { id: source.passages[0].id, locator: source.passages[0].locator },
        }],
      });
    }
    if (path === `/research-jobs/${jobId}/retry-deferred` && request.method() === 'POST' && options.deferredRetry) {
      currentJob = { ...job, id: followUpJobId, parent_job_id: jobId, status: 'queued', current_stage: 'extraction' };
      jobs = [currentJob, ...jobs];
      return json(route, { job: currentJob, queued_retry_count: 1, idempotent_replay: false });
    }
    if (path === `/research-jobs/${jobId}`) return currentJob ? json(route, currentJob) : json(route, { detail: 'Not found' }, 404);
    if (path === `/research-jobs/${jobId}/resume` && request.method() === 'POST' && currentJob) {
      currentJob = { ...currentJob, status: 'active' };
      jobs = [currentJob];
      return json(route, currentJob);
    }
    if (path === `/research-jobs/${jobId}/advance` && request.method() === 'POST' && currentJob) {
      advanceCount += 1;
      currentJob = advanceCount > 1 || options.initialJobStatus === 'paused'
        ? { ...currentJob, status: 'completed_with_limitations', current_stage: 'complete' }
        : { ...currentJob, current_stage: 'search' };
      jobs = [currentJob];
      return json(route, currentJob);
    }
    if (path === `/research-jobs/${jobId}/events`) return json(route, { items: displayedEvents });
    if (path === `/research-jobs/${jobId}/sources`) return json(route, { items: [activeSource] });
    if (path === `/research-jobs/${jobId}/candidates`) return json(route, { items: candidates, total: candidates.length, limit: 200, offset: 0 });
    if (path === `/research-jobs/${jobId}/claims`) {
      return json(route, { items: [{
        id: claimId,
        source_id: sourceId,
        passage_id: source.passages[0].id,
        text: firstClaimUnit,
        source_sentence: sourceSentence,
        span_start: 0,
        span_end: firstClaimUnit.length,
        span_offset_unit: 'unicode_codepoint_exclusive_end',
        atomization_status: 'atomized_exact_span',
        atomization_version: 1,
        claim_type: 'source_reported_result',
        evidence_status: 'source_reported_not_verified',
        appraisal: {},
        economic_facets: {
          schema_version: 1,
          status: 'model_assessed_not_independently_verified',
          evidence_kind: 'association',
          provider: 'openrouter',
          model: 'openrouter/free',
          facets: {
            population: { value: 'Sampled small firms', passage_ids: [source.passages[0].id], status: 'model_assessed_not_independently_verified' },
            intervention_or_exposure: { value: 'AI adoption', passage_ids: [source.passages[0].id], status: 'model_assessed_not_independently_verified' },
            comparator: { value: 'unknown', passage_ids: [], status: 'not_reported_or_unlinked' },
            outcome: { value: 'Productivity', passage_ids: [source.passages[0].id], status: 'model_assessed_not_independently_verified' },
            estimate: { value: 'unknown', passage_ids: [], status: 'not_reported_or_unlinked' },
            uncertainty: { value: 'unknown', passage_ids: [], status: 'not_reported_or_unlinked' },
            geography: { value: 'unknown', passage_ids: [], status: 'not_reported_or_unlinked' },
            time_period: { value: 'unknown', passage_ids: [], status: 'not_reported_or_unlinked' },
            measure: { value: 'unknown', passage_ids: [], status: 'not_reported_or_unlinked' },
          },
        },
      }] });
    }
    if (path === `/research-jobs/${jobId}/relationships`) {
      if (options.withComparisons) return json(route, { items: [{
        id: 'relationship-browser-fixture', claim_a_id: claimId, claim_b_id: claimId,
        relationship_type: 'scope_difference', scope_alignment: 'different', scope_differences: ['geography'],
        rationale: 'The reports refer to different study scopes and should not be pooled as if they describe one population.',
        evidence: [{ claim_id: claimId, passage_ids: [source.passages[0].id] }],
        status: 'model_assessed_not_independently_verified', schema_version: 1, provider: 'fixture', model: 'fixture-model', created_at: job.created_at,
      }], status: 'model_assessed_not_independently_verified' });
      return json(route, { items: [], status: 'not_assessed', message: 'Model review was not performed.' });
    }
    if (path === `/research-jobs/${jobId}/hypotheses`) {
      if (options.withComparisons) return json(route, { items: ['A', 'B'].map((side) => ({
        id: `hypothesis-${side}-browser-fixture`, comparison_group_id: 'group-browser-fixture', side,
        statement: side === 'A' ? 'AI adoption may improve productivity when firms can reorganize workflows.' : 'Measured productivity gains may reflect selection of already capable firms.',
        evidence: [{ claim_id: claimId, passage_ids: [source.passages[0].id] }],
        uncertainty: 'The fixture does not establish a causal effect.',
        why_competing: 'The observed association can arise from adoption effects or selection into adoption.',
        status: 'model_assessed_not_independently_verified', schema_version: 1, provider: 'fixture', model: 'fixture-model', created_at: job.created_at,
      })), status: 'model_assessed_not_independently_verified' });
      return json(route, { items: [], status: 'not_assessed', message: 'Model review was not performed.' });
    }
    if (path === `/conversations/${conversationId}/messages`) {
      const offset = Number(url.searchParams.get('offset') || 0);
      const page = options.seedConversation && offset === 2 ? [messages[0]] : messages.slice(-2);
      return json(route, { items: page, limit: 200, offset, has_more: options.seedConversation && offset === 0 });
    }
    if (path === `/research-jobs/${jobId}/plan`) {
      return json(route, planForCurrentJob());
    }
    if (path === `/research-jobs/${jobId}/report`) return json(route, displayedReport);
    if (path === '/settings/providers') {
      return json(route, options.providerStatus ?? { active_provider: 'disabled', provider_ready: false, model: null, paid_calls_allowed: false });
    }
    if (path === '/settings/depth-profiles') {
      return json(route, { profiles: { quick: { ...profile, name: 'quick' }, standard: profile, deep: { ...profile, name: 'deep' } } });
    }
    if (path === '/me/preferences' && request.method() === 'PATCH') {
      const payload = request.postDataJSON() as { retention_days?: 30 | 90 | 365 | null };
      retentionDays = payload.retention_days ?? null;
      return json(route, { default_depth: 'standard', default_budget_ceiling_usd: 0, retention_days: retentionDays, is_customized: true, updated_at: '2026-10-29T08:00:00Z' });
    }
    if (path === '/me/preferences' && request.method() === 'DELETE') {
      retentionDays = null;
      return json(route, { default_depth: 'standard', default_budget_ceiling_usd: 0, retention_days: null, is_customized: false, updated_at: null });
    }
    if (path === '/me/preferences') {
      return json(route, { default_depth: 'standard', default_budget_ceiling_usd: 0, retention_days: retentionDays, is_customized: retentionDays !== null, updated_at: null });
    }
    if (path === '/me/data-lifecycle') {
      return json(route, {
        report_exports: { status: 'available', formats: ['markdown', 'json'], scope: 'One report at a time.' },
        project_archive: { status: 'available', effect: 'Projects are retained and can be restored.', restore_supported: true },
        project_permanent_deletion: { status: 'available', detail: 'Archived projects can be permanently deleted after typing DELETE and the exact project title.' },
        full_account_export: { status: 'available', alternative: 'Download Veda-stored account research records as JSON.', endpoint: '/api/v1/me/export', format: 'json' },
        account_deletion: { status: 'unsupported', detail: 'The Veda-data purge does not remove your sign-in account. Identity-provider account deletion must be requested from the configured authentication provider.' },
        veda_data_deletion: { status: 'available', endpoint: '/api/v1/me/data', confirmation_phrase: 'DELETE VEDA DATA', detail: "Permanently removes your Veda-stored projects and research records and resets your saved preferences. It is blocked while a bounded research step is running. Your sign-in account, operator-held backups, and current UTC day's quota safety counter are not deleted; export your data first if you need a copy." },
        retention: { status: 'configurable_archived_project_retention', options_days: [30, 90, 365], detail: 'Expired projects are removed only when deployment maintenance runs.' },
      });
    }
    if (path === '/me/data' && request.method() === 'DELETE') {
      const payload = request.postDataJSON() as { confirmation?: string };
      if (payload.confirmation !== 'DELETE VEDA DATA') return json(route, { detail: 'Type DELETE VEDA DATA to confirm.' }, 422);
      const deletedProjects = new Set([...projects, ...archivedProjects].map((item) => item.id)).size;
      projects = [];
      archivedProjects = [];
      jobs = [];
      currentJob = null;
      conversations = [];
      messages = [];
      retentionDays = null;
      return json(route, {
        deleted_projects: deletedProjects,
        deleted_preferences: true,
        daily_quota_counters_preserved_until_utc_date: '2026-10-29',
        identity_provider_account_deleted: false,
      });
    }
    if (path === '/me/export' && request.method() === 'GET') {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        headers: { 'content-disposition': 'attachment; filename="veda-account-export-2026-10-29.json"', 'cache-control': 'no-store', 'access-control-expose-headers': 'Content-Disposition, X-Request-ID' },
        body: JSON.stringify({ export: { schema_version: 1 }, collections: { projects: [project], research_jobs: [job], sources: [source] } }),
      });
    }
    if (path === `/sources/${sourceId}`) return json(route, activeSource);
    if (path === `/claims/${claimId}/evidence`) {
      return json(route, { claim: { id: claimId, source_id: sourceId, passage_id: source.passages[0].id, text: firstClaimUnit, source_sentence: sourceSentence, span_start: 0, span_end: firstClaimUnit.length, span_offset_unit: 'unicode_codepoint_exclusive_end', atomization_status: 'atomized_exact_span', atomization_version: 1, claim_type: 'source_reported_result', evidence_status: 'source_reported_not_verified', appraisal: { schema_version: 1, methodology_appraisal: { schema_version: 1, status: 'model_assessed_not_independently_verified', relationship: 'qualifies', rationale: 'The study design supports an association claim but does not identify a causal effect.', passage_ids: [source.passages[0].id], provider: 'openrouter', model: 'fixture/free' } }, economic_facets: {
        schema_version: 1, status: 'model_assessed_not_independently_verified', evidence_kind: 'association', provider: 'openrouter', model: 'openrouter/free',
        facets: {
          population: { value: 'Sampled small firms', passage_ids: [source.passages[0].id], status: 'model_assessed_not_independently_verified' },
          intervention_or_exposure: { value: 'AI adoption', passage_ids: [source.passages[0].id], status: 'model_assessed_not_independently_verified' },
          comparator: { value: 'unknown', passage_ids: [], status: 'not_reported_or_unlinked' },
          outcome: { value: 'Productivity', passage_ids: [source.passages[0].id], status: 'model_assessed_not_independently_verified' },
          estimate: { value: 'unknown', passage_ids: [], status: 'not_reported_or_unlinked' },
          uncertainty: { value: 'unknown', passage_ids: [], status: 'not_reported_or_unlinked' },
          geography: { value: 'unknown', passage_ids: [], status: 'not_reported_or_unlinked' },
          time_period: { value: 'unknown', passage_ids: [], status: 'not_reported_or_unlinked' },
          measure: { value: 'unknown', passage_ids: [], status: 'not_reported_or_unlinked' },
        },
      } }, source: activeSource, passage: source.passages[0], methodology_passages: [source.passages[0]] });
    }
    if (path === `/reports/${report.id}/export`) {
      return route.fulfill({
        status: 200,
        contentType: 'text/markdown',
        headers: { 'content-disposition': 'attachment; filename=veda-report-browser-fixture.md' },
        body: report.body_markdown,
      });
    }
    return json(route, { error: { message: `Unexpected browser fixture request: ${request.method()} ${path}` } }, 404);
  });
  return { projectListRequestCounter };
}

async function openProject(page: Page, options: Parameters<typeof installApiFixtures>[1] = {}) {
  await installApiFixtures(page, options);
  await page.goto('/');
  await page.getByRole('button', { name: 'Continue to local workspace' }).click();
  if (options.projectInitiallyStored === false) return;
  await page.locator('.project-grid').getByRole('button', { name: /AI adoption in small firms/ }).click();
}

async function openJob(page: Page, options: Parameters<typeof installApiFixtures>[1] = {}) {
  await openProject(page, options);
  if (options.projectInitiallyStored === false) return;
  await page.locator('.job-list').getByRole('button', { name: /What does evidence say about AI adoption/ }).click();
}

async function openReport(
  page: Page,
  options: Parameters<typeof installApiFixtures>[1] = {},
) {
  await openJob(page, options);
  await expect(page.getByRole('tab', { name: /report/i })).toBeVisible({ timeout: 15_000 });
  await page.getByRole('tab', { name: /report/i }).click();
  await expect(
    page.getByRole('heading', {
      name: options.fullTextEvidence || options.grobidFullText || options.jatsFullText || options.officialStatistics
        ? 'Evidence map'
        : 'Historical report text withheld',
      exact: true,
    }),
  ).toBeVisible();
}

async function expectNoAxeViolations(page: Page, viewName: string) {
  const scan = await new AxeBuilder({ page })
    .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
    .analyze();
  expect(scan.violations, `${viewName}: ${JSON.stringify(scan.violations)}`).toEqual([]);
}

async function expectNoHorizontalOverflow(page: Page, viewName: string) {
  const overflowing = await page.evaluate(() => {
    const width = document.documentElement.clientWidth;
    return [...document.body.querySelectorAll<HTMLElement>('*')]
      .map((element) => {
        const rect = element.getBoundingClientRect();
        return {
          tag: element.tagName.toLowerCase(),
          className: typeof element.className === 'string' ? element.className : '',
          text: (element.innerText || '').slice(0, 90),
          left: Math.round(rect.left),
          right: Math.round(rect.right),
          width: Math.round(rect.width),
        };
      })
      .filter((item) => item.width > 0 && item.right > width + 1)
      .slice(0, 12);
  });
  expect(overflowing, `${viewName} overflow: ${JSON.stringify(overflowing)}`).toEqual([]);
}

test('report citations open their source inspector by mouse and keyboard', async ({ page }) => {
  await openReport(page);
  await expect(page.getByText(/Historical report text is withheld because abstract-version text reuse rights were not recorded/)).toBeVisible();
  await expect(page.getByText(sourceSentence, { exact: true })).toHaveCount(0);
  const coverage = page.locator('.audit-card');
  await expect(coverage).toContainText('Scholarly search coverage');
  await expect(coverage).toContainText('Governed source-class coverage · registry fixture-registry-v1');
  await expect(coverage).toContainText('consulting: not integrated');
  await expect(coverage).toContainText('planned because the question matched: productivity');
  await expect(coverage).toContainText('small-firm AI productivity counterevidence');
  await expect(coverage).toContainText('Candidate exclusions');
  await expect(coverage).toContainText('retry-after 45s');
  await expect(coverage).toContainText('not a measure of study quality');
  await expect(coverage).toContainText('Official statistics routing');
  await expect(coverage).toContainText('Routing was not recorded for this historical report.');
  await expect(coverage).toContainText('Semantic audit input coverage');
  await expect(coverage).toContainText('1 of 2 batches completed');
  await expect(coverage).toContainText('SA002 · uncertain');
  const citation = page.getByRole('button', { name: 'Open source S1' });
  await expect(citation).toBeVisible();
  await citation.focus();
  await page.keyboard.press('Enter');
  const inspector = page.locator('.evidence-drawer');
  await expect(inspector.getByText('SOURCE INSPECTOR')).toBeVisible();
  await expect(inspector.getByRole('heading', { name: source.title })).toBeVisible();
  await expect(inspector.getByText('Legacy abstract text is stored; item/version reuse rights were not recorded.')).toBeVisible();
  await expect(inspector.getByText(/Abstract text withheld: item\/version reuse permission/)).toBeVisible();
  await expect(inspector.getByText(source.passages[0].content, { exact: true })).toHaveCount(0);
  await expect(inspector.getByText(/Snapshot v1 · fixture-v1 · SHA-256 a{16}/)).toBeVisible();
  await expect(inspector.getByRole('heading', { name: 'Source identity and registry' })).toBeVisible();
  await expect(inspector.getByText('No verified ranking/list match', { exact: true })).toBeVisible();
  await expect(inspector.getByRole('heading', { name: 'Methodological appraisal' })).toBeVisible();
  await expect(inspector.getByText('Observational panel study', { exact: true })).toBeVisible();
  await expect(inspector.getByText('Small sampled population limits generalization', { exact: true })).toBeVisible();
  const appraisalPassage = inspector.getByRole('link', { name: 'View linked passage abstract sentence 1' }).first();
  await expect(appraisalPassage).toHaveAttribute('href', '#source-passage-passage-browser-fixture');
  await appraisalPassage.click();
  await expect(inspector.locator('#source-passage-passage-browser-fixture')).toContainText('Abstract text withheld');
  await inspector.getByRole('button', { name: 'Close source inspector' }).click();
  await expect(inspector).toHaveCount(0);
});

test('source inspector preserves Crossref identity evidence without labeling it ROR', async ({ page }) => {
  await openReport(page, { crossrefVerifiedPublisher: true });
  await page.getByRole('button', { name: 'Open source S1' }).click();
  const inspector = page.getByRole('dialog', { name: 'AI adoption and productivity in small firms' });
  await expect(inspector).toBeVisible();
  await expect(inspector).toContainText('Unseeded Wind Systems Laboratory');
  await expect(inspector).toContainText(/verified domain specialist/i);
  await expect(inspector).toContainText('crossref doi title publisher and link domain match');
  await expect(inspector.getByRole('link', { name: 'Open verification record' })).toHaveAttribute(
    'href',
    'https://api.crossref.org/works/10.5555%2Fpublisher-report',
  );
  await expect(inspector.getByText(/Identity evidence supports the listed organization\/domain or publisher-publication relationship only/)).toBeVisible();
  await expect(inspector.getByText('Publication rights', { exact: true })).toBeVisible();
});

test('source inspector separates OpenAIRE catalog corroboration from content rights', async ({ page }) => {
  await openReport(page, { openaireCatalogPublication: true });
  await page.getByRole('button', { name: 'Open source S1' }).click();
  const inspector = page.getByRole('dialog', { name: source.title });
  await expect(inspector).toBeVisible();
  await expect(inspector.getByRole('heading', { name: 'Publication catalog corroboration' })).toBeVisible();
  await expect(inspector).toContainText('catalog corroborated');
  await expect(inspector).toContainText('openaire____::report-fixture');
  await expect(inspector).toContainText('OpenAIRE Graph; attribution required under CC-BY');
  await expect(inspector).toContainText('Document rights');
  await expect(inspector).toContainText('not assessed');
  await expect(inspector).toContainText('does not establish the organization\'s general authority');
});

test('source inspector separates private research analysis from sharing rights', async ({ page }) => {
  await openReport(page, { fullTextEvidence: true, privateResearchRights: true });
  await page.getByRole('button', { name: 'Open source S1' }).click();
  const inspector = page.locator('.evidence-drawer');
  await expect(inspector.getByText('PERMITTED_WITH_LIMITATIONS', { exact: true })).toBeVisible();
  await expect(inspector.getByText('LIMITED_EXCERPTS · at most 4 passages / 1200 characters')).toBeVisible();
  await expect(inspector.getByText('CITATION_ONLY', { exact: true })).toBeVisible();
  await expect(inspector.getByText('This is not a legal opinion or redistribution grant.')).toBeVisible();
  await expect(inspector.getByRole('link', { name: 'Open terms' })).toHaveAttribute(
    'href',
    'https://example.org/terms',
  );
  await expect(inspector.getByText(source.passages[0].content, { exact: true })).toBeVisible();
});

test('model-authored synthesis is labeled separately from a preliminary evidence map', async ({ page }) => {
  await openReport(page, { modelAssistedSynthesis: true });
  await expect(
    page.getByRole('heading', { name: 'Model-assisted research synthesis' }),
  ).toBeVisible();
});

test('a due deferred scholarly request can be continued as a linked child run', async ({ page }) => {
  await openJob(page, { deferredRetry: true });
  const retry = page.getByRole('button', { name: 'Continue deferred retrieval (1)' });
  await expect(retry).toBeEnabled();
  await retry.click();
  await page.getByRole('tab', { name: /conversation/i }).click();
  await expect(page.getByRole('heading', { name: 'Evidence carried into this continuation' })).toBeVisible();
  await expect(page.getByText(/Only the listed due, deferred URLs are retried/)).toBeVisible();
  await expect(page.getByRole('heading', { name: 'What informed this follow-up' })).toHaveCount(0);
});

test('report claim-unit manifest opens an inspector with the exact source span highlighted', async ({ page }) => {
  await openReport(page, { fullTextEvidence: true });
  const manifest = page.locator('.claim-unit-manifest');
  await expect(manifest).toContainText('Source claim units (1)');
  await manifest.locator('summary').click();
  await expect(manifest).toContainText('Economic facets (model assessed not independently verified): outcome: Productivity');
  await manifest.getByRole('button', { name: 'Inspect exact source span' }).click();
  const inspector = page.locator('.evidence-drawer');
  await expect(inspector.getByRole('heading', { name: firstClaimUnit })).toBeVisible();
  await expect(inspector.locator('mark.claim-span-highlight')).toHaveText(firstClaimUnit);
  await expect(inspector.locator('.claim-source-quote')).toContainText(sourceSentence);
  await expect(inspector.locator('.claim-source-quote')).toContainText(`Unicode codepoint span [0, ${firstClaimUnit.length})`);
});

test('source library exposes candidate exclusions and abstract-text rights omissions', async ({ page }) => {
  await page.setViewportSize({ width: 360, height: 800 });
  await openJob(page);
  await page.getByRole('tab', { name: /sources/i }).click();
  await page.getByRole('tab', { name: /all candidates/i }).click();
  await expect(page.getByText('A candidate excluded by the source cap')).toBeVisible();
  await expect(page.getByText(/Abstract text omitted: reuse rights are not verified for this source version/)).toBeVisible();
  await expect(page.getByText('source limit', { exact: true })).toBeVisible();
  await expect(page.getByText(/Source class: academic · identity unregistered · methodology not assessed/)).toBeVisible();
  await expect(page.getByText('counterevidence and limitations', { exact: false })).toBeVisible();
  await expect(page.getByText('QUESTION SCORE 0.85')).toBeVisible();
  await expect(page.getByText('QUERY SCORE 0.72')).toBeVisible();
  await expect(page.getByText('RANK SCORE 0.85')).toBeVisible();
  await expect(page.getByText(/retrieval relevance only; not source quality/i)).toBeVisible();
  await expect(page.getByText(/deterministic lexical scores remain visible as the baseline/i)).toBeVisible();
  await expect(page.getByText(/a bounded model review may promote a directly relevant bibliographic record past a lexical topic-gate miss/i)).toBeVisible();
  const viewport = await page.evaluate(() => ({ client: document.documentElement.clientWidth, scroll: document.documentElement.scrollWidth }));
  expect(viewport.scroll).toBeLessThanOrEqual(viewport.client + 1);
});

test('source inspector exposes ILOSTAT rights and descriptive-series metadata', async ({ page }) => {
  await openJob(page, { officialStatistics: true });
  await page.getByRole('tab', { name: /sources/i }).click();
  await page.getByRole('button', { name: /Employment by sex and age — ILOSTAT/ }).click();
  const inspector = page.locator('.evidence-drawer');
  await expect(inspector.getByRole('heading', { name: 'Official statistical series' })).toBeVisible();
  await expect(inspector.getByText('NOT A STUDY')).toBeVisible();
  await expect(inspector.getByText('3500000000')).toBeVisible();
  await expect(inspector.getByText('PERSONS', { exact: true })).toBeVisible();
  await expect(inspector.getByText('CC BY 4.0 under ILO Open Access policy for post-2023 datasets; third-party exceptions apply')).toBeVisible();
  await expect(inspector.getByText('As reported in ILOSTAT')).toBeVisible();
  await expect(inspector.getByRole('heading', { name: 'Source identity and registry' })).toBeVisible();
  await expect(inspector.getByText('Official Statistics, Multilateral')).toBeVisible();
  await expect(inspector.getByText(/Document methodology.*Not assessed by source identity/)).toBeVisible();
  await expect(inspector.getByRole('link', { name: 'Reuse terms' })).toHaveAttribute('href', 'https://www.ilo.org/rights-and-permissions');
});

test('source inspector separates reported license evidence from an unreviewed host denial', async ({ page }) => {
  await openJob(page, { unreviewedHost: true });
  await page.getByRole('tab', { name: /sources/i }).click();
  await page.getByRole('button', { name: /AI adoption and productivity in small firms/ }).click();
  const inspector = page.locator('.evidence-drawer');
  await expect(inspector.getByText('Reported license', { exact: true })).toBeVisible();
  await expect(inspector.getByText('cc-by', { exact: true })).toBeVisible();
  await expect(inspector.getByText('OpenAlex best_oa_location metadata assertion', { exact: true })).toBeVisible();
  await expect(inspector.getByText('denied or unknown', { exact: true })).toBeVisible();
  await expect(inspector.getByText('host_policy_unknown', { exact: true })).toBeVisible();
});

test('source library keeps evidence access separate from a failed full-text attempt', async ({ page }) => {
  await openJob(page);
  await page.getByRole('tab', { name: /sources/i }).click();
  const sourceRow = page.getByRole('button', { name: /AI adoption and productivity in small firms/ });
  await expect(sourceRow.getByText('ABSTRACT-ONLY')).toBeVisible();
  await expect(sourceRow.getByText('HTML · ERROR')).toBeVisible();
  await page.getByLabel('Access or attempt status').selectOption('error');
  await expect(sourceRow).toBeVisible();
  await sourceRow.click();
  const inspector = page.locator('.evidence-drawer');
  await expect(inspector.getByText('Evidence access class', { exact: true })).toBeVisible();
  await expect(inspector.getByText('Short abstract excerpt from scholarly metadata.')).toBeVisible();
  await expect(inspector.getByText('HTML retrieval outcome', { exact: true })).toBeVisible();
  await expect(inspector.getByText('ERROR · timeout', { exact: true })).toBeVisible();
});

test('source inspector separates OpenAlex archived-format availability from retrieval and reuse rights', async ({ page }) => {
  await openJob(page, { openAlexContentAvailability: { pdf: true, grobid_xml: true } });
  await page.getByRole('tab', { name: /sources/i }).click();
  await page.getByRole('button', { name: /AI adoption and productivity in small firms/ }).click();
  const inspector = page.locator('.evidence-drawer');
  await expect(inspector.getByText('OpenAlex archived formats', { exact: true })).toBeVisible();
  await expect(inspector.getByText('PDF available · GROBID TEI available', { exact: true })).toBeVisible();
  await expect(inspector.getByText(/Availability metadata only\. Veda has not downloaded these files/)).toBeVisible();
  await expect(inspector.getByText('Short abstract excerpt from scholarly metadata.', { exact: true })).toBeVisible();
});

test('source inspector exposes JATS rights, parser provenance and exact methods passage', async ({ page }) => {
  await openJob(page, { jatsFullText: true });
  await page.getByRole('tab', { name: /sources/i }).click();
  const sourceRow = page.getByRole('button', { name: /AI adoption and productivity in small firms/ });
  await expect(sourceRow.getByText('LICENSED JATS FULL TEXT')).toBeVisible();
  await sourceRow.click();
  const inspector = page.locator('.evidence-drawer');
  await expect(inspector.getByText('Europe PMC full-text status').locator('..')).toContainText('retrieved');
  await expect(inspector.getByText('PMC1234567', { exact: true })).toBeVisible();
  await expect(inspector.getByText('Article rights decision').locator('..')).toContainText('permitted');
  await expect(inspector.locator('.detail-list > div').filter({ hasText: 'Article license' }).getByText('CC BY 4.0', { exact: true })).toBeVisible();
  await expect(inspector.getByText(/veda_jats jats-v1 · 3 sections · 3 passages · complete · Methods\/Results available/)).toBeVisible();
  await expect(inspector.getByText('Methods > Study design · XML sec[1] p[1]')).toBeVisible();
  await expect(inspector.getByText('Methods: The authors randomized 48 participants to two task conditions.', { exact: true })).toBeVisible();
});

test('source inspector exposes GROBID version and section-aware PDF passage', async ({ page }) => {
  await openJob(page, { grobidFullText: true });
  await page.getByRole('tab', { name: /sources/i }).click();
  await page.getByRole('button', { name: /AI adoption and productivity in small firms/ }).click();
  const drawer = page.locator('.evidence-drawer');
  await expect(drawer.getByText(/GROBID parser.*parsed.*0\.9\.1-abc123/i)).toBeVisible();
  await expect(drawer.getByText(/grobid 0\.9\.1-abc123.*2 sections.*2 passages/i)).toBeVisible();
  await drawer.getByText(/Extracted section headings/).click();
  await expect(drawer.getByText(/methods: Methods · Methods/i)).toBeVisible();
  await expect(drawer.getByText(/TEI Methods \[tei-section-0001\] paragraph 1 sentence 1/)).toBeVisible();
  await expect(drawer.getByText('Participants were randomized to the AI-assisted and control conditions.')).toBeVisible();
});

test('report verification uses question-adaptive sufficiency as the current status', async ({ page }) => {
  await openJob(page, { fullTextEvidence: true, omitAdaptiveRequirementEvidence: true });
  await expect(page.getByRole('tab', { name: /report/i })).toBeVisible({ timeout: 15_000 });
  await page.getByRole('tab', { name: /report/i }).click();
  await expect(page.locator('.report-reader')).toBeVisible();
  const status = page.getByRole('status', { name: 'Question-adaptive evidence sufficiency' });
  await expect(status).toContainText('PRELIMINARY EVIDENCE MAP');
  await expect(status).toContainText('independent_corroboration_not_established');
  await expect(status).toContainText('Human review: not performed');
});

test('versioned job scope and event metrics remain usable in the browser', async ({ page }) => {
  test.setTimeout(60_000);
  await openJob(page);
  await expect(page.getByRole('heading', { name: job.question })).toBeVisible({ timeout: 15_000 });
  await expect(page.locator('.job-scope-chips')).toContainText('India');
  await expect(page.locator('.job-scope-chips')).toContainText('Small firms');
  const claimCount = page.locator('.coverage-rows span').filter({ hasText: 'Passage-linked claims' });
  await expect(claimCount.locator('b')).toHaveText('1');
});

test('session and persisted project evidence reopen after a browser refresh', async ({ page }) => {
  await openJob(page);
  await page.reload();
  await expect(page.locator('.project-grid')).toBeVisible();
  await page.locator('.project-grid').getByRole('button', { name: /AI adoption in small firms/ }).click();
  await page.getByRole('button', { name: /What does evidence say about AI adoption/ }).click();
  await page.getByRole('tab', { name: /report/i }).click();
  await expect(page.getByRole('heading', { name: 'Historical report text withheld', exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Open source S1' })).toBeVisible();
});

test('research plan UI reports model-assisted provider and model provenance', async ({ page }) => {
  await openJob(page, { modelAssistedPlan: true });
  await expect(page.getByText('Model-assisted selection · openrouter · openrouter/free')).toBeVisible();
});

test('pre-dispatch model plan exposes operation, quota, spend and deferred-work limits', async ({ page }) => {
  await openJob(page, { modelExecutionPlan: true });
  const allocation = page.getByRole('region', { name: 'Pre-dispatch model workload plan' });
  await expect(allocation.getByRole('heading', { name: 'Requests and limits' })).toBeVisible();
  await expect(allocation).toContainText('6/7 requests');
  await expect(allocation).toContainText('₹3.50');
  await expect(allocation).toContainText('Global 12 · this user 5');
  await expect(allocation).toContainText('Latency estimate');
  await allocation.getByText(/Inspect operation allocation/).click();
  await expect(allocation).toContainText('deferred: request quota');
});

test('researcher can create a project, start a bounded run, inspect evidence, and export the report', async ({ page }) => {
  // This journey includes two full axe scans and a multi-stage research run; bound it independently of suite contention.
  test.setTimeout(60_000);
  const projectBrief = 'Evaluate whether small firms can adopt AI without excluding rural operators.';
  const runContext = 'For this run, compare rural firms with urban firms and report implementation costs separately.';
  await openJob(page, { projectInitiallyStored: false, fullTextEvidence: true });
  await page.getByRole('button', { name: 'Create your first project' }).click();
  const createDialog = page.getByRole('dialog', { name: 'Create a research project' });
  await createDialog.getByLabel('Project name').fill(project.title);
  await createDialog.getByLabel('Persistent project brief').fill(projectBrief);
  await createDialog.getByRole('button', { name: 'Create project' }).click();
  await expect(page.getByRole('heading', { name: project.title, exact: true })).toBeVisible();

  await page.getByRole('button', { name: 'Start research' }).click();
  const composer = page.locator('.modal-card');
  await expect(composer.getByLabel(/Decision context/)).toHaveValue(projectBrief);
  await expect(composer.getByText(/edits do not change the persistent project brief/i)).toBeVisible();
  await expect(composer.locator('.budget-note')).toContainText('Crossref and OpenAlex');
  await expect(composer.locator('.budget-note')).toContainText('World Bank Data360');
  await expect(composer.locator('.budget-note')).toContainText('when you supply a supported geography');
  await expect(composer.locator('.budget-note')).toContainText('your research question and geography to World Bank Data360');
  await expect(composer.locator('.budget-note')).toContainText('ILOSTAT');
  await expect(composer.locator('.budget-note')).toContainText('Employment questions with an explicitly supplied World geography');
  await expect(composer.locator('.budget-note')).toContainText('Model processing. No model provider is enabled.');
  await expectNoAxeViolations(page, 'project-brief research composer');
  await page.setViewportSize({ width: 360, height: 800 });
  await expectNoHorizontalOverflow(page, 'project-brief research composer');
  await page.setViewportSize({ width: 1280, height: 900 });
  await composer.getByLabel('Research question').fill(job.question);
  await composer.getByLabel(/Decision context/).fill(runContext);
  await composer.getByLabel('Geography').fill('India');
  await composer.getByLabel('Population or industry').fill('Small firms');
  await composer.getByRole('button', { name: 'Start research' }).click();
  await expect(page.getByRole('heading', { name: job.question })).toBeVisible();
  await expect(page.getByText('Deterministic fallback · provider disabled')).toBeVisible();
  await expect(page.getByLabel('Saved decision context').getByText(runContext, { exact: true })).toBeVisible();
  await expect(page.getByLabel('Saved decision context').getByText('India', { exact: true })).toBeVisible();
  await expect(page.getByText('Comparator, outcomes and bias checks')).toBeVisible();
  await expect(page.getByText('No assumptions supplied; none inferred')).toBeVisible();
  await expect(page.getByText('Planning lenses only; these are not provider search filters.')).toBeVisible();
  await expect(page.getByText('Search explicitly for null, negative, conflicting, and alternative findings.')).toBeVisible();
  await page.getByText('When Veda will qualify or abstain').click();
  await expect(page.getByText(/a bounded search with no counterevidence does not show none exists/i)).toBeVisible();
  const planAudit = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa']).analyze();
  expect(planAudit.violations).toEqual([]);
  await page.setViewportSize({ width: 360, height: 800 });
  const planWidth = await page.evaluate(() => document.documentElement.scrollWidth);
  expect(planWidth).toBeLessThanOrEqual(360);
  await page.setViewportSize({ width: 1280, height: 900 });

  await page.getByRole('button', { name: 'Run while open' }).click();
  await expect(page.locator('.job-hero .status-pill')).toContainText(/limitations/i, { timeout: 15_000 });
  await page.getByRole('tab', { name: /evidence/i }).click();
  await page.getByRole('button', { name: /productivity association/ }).click();
  const evidence = page.locator('.evidence-drawer');
  await expect(evidence.getByText('CLAIM EVIDENCE')).toBeVisible();
  await expect(evidence.getByText(source.passages[0].content, { exact: true })).toBeVisible({ timeout: 15_000 });
  await expect(evidence.getByRole('heading', { name: 'Economic evidence facets' })).toBeVisible();
  await expect(evidence.getByText('Productivity', { exact: true })).toBeVisible();
  await evidence.getByRole('button', { name: 'Close evidence inspector' }).click();

  await page.getByRole('tab', { name: /report/i }).click();
  await expect(page.getByRole('button', { name: 'Open source S1' })).toBeVisible();
  await expect(page.getByText('CONDITIONAL IMPLICATIONS')).toBeVisible();
  await expect(page.getByText('collect more evidence', { exact: true })).toBeVisible();
  const downloadPromise = page.waitForEvent('download');
  await page.getByRole('button', { name: /Markdown/ }).click();
  const download = await downloadPromise;
  expect(download.suggestedFilename()).toMatch(/\.md$/);
});

test('paused research resumes and advances in the browser', async ({ page }) => {
  await openJob(page, { initialJobStatus: 'paused' });
  await expect(page.getByRole('button', { name: 'Resume' })).toBeVisible();
  await page.getByRole('button', { name: 'Resume' }).click();
  await expect(page.getByRole('button', { name: 'Resume' })).toHaveCount(0);
  await page.getByRole('button', { name: 'Next step' }).click();
  await expect(page.locator('.job-hero .status-pill')).toContainText(/limitations/i);
  await page.getByRole('tab', { name: /report/i }).click();
  await expect(page.getByRole('heading', { name: 'Historical report text withheld', exact: true })).toBeVisible();
});

test('report and source-inspector screens have no WCAG A/AA axe violations', async ({ page }) => {
  await openReport(page);
  const reportScan = await new AxeBuilder({ page })
    .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
    .analyze();
  expect(reportScan.violations).toEqual([]);

  await page.getByRole('button', { name: 'Open source S1' }).click();
  const inspectorScan = await new AxeBuilder({ page })
    .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
    .analyze();
  expect(inspectorScan.violations).toEqual([]);
});

test('report remains usable at a 360px mobile viewport', async ({ page }) => {
  await page.setViewportSize({ width: 360, height: 800 });
  await openReport(page);
  await expect(page.getByRole('heading', { name: 'Historical report text withheld', exact: true })).toBeInViewport();
  const viewport = await page.evaluate(() => ({
    clientWidth: document.documentElement.clientWidth,
    scrollWidth: document.documentElement.scrollWidth,
  }));
  expect(viewport.scrollWidth).toBeLessThanOrEqual(viewport.clientWidth + 1);
  await page.getByRole('button', { name: 'Open source S1' }).click();
  await expect(page.locator('.evidence-drawer').getByRole('heading', { name: source.title })).toBeVisible();
});

test('expired protected session returns to sign-in and clears the stale local token', async ({ page }) => {
  await installApiFixtures(page, { expiredProjectSession: true });
  await page.goto('/');
  await page.getByRole('button', { name: 'Continue to local workspace' }).click();
  await expect(page.getByRole('heading', { name: /Research that/ })).toBeVisible();
  await expect.poll(() => page.evaluate(() => sessionStorage.getItem('veda_local_session'))).toBeNull();
});

test('local sign-in failure is visible and sign-out removes the persisted session', async ({ page }) => {
  await installApiFixtures(page, { localSignInStatus: 503 });
  await page.goto('/');
  await page.getByRole('button', { name: 'Continue to local workspace' }).click();
  await expect(page.getByText('Local sign-in is disabled. Enable it only for development in the backend environment.')).toBeVisible();
  await expect(page.locator('.signin-page')).toBeVisible();

  await installApiFixtures(page);
  await page.reload();
  await page.getByRole('button', { name: 'Continue to local workspace' }).click();
  await expect(page.locator('.project-grid')).toBeVisible();
  await page.getByTitle('Sign out').click();
  await expect(page.getByRole('button', { name: 'Continue to local workspace' })).toBeVisible();
  await expect.poll(() => page.evaluate(() => sessionStorage.getItem('veda_local_session'))).toBeNull();
});

test('project edit, archive and restore remain available through account data controls', async ({ page }) => {
  await openJob(page);
  await page.locator('.job-view').getByRole('button', { name: project.title }).click();
  const editButton = page.getByRole('button', { name: 'Edit project' });
  await editButton.click();
  const dialog = page.getByRole('dialog', { name: 'Edit research project' });
  await dialog.getByLabel('Project name').fill('AI adoption and firm productivity');
  await dialog.getByLabel('Persistent project brief').fill('Updated scope for the browser lifecycle fixture.');
  await dialog.getByRole('button', { name: 'Save changes' }).click();
  await expect(page.getByRole('heading', { name: 'AI adoption and firm productivity' })).toBeVisible();

  await page.getByRole('button', { name: 'Archive project' }).click();
  await expect(page.getByText('Start with the question that matters.')).toBeVisible();
  await page.getByRole('button', { name: 'Preferences and data' }).click();
  const preferences = page.getByRole('dialog', { name: 'Preferences and data' });
  await expect(preferences.getByText('AI adoption and firm productivity')).toBeVisible();
  await preferences.getByRole('button', { name: 'Restore' }).click();
  await preferences.getByRole('button', { name: 'Close dialog' }).click();
  await expect(page.locator('.project-grid').getByRole('button', { name: /AI adoption and firm productivity/ })).toBeVisible();
});

test('full account export downloads the authenticated Veda data archive', async ({ page }) => {
  await openJob(page);
  await page.getByRole('button', { name: 'Preferences and data' }).click();
  const preferences = page.getByRole('dialog', { name: 'Preferences and data' });
  await expect(preferences.getByText(/Identity-provider records and original HTML\/PDF bytes are not stored or included/)).toBeVisible();
  const downloadEvent = page.waitForEvent('download');
  await preferences.getByRole('button', { name: 'Download full account export' }).click();
  const download = await downloadEvent;
  expect(download.suggestedFilename()).toMatch(/^veda-account-export-\d{4}-\d{2}-\d{2}\.json$/);
});

test('retention settings schedule future archives and restore cancels the purge date', async ({ page }) => {
  await openJob(page);
  await page.getByRole('button', { name: 'Preferences and data' }).click();
  let preferences = page.getByRole('dialog', { name: 'Preferences and data' });
  await preferences.getByLabel('Delete archived projects after').selectOption('30');
  await preferences.getByRole('button', { name: 'Save defaults' }).click();
  await expect(preferences.getByText('Your defaults are saved to your account.')).toBeVisible();
  await preferences.getByRole('button', { name: 'Close dialog' }).click();

  await page.locator('.job-view').getByRole('button', { name: project.title }).click();
  await page.getByRole('button', { name: 'Archive project' }).click();
  await page.getByRole('button', { name: 'Preferences and data' }).click();
  preferences = page.getByRole('dialog', { name: 'Preferences and data' });
  await expect(preferences.getByText(/^Scheduled for deletion/)).toBeVisible();
  await expectNoAxeViolations(page, 'scheduled project retention');
  await preferences.getByRole('button', { name: 'Restore' }).click();
  await expect(preferences.getByText('No archived projects.')).toBeVisible();
});

test('permanent deletion requires the exact archived project title', async ({ page }) => {
  await installApiFixtures(page, { projectInitiallyStored: false, archivedProjectInitiallyStored: true });
  await page.goto('/');
  await page.getByRole('button', { name: 'Continue to local workspace' }).click();
  await page.getByRole('button', { name: 'Preferences and data' }).click();
  const preferences = page.getByRole('dialog', { name: 'Preferences and data' });
  const deleteButton = preferences.getByRole('button', { name: 'Delete permanently' });
  await deleteButton.click();
  await expect(preferences.getByText(/Deletion is unavailable while a research step is still running/)).toBeVisible();
  const confirmation = preferences.getByLabel(`Type ${project.title} to confirm deletion`);
  await confirmation.fill('wrong project');
  const permanentlyDelete = preferences.getByRole('button', { name: 'Permanently delete' });
  await expect(permanentlyDelete).toBeDisabled();
  await expectNoAxeViolations(page, 'permanent-delete confirmation');
  await confirmation.fill(project.title);
  await expect(permanentlyDelete).toBeEnabled();
  await permanentlyDelete.click();
  await expect(preferences.getByText('No archived projects.')).toBeVisible();
});

test('Veda data deletion requires its distinct phrase and discloses retained sign-in and quota controls', async ({ page }) => {
  await installApiFixtures(page);
  await page.goto('/');
  await page.getByRole('button', { name: 'Continue to local workspace' }).click();
  await page.getByRole('button', { name: 'Preferences and data' }).click();
  const preferences = page.getByRole('dialog', { name: 'Preferences and data' });
  await expect(preferences.getByText(/does not remove your sign-in account/)).toBeVisible();
  await expect(preferences.getByText(/current UTC day's quota safety counter are not deleted/)).toBeVisible();

  await preferences.getByRole('button', { name: 'Delete all Veda data' }).click();
  const confirmation = preferences.getByLabel('Type DELETE VEDA DATA to confirm');
  const deleteButton = preferences.getByRole('button', { name: 'Permanently delete Veda data' });
  await confirmation.fill('DELETE');
  await expect(deleteButton).toBeDisabled();
  await confirmation.fill('DELETE VEDA DATA');
  await expect(deleteButton).toBeEnabled();
  await deleteButton.click();

  await expect(preferences.getByRole('status')).toContainText('Deleted 1 Veda project(s).');
  await expect(preferences.getByRole('status')).toContainText('your sign-in account remains active');
  await expect(preferences.getByText('No archived projects.')).toBeVisible();
  await expectNoAxeViolations(page, 'Veda data deletion confirmation and result');
});

test('conversation history paginates and a follow-up preserves parent evidence provenance', async ({ page }) => {
  await openJob(page, { seedConversation: true });
  await page.getByRole('tab', { name: /conversation/i }).click();
  const history = page.locator('.conversation-history');
  await expect(history.getByRole('heading', { name: 'Research history' })).toBeVisible();
  await expect(history.getByText(job.question)).toBeVisible();
  await history.getByRole('button', { name: 'Load older messages' }).click();
  await expect(history.getByText('Earlier update: discovery was bounded to the available scholarly providers.')).toBeVisible();

  await page.getByRole('button', { name: 'Follow up' }).click();
  const composer = page.getByRole('dialog', { name: 'Continue this research' });
  await expect(composer.getByLabel(/Decision context/)).toHaveValue(project.description);
  await expect(composer.getByText(/do not change the persistent project brief/i)).toBeVisible();
  await composer.getByLabel('Research question').fill('What new evidence changes the productivity association?');
  await composer.getByRole('button', { name: 'Start follow-up' }).click();
  await expect(page.getByRole('heading', { name: 'What new evidence changes the productivity association?' })).toBeVisible();
  await page.getByRole('tab', { name: 'overview' }).click();
  await expect(page.getByLabel('Saved decision context').getByText(project.description, { exact: true })).toBeVisible();
  await page.getByRole('tab', { name: /conversation/i }).click();
  const context = page.locator('.follow-up-context-card');
  await expect(context.getByRole('heading', { name: 'What informed this follow-up' })).toBeVisible();
  await expect(context.getByText(job.question)).toBeVisible();
  await expect(context.getByText(source.passages[0].locator)).toBeVisible();
  await context.getByRole('button', { name: 'Inspect parent passage' }).click();
  await expect(page.locator('.evidence-drawer').getByText('CLAIM EVIDENCE')).toBeVisible();
});

test('comparison relationships and both hypotheses link into the evidence inspector', async ({ page }) => {
  await openJob(page, { withComparisons: true });
  await page.getByRole('tab', { name: /compare/i }).click();
  const panel = page.locator('.comparison-panel');
  await expect(panel.getByRole('heading', { name: 'How stored claims compare' })).toBeVisible();
  await expect(panel.getByText('Scope differences', { exact: true })).toBeVisible();
  await expect(panel.getByText('AI adoption may improve productivity when firms can reorganize workflows.')).toBeVisible();
  await expect(panel.getByText('Measured productivity gains may reflect selection of already capable firms.')).toBeVisible();
  await panel.locator('.comparison-evidence').first().focus();
  await page.keyboard.press('Enter');
  await expect(page.locator('.evidence-drawer').getByText('CLAIM EVIDENCE')).toBeVisible();
});

test('edit dialog traps keyboard focus and restores it to its opener', async ({ page }) => {
  await openJob(page);
  await page.locator('.job-view').getByRole('button', { name: project.title }).click();
  const editButton = page.getByRole('button', { name: 'Edit project' });
  await editButton.click();
  const dialog = page.getByRole('dialog', { name: 'Edit research project' });
  const nameField = dialog.getByLabel('Project name');
  const closeDialog = dialog.getByRole('button', { name: 'Close dialog' });
  await expect(nameField).toBeFocused();
  await page.keyboard.press('Shift+Tab');
  await expect(closeDialog).toBeFocused();
  await page.keyboard.press('Shift+Tab');
  await expect(dialog.getByRole('button', { name: 'Save changes' })).toBeFocused();
  await page.keyboard.press('Tab');
  await expect(closeDialog).toBeFocused();
  await page.keyboard.press('Escape');
  await expect(dialog).toHaveCount(0);
  await expect(editButton).toBeFocused();
});

test('comparison inspection is accessible and fits a narrow viewport', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await openJob(page, { withComparisons: true });
  await page.getByRole('tab', { name: /compare/i }).click();
  const viewport = await page.evaluate(() => ({ clientWidth: document.documentElement.clientWidth, scrollWidth: document.documentElement.scrollWidth }));
  expect(viewport.scrollWidth).toBeLessThanOrEqual(viewport.clientWidth + 1);
  const scan = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa']).analyze();
  expect(scan.violations).toEqual([]);
});

test('dashboard, project history, create/edit and archived-project dialogs pass axe on mobile', async ({ page }) => {
  await page.setViewportSize({ width: 360, height: 800 });
  await installApiFixtures(page, { archivedProjectInitiallyStored: true, seedConversation: true });
  await page.goto('/');
  await page.getByRole('button', { name: 'Continue to local workspace' }).click();
  await expect(page.locator('.project-grid')).toBeVisible();
  await expectNoAxeViolations(page, 'dashboard');

  const dashboardWidth = await page.evaluate(() => ({ client: document.documentElement.clientWidth, scroll: document.documentElement.scrollWidth }));
  expect(dashboardWidth.scroll).toBeLessThanOrEqual(dashboardWidth.client + 1);
  await page.locator('.section-actions').getByRole('button', { name: 'New project' }).click();
  const createDialog = page.getByRole('dialog', { name: 'Create a research project' });
  await expect(createDialog.getByLabel('Project name')).toBeFocused();
  await expectNoAxeViolations(page, 'create project dialog');
  await page.keyboard.press('Escape');

  await page.locator('.project-grid').getByRole('button', { name: /AI adoption in small firms/ }).click();
  await expect(page.locator('.project-view')).toBeVisible();
  await expectNoHorizontalOverflow(page, 'project run and conversation history');
  await expectNoAxeViolations(page, 'project and run history');
  await page.getByRole('button', { name: 'Edit project' }).click();
  const editDialog = page.getByRole('dialog', { name: 'Edit research project' });
  await expect(editDialog.getByLabel('Project name')).toBeFocused();
  await expectNoAxeViolations(page, 'edit project dialog');
  await expectNoHorizontalOverflow(page, 'edit project dialog');
  await page.keyboard.press('Escape');
  await expect(page.getByRole('button', { name: 'Edit project' })).toBeFocused();

  await page.getByRole('button', { name: 'Preferences and data' }).click();
  const archivedDialog = page.getByRole('dialog', { name: 'Preferences and data' });
  await expect(archivedDialog.getByText(project.title)).toBeVisible();
  await expectNoAxeViolations(page, 'archived project history dialog');
  await expectNoHorizontalOverflow(page, 'archived project history dialog');
  await page.keyboard.press('Escape');
});

test('empty dashboard and first-project dialog pass axe and mobile keyboard checks', async ({ page }) => {
  await page.setViewportSize({ width: 360, height: 800 });
  await openJob(page, { projectInitiallyStored: false });
  await expect(page.locator('.empty-state')).toBeVisible();
  await expectNoAxeViolations(page, 'empty dashboard');
  await expectNoHorizontalOverflow(page, 'empty dashboard');
  const createButton = page.getByRole('button', { name: 'Create your first project' });
  await createButton.click();
  const dialog = page.getByRole('dialog', { name: 'Create a research project' });
  await expect(dialog.getByLabel('Project name')).toBeFocused();
  await expectNoAxeViolations(page, 'first-project dialog');
  await expectNoHorizontalOverflow(page, 'first-project dialog');
  await page.keyboard.press('Escape');
  await expect(createButton).toBeFocused();
});

test('conversation and both research composers pass axe with keyboard and narrow-screen checks', async ({ page }) => {
  await page.setViewportSize({ width: 360, height: 800 });
  await openJob(page, { seedConversation: true });
  await page.getByRole('tab', { name: /conversation/i }).click();
  await expectNoAxeViolations(page, 'conversation history');
  const conversationWidth = await page.evaluate(() => ({ client: document.documentElement.clientWidth, scroll: document.documentElement.scrollWidth }));
  expect(conversationWidth.scroll).toBeLessThanOrEqual(conversationWidth.client + 1);

  const followUpButton = page.getByRole('button', { name: 'Follow up' });
  await followUpButton.click();
  const followUpDialog = page.getByRole('dialog', { name: 'Continue this research' });
  await expect(followUpDialog.getByLabel('Research question')).toBeFocused();
  await expect(followUpDialog.locator('.budget-note')).toContainText('Crossref and OpenAlex');
  await expect(followUpDialog.locator('.budget-note')).toContainText('World Bank Data360');
  await expect(followUpDialog.locator('.budget-note')).toContainText('when you supply a supported geography');
  await expect(followUpDialog.locator('.budget-note')).toContainText('your research question and geography to World Bank Data360');
  await expect(followUpDialog.locator('.budget-note')).toContainText('ILOSTAT');
  await expect(followUpDialog.locator('.budget-note')).toContainText('Employment questions with an explicitly supplied World geography');
  await expect(followUpDialog.locator('.budget-note')).toContainText('Model processing. No model provider is enabled.');
  await expectNoAxeViolations(page, 'follow-up research composer');
  await page.keyboard.press('Escape');
  await expect(followUpButton).toBeFocused();

  await page.locator('.job-view').getByRole('button', { name: project.title }).click();
  await page.getByRole('button', { name: 'Start research' }).click();
  const composer = page.getByRole('dialog', { name: 'Shape your research question' });
  await expect(composer.getByLabel('Research question')).toBeFocused();
  await expectNoAxeViolations(page, 'new research composer');
  await expectNoHorizontalOverflow(page, 'new research composer');
  await page.keyboard.press('Escape');
});

test('research composer does not describe an unready model provider as enabled for requests', async ({ page }) => {
  await openJob(page, {
    providerStatus: {
      active_provider: 'openrouter',
      provider_ready: false,
      model: 'openrouter/free',
      paid_calls_allowed: false,
    },
  });
  await page.getByRole('button', { name: 'Follow up' }).click();
  const disclosure = page.locator('.budget-note');
  await expect(disclosure).toContainText('The selected provider is not ready.');
  await expect(disclosure).toContainText('this server will not send a model request');
  await expect(disclosure).not.toContainText('The server may send your question');
});

test('AI relevance review is off by default and persisted only after explicit opt-in', async ({ page }) => {
  await openJob(page, {
    providerStatus: {
      active_provider: 'openrouter',
      provider_ready: true,
      model: 'openrouter/free',
      paid_calls_allowed: false,
    },
  });
  await page.locator('.job-view').getByRole('button', { name: project.title }).click();
  await page.getByRole('button', { name: 'Start research' }).click();
  const composer = page.getByRole('dialog', { name: 'Shape your research question' });
  const optIn = composer.getByRole('checkbox', { name: /Use AI-assisted source relevance review/ });
  await expect(optIn).toBeEnabled();
  await expect(optIn).not.toBeChecked();

  let submittedPayload: Record<string, unknown> | undefined;
  page.on('request', (request) => {
    if (
      request.method() === 'POST' &&
      new URL(request.url()).pathname === `/api/v1/projects/${project.id}/research-jobs`
    ) {
      submittedPayload = request.postDataJSON() as Record<string, unknown>;
    }
  });
  await composer.getByLabel('Research question').fill('Does a bounded evidence review recover relevant literature?');
  await optIn.check();
  await composer.getByRole('button', { name: 'Start research' }).click();
  await expect(page.getByRole('heading', { name: 'Does a bounded evidence review recover relevant literature?' })).toBeVisible();
  expect(submittedPayload?.ai_assisted_relevance).toBe(true);
});

test('claim and source evidence inspectors pass axe and stay within a narrow viewport', async ({ page }) => {
  await page.setViewportSize({ width: 360, height: 800 });
  await openJob(page, { fullTextEvidence: true });
  await page.getByRole('tab', { name: /evidence/i }).click();
  const claimTrigger = page.getByRole('button', { name: /productivity association/ });
  await claimTrigger.click();
  const claimInspector = page.locator('.evidence-drawer');
  await expect(claimInspector.getByRole('heading', { name: /productivity association/ })).toBeVisible();
  await expect(claimInspector.getByRole('heading', { name: 'Methodological relationship' })).toBeVisible();
  await expect(claimInspector.getByText('qualifies', { exact: true })).toBeVisible();
  await expect(claimInspector.getByText('The study design supports an association claim but does not identify a causal effect.')).toBeVisible();
  await expect(claimInspector.locator('.methodology-passage').getByText(source.passages[0].locator, { exact: true })).toBeVisible();
  await expect(claimInspector.getByRole('button', { name: 'Close evidence inspector' })).toBeFocused();
  await expectNoAxeViolations(page, 'claim evidence inspector');
  let viewport = await page.evaluate(() => ({ client: document.documentElement.clientWidth, scroll: document.documentElement.scrollWidth }));
  expect(viewport.scroll).toBeLessThanOrEqual(viewport.client + 1);
  await page.keyboard.press('Escape');
  await expect(claimInspector).toHaveCount(0);
  await expect(claimTrigger).toBeFocused();

  await page.getByRole('tab', { name: /sources/i }).click();
  const sourceTrigger = page.getByRole('button', { name: /AI adoption and productivity in small firms/ });
  await sourceTrigger.click();
  const sourceInspector = page.locator('.evidence-drawer');
  await expect(sourceInspector.getByRole('heading', { name: source.title })).toBeVisible();
  await expect(sourceInspector.getByRole('button', { name: 'Close source inspector' })).toBeFocused();
  await expectNoAxeViolations(page, 'source evidence inspector');
  viewport = await page.evaluate(() => ({ client: document.documentElement.clientWidth, scroll: document.documentElement.scrollWidth }));
  expect(viewport.scroll).toBeLessThanOrEqual(viewport.client + 1);
  await page.keyboard.press('Escape');
  await expect(sourceInspector).toHaveCount(0);
  await expect(sourceTrigger).toBeFocused();
});

test('dashboard search announces no matches and restores projects when the query is cleared', async ({ page }) => {
  await page.setViewportSize({ width: 360, height: 800 });
  await installApiFixtures(page);
  await page.goto('/');
  await page.getByRole('button', { name: 'Continue to local workspace' }).click();
  const search = page.getByRole('textbox', { name: 'Search projects' });
  await search.fill('no project has this phrase');
  await expect(page.getByRole('status').getByRole('heading', { name: 'No matching projects' })).toBeVisible();
  await expectNoAxeViolations(page, 'dashboard search no-match status');
  await expectNoHorizontalOverflow(page, 'dashboard search no-match status');
  await search.clear();
  await expect(page.locator('.project-grid').getByRole('button', { name: /AI adoption in small firms/ })).toBeVisible();
});

test('dashboard refresh exposes its loading state while the project list request is pending', async ({ page }) => {
  await installApiFixtures(page, { projectListDelayMs: 450, projectListDelayAfterFirst: true });
  await page.goto('/');
  await page.getByRole('button', { name: 'Continue to local workspace' }).click();
  await expect(page.locator('.project-grid')).toBeVisible();
  await page.getByRole('button', { name: 'Refresh projects' }).click();
  await expect(page.getByText('Opening your workspace…')).toBeVisible();
  await expect(page.locator('.project-grid').getByRole('button', { name: /AI adoption in small firms/ })).toBeVisible();
});

test('dashboard project-list failure is visible and can be retried', async ({ page }) => {
  await page.setViewportSize({ width: 360, height: 800 });
  const fixture = await installApiFixtures(page, {
    projectListFailureOnce: true,
    projectListFailureRequestId: 'project-list-failure-123',
  });
  await page.goto('/');
  await page.getByRole('button', { name: 'Continue to local workspace' }).click();
  const error = page.getByRole('alert');
  await expect(error).toContainText('Project service temporarily unavailable.');
  await expect(error).toContainText('Reference ID: project-list-failure-123');
  await expect(page.getByText('Project availability is unknown until the list can be refreshed.')).toBeVisible();
  await expectNoAxeViolations(page, 'dashboard project-list error and retry');
  await expectNoHorizontalOverflow(page, 'dashboard project-list error and retry');
  const initialRequests = fixture.projectListRequestCounter.count;
  await page.getByRole('button', { name: 'Retry project loading' }).click();
  await expect.poll(() => fixture.projectListRequestCounter.count).toBeGreaterThan(initialRequests);
  await expect(page.locator('.project-grid').getByRole('button', { name: /AI adoption in small firms/ })).toBeVisible();
  await expect(page.getByRole('alert')).toHaveCount(0);
});

test('project conversation and run history failures remain distinct and can be retried', async ({ page }) => {
  await page.setViewportSize({ width: 360, height: 800 });
  await openProject(page, { seedConversation: true, projectHistoryFailures: 'both' });
  const recovery = page.getByRole('alert');
  await expect(recovery).toContainText('Conversations: Conversation history is temporarily unavailable.');
  await expect(recovery).toContainText('Research runs: Research-run history is temporarily unavailable.');
  await expectNoAxeViolations(page, 'project history failure and recovery controls');
  await expectNoHorizontalOverflow(page, 'project history failure and recovery controls');
  await page.getByRole('button', { name: 'Retry project history' }).click();
  await expect(page.locator('.job-list').getByRole('button', { name: /What does evidence say about AI adoption/ })).toBeVisible();
  await expect(page.locator('.conversation-list').getByRole('button', { name: /What does evidence say about AI adoption/ })).toBeVisible();
  await expect(page.getByRole('alert')).toHaveCount(0);
});

test('a research-run history failure does not hide successfully loaded conversations', async ({ page }) => {
  await openProject(page, { seedConversation: true, projectHistoryFailures: 'jobs' });
  await expect(page.getByRole('alert')).toContainText('Research runs: Research-run history is temporarily unavailable.');
  await expect(page.getByRole('alert')).not.toContainText('Conversations:');
  await expect(page.locator('.conversation-list').getByRole('button', { name: /What does evidence say about AI adoption/ })).toBeVisible();
  await page.getByRole('button', { name: 'Retry project history' }).click();
  await expect(page.locator('.job-list').getByRole('button', { name: /What does evidence say about AI adoption/ })).toBeVisible();
  await expect(page.getByRole('alert')).toHaveCount(0);
});

test('a conversation-history failure does not hide successfully loaded research runs', async ({ page }) => {
  await openProject(page, { seedConversation: true, projectHistoryFailures: 'conversations' });
  await expect(page.getByRole('alert')).toContainText('Conversations: Conversation history is temporarily unavailable.');
  await expect(page.getByRole('alert')).not.toContainText('Research runs:');
  await expect(page.locator('.job-list').getByRole('button', { name: /What does evidence say about AI adoption/ })).toBeVisible();
  await page.getByRole('button', { name: 'Retry project history' }).click();
  await expect(page.locator('.conversation-list').getByRole('button', { name: /What does evidence say about AI adoption/ })).toBeVisible();
  await expect(page.getByRole('alert')).toHaveCount(0);
});

test('project history exposes loading while its conversations and run requests are pending', async ({ page }) => {
  await openProject(page, { projectHistoryDelayMs: 450 });
  await expect(page.getByText('Loading project history…')).toBeVisible();
  await expect(page.locator('.job-list').getByRole('button', { name: /What does evidence say about AI adoption/ })).toBeVisible();
});

test('empty project history is stated without implying a failed request', async ({ page }) => {
  await page.setViewportSize({ width: 360, height: 800 });
  await openProject(page, { emptyProjectHistory: true });
  await expect(page.locator('.history-empty')).toContainText('Research runs you start here will stay attached to this project.');
  await expect(page.getByRole('alert')).toHaveCount(0);
  await expectNoAxeViolations(page, 'empty project history');
  await expectNoHorizontalOverflow(page, 'empty project history');
});
