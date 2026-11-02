export type Project = {
  id: string;
  title: string;
  description: string;
  domain: string;
  archived_at: string | null;
  purge_at: string | null;
  created_at: string;
  updated_at: string;
};

export type ResearchJob = {
  schema_version?: 1;
  id: string;
  project_id: string;
  parent_job_id: string | null;
  conversation_id: string | null;
  question: string;
  scope: {
    schema_version?: 1;
    context?: string | null;
    geography?: string | null;
    population?: string | null;
    time_horizon?: string | null;
    decision_objective?: string | null;
    comparator?: string | null;
    target_outcome?: string | null;
    denominator?: string | null;
    assumptions_to_test?: string | null;
    extensions?: Record<string, unknown>;
    [key: string]: string | number | null | undefined | Record<string, unknown>;
  };
  depth: 'quick' | 'standard' | 'deep';
  model_provider?: string | null;
  model_name?: string | null;
  budget_ceiling_usd: number;
  budget_ceiling_inr: number;
  cost_spent_estimate_inr: number;
  cost_reserved_inr: number;
  cost_spent_estimate_usd: number;
  unknown_cost_calls?: number | null;
  cost_estimate_complete?: boolean;
  cost_reserved_usd: number;
  model_calls_reserved: number;
  prompt_characters_reserved: number;
  prompt_token_budget_reserved: number;
  output_token_budget_reserved: number;
  resource_limits: DepthProfile;
  status: string;
  current_stage: string;
  version: number;
  attempt: number;
  error_class: string | null;
  error_message: string | null;
  created_at: string;
  updated_at: string;
};

export type DepthProfile = {
  name: 'quick' | 'standard' | 'deep';
  max_queries: number;
  max_records_per_provider_query: number;
  max_sources: number;
  max_html_pages: number;
  max_pdf_documents: number;
  max_html_passages: number;
  max_passages: number;
  max_model_calls: number;
  max_prompt_characters_per_call: number;
  max_prompt_characters_total: number;
  max_prompt_tokens_per_call: number;
  max_prompt_token_budget_total: number;
  max_output_tokens_per_call: number;
  max_output_token_budget_total: number;
  max_retries: number;
  max_step_seconds: number;
};

export type UserPreferences = {
  default_depth: DepthProfile['name'];
  default_budget_ceiling_usd: number;
  retention_days: 30 | 90 | 365 | null;
  is_customized: boolean;
  updated_at: string | null;
};

export type DataLifecycle = {
  report_exports: { status: string; formats: Array<'markdown' | 'json'>; scope: string };
  project_archive: { status: string; effect: string; restore_supported: boolean };
  project_permanent_deletion: { status: string; detail: string };
  full_account_export: { status: string; alternative: string };
  account_deletion: { status: string; detail: string };
  veda_data_deletion: {
    status: string;
    endpoint: string;
    confirmation_phrase: 'DELETE VEDA DATA';
    detail: string;
  };
  retention: { status: string; detail: string };
};

export type VedaDataPurgeResult = {
  deleted_projects: number;
  deleted_preferences: boolean;
  daily_quota_counters_preserved_until_utc_date: string;
  identity_provider_account_deleted: false;
};

export type JobEvent = {
  schema_version?: 1;
  id: string;
  event_type: string;
  stage: string | null;
  message: string;
  data: Record<string, unknown> & { data_schema_version?: 1 };
  created_at: string;
};

export type ResearchPlan = {
  version: number;
  schema_version?: number;
  planning_mode?: string;
  planning_provenance?: {
    status: 'model_selection_applied' | 'deterministic_fallback';
    provider: 'openrouter' | 'openai' | null;
    model: string | null;
    fallback_reason: string | null;
  };
  decision_context?: {
    decision_objective: string | null;
    context: string | null;
    population: string | null;
    geography: string | null;
    time_horizon: string | null;
  };
  planning_lenses?: {
    comparator_or_counterfactual: {
      status: 'specified' | 'unspecified';
      user_statement: string | null;
      prompt: string;
    };
    outcomes: {
      status: 'specified' | 'partially_specified' | 'unspecified';
      target_outcome: string | null;
      denominator: string | null;
      possible_outcomes_prompt: string;
      denominator_prompt: string;
    };
    assumptions: {
      status: 'user_supplied' | 'not_provided';
      user_supplied_text: string | null;
      system_inferred_assumptions: string[];
    };
    confounding: {
      applicability: 'evaluate_if_nonrandomized_or_observational_evidence';
      considerations: string[];
      prompt: string;
    };
    evidence_types: {
      types_to_consider: string[];
      mode: 'planning_lenses_only_not_provider_filters';
      provider_type_filter_applied: false;
    };
  };
  scope_status?: 'specified' | 'underspecified';
  missing_scope_fields?: string[];
  scope_notice?: string;
  queries: string[];
  query_rationales?: { query: string; purpose: string; focus: string }[];
  subquestions: { text: string; purpose: string }[];
  stopping_criteria?: {
    execution: string;
    insufficient_evidence: string;
    incomparability: string;
    counterevidence: string;
  };
  resource_limits?: DepthProfile;
};

export type OfficialStatisticsMetadata = {
  indicator_id: string;
  indicator_name: string;
  database_id: string;
  dataset_name: string;
  dataset_url: string;
  dataset_terms_url: string;
  license: string | null;
  license_url: string | null;
  attribution: string;
  definition: string | null;
  statistical_concept: string | null;
  methodology: string | null;
  limitations: string | null;
  periodicity: string | null;
  source_update_date: string | null;
  measurement_unit: string | null;
  retrieved_at: string;
  data_sources: { name: string | null; organization: string | null; publisher: string | null; url: string | null }[];
  observations: {
    value: string;
    period: string;
    geography_code: string;
    geography_name: string;
    unit_measure: string | null;
    unit_type: string | null;
    unit_multiplier: number | null;
    observation_status: string | null;
  }[];
};

export type AppraisalValue = {
  value: string;
  passage_ids: string[];
  status: string;
};

export type SourceMethodologicalAppraisal = {
  schema_version?: number;
  status?: string;
  reason?: string | null;
  provider?: string | null;
  model?: string | null;
  fields?: Record<string, AppraisalValue>;
  extensions?: Record<string, unknown>;
};

export type ClaimMethodologyAppraisal = {
  schema_version?: number;
  status: string;
  relationship: 'supports' | 'qualifies' | 'contradicts' | 'insufficient' | string;
  rationale: string;
  passage_ids: string[];
  provider?: string | null;
  model?: string | null;
  extensions?: Record<string, unknown>;
};

export type ClaimAppraisal = {
  schema_version?: number;
  extraction?: string | null;
  methodology_appraisal?: ClaimMethodologyAppraisal | null;
  economic_facets?: unknown;
  extensions?: Record<string, unknown>;
};

export type Source = {
  id: string;
  title: string;
  doi: string | null;
  url: string | null;
  authors: { given?: string; family?: string; name?: string }[];
  published_year: number | null;
  publisher: string | null;
  provider: string;
  provider_metadata_schema_version?: number | null;
  source_governance?: {
    registry_version: string;
    source_classes: string[];
    matched_registry_ids: string[];
    matched_identity_provenance: { registry_id: string; source_url: string; verified_at: string }[];
    matched_institution_identifiers: { registry_id: string; namespace: string; identifier: string }[];
    matched_organization_identifiers: { registry_id: string; namespace: string; identifier: string }[];
    identity_status: 'verified' | 'unverified' | 'unregistered';
    quality_review_status: 'not_assessed' | 'review_pending' | 'reviewed';
    methodological_quality: 'not_assessed';
    methodology_review_required: boolean;
    academic_preference: 'QS_TOP_100' | 'QS_101_250_ELIGIBLE' | 'Q1' | 'FT50' | 'NONE';
    quality_claim_is_truth_claim: false;
    matched_institution_rankings: { canonical_id: string; system: string; ranking_year: number; rank: number; subject_category: string }[];
    matched_journal_classifications: { registry_id: string; issn: string; classification: 'Q1' | 'FT50'; system: string; ranking_year: number; subject_category?: string | null }[];
    unverified_classification_count: number;
    discovery_status: string;
    selection_guidance: string;
    counterevidence_exception: boolean;
  } | null;
  organization_provenance?: {
    organization_id: string;
    organization_name: string;
    identity_status: string;
    verification_method: string;
    verification_source: string | null;
    openalex_institution_id: string | null;
    quality_assessment: 'not_assessed';
    publisher_verification?: string;
    official_domain?: string | null;
    publisher_linked_domain?: string;
    official_publication_url?: string;
    publication_discovery_provider?: string;
    publication_content_access?: 'not_retrieved' | 'full_text_html' | 'full_text_pdf' | 'full_text_jats';
    publication_rights_status?: 'metadata_only_not_assessed' | 'permitted';
  } | null;
  openalex_fulltext_availability?: { pdf?: boolean | null; grobid_xml?: boolean | null } | null;
  institutional_publication?: {
    publisher_record_id: string;
    document_type: string | null;
    report_number: string | null;
    metadata_access: 'public_official_api';
    metadata_reuse_rights_status: 'not_assessed';
    full_text_retrieved: false;
    full_text_rights_status: 'not_assessed';
  } | null;
  official_publication?: {
    provider: 'GOV.UK Search API';
    record_path: string;
    document_type: 'policy_paper';
    publishing_organizations: string[];
    publishing_organization_records: VerifiedGovernmentOrganization[];
    metadata_access: 'public_official_api';
    metadata_reuse_status: 'metadata_only_content_rights_not_assessed';
    api_support_status: 'unsupported_best_effort';
    full_text_retrieved: false;
    full_text_rights_status: 'not_assessed';
  } | null;
  official_site_publication?: {
    organization_id: string;
    organization_name: string;
    identity_status: 'VERIFIED_ESTABLISHED' | 'VERIFIED_DOMAIN_SPECIALIST';
    verification_source: string | null;
    official_domain: string | null;
    homepage_url: string;
    api_url: string;
    discovery_query: string;
    wordpress_record_id: number;
    result_type: 'post';
    result_subtype: string;
    metadata_access: 'public_official_site_search_api';
    content_fetched: false;
    rights_status: 'not_assessed';
    quality_assessment: 'not_assessed';
    publisher_verification:
      | 'official_domain_linked_from_ror_verified_site'
      | 'crossref_doi_title_publisher_and_link_domain_match'
      | 'verified_organization_domain_and_catalog_record_match';
  } | null;
  source_type: string;
  statistics?: OfficialStatisticsMetadata | null;
  retrieval_status: string;
  retrieval?: {
    govuk_content?: {
      status?: string;
      access_class?: 'official_publication_page_body';
      api_url?: string;
      publication_url?: string;
      retrieved_at?: string;
      public_updated_at?: string | null;
      document_id?: string;
      document_sha256?: string;
      passage_count?: number;
      passage_limit?: number;
      paragraphs_truncated?: boolean;
      overlength_or_fragment_sentences_skipped?: number;
      license_code?: string;
      license_url?: string;
      rights_status?: string;
      rights_limit?: string;
      attachments_fetched?: false;
      error_code?: string;
      request_dispatched?: boolean;
    };
    outcomes?: {
      schema_version: number;
      by_format?: Partial<Record<'html' | 'pdf' | 'jats', {
        schema_version: number;
        format: 'html' | 'pdf' | 'jats';
        outcome: 'not_attempted' | 'retrieved' | 'partial' | 'unavailable' | 'error' | 'deferred';
        observed_at?: string;
        reason_code?: string;
        error_code?: string;
        retry_after_seconds?: number;
        truncated?: boolean;
      }>>;
    };
    status?: string;
    scope?: string;
    rights_decision?: string;
    rights_basis?: string;
    rights_assessment?: {
      discovery?: string;
      access?: string;
      analysis?: string;
      retention?: string;
      sharing?: string;
      basis?: string;
      policy_version?: string;
      legal_review_required?: boolean;
      max_retained_verbatim_characters?: number | null;
      max_retained_passages?: number | null;
      robots_status?: string;
      site_terms_status?: string;
      terms_url?: string | null;
      reason_codes?: string[];
      warnings?: string[];
    };
    official_page_content?: {
      status?: string;
      reason_code?: string;
      rights_status?: string;
      content_retained?: boolean;
    };
    openaire_resolution?: {
      status?: string;
      reason?: string;
      error_code?: string;
      query?: string;
      request_dispatched?: boolean;
      result_count?: number;
      matched_doi?: string | null;
      matched_title?: string | null;
      license_code?: string;
      selected_url?: string;
      repository_name?: string | null;
      repository_url?: string | null;
      license_url?: string;
      content_version?: string | null;
      retrieved_at?: string;
      retry_after_seconds?: number;
    };
    license?: string | null;
    license_evidence?: string;
    site_policy_status?: string;
    host_policy_id?: string;
    host_terms_url?: string;
    robots_status?: string;
    version?: string | null;
    media_type?: string;
    document_sha256?: string;
    final_host?: string;
    retrieved_at?: string;
    truncated?: boolean;
    page_count?: number | null;
    pages_extracted?: number;
    ocr_performed?: boolean;
    jats?: {
      status?: string;
      reason?: string;
      pmcid?: string;
      doi?: string | null;
      raw_license?: string | null;
      license?: string | null;
      open_access?: boolean | null;
      rights_decision?: string;
      document_sha256?: string;
      retrieved_at?: string;
      sections_count?: number;
      passages_count?: number;
      methods_results_usable?: boolean;
      extraction_status?: string;
    };
    structured_document?: {
      schema_version?: number;
      document_id?: string;
      representation_format?: string;
      parser_name?: string;
      parser_version?: string;
      extraction_status?: string;
      methods_results_usable?: boolean;
      sections_count?: number;
      passages_count?: number;
      rights_decision?: string;
      document_sha256?: string;
      structured_content_sha256?: string;
      extraction_warnings?: string[];
      sections?: {
        section_id: string;
        original_heading: string;
        normalized_type: string;
        section_path: string[];
        ordinal: number;
        source_locator: string;
      }[];
      section_metadata_truncated?: boolean;
    };
    grobid?: {
      status?: string;
      error_code?: string;
      parser_version?: string;
    };
    error_code?: string;
    reason?: string;
    pdf_available?: boolean;
    deferred_retries?: Partial<Record<'html' | 'pdf' | 'jats', {
      status?: 'pending' | 'scheduled' | 'completed' | 'failed';
      due_at?: string;
      retry_after_seconds?: number;
      continuation_job_id?: string;
      scheduled_at?: string;
      last_attempt_at?: string;
      error_code?: string;
    }>>;
    pdf?: {
      status?: string;
      error_code?: string;
      site_policy_status?: string;
      host_policy_id?: string;
      host_terms_url?: string;
      robots_status?: string;
    };
  };
  abstract_excerpt: string | null;
  abstract_text_available_at_discovery?: boolean | null;
  abstract_text_retention_status?:
    | 'retained_item_license_verified_v1'
    | 'not_available'
    | 'not_retained_item_text_rights_unverified'
    | 'legacy_not_recorded'
    | string
    | null;
  appraisal: SourceMethodologicalAppraisal;
  passages?: Passage[];
};

export type DiscoveryCandidate = {
  id: string;
  provider: string;
  provider_record_id: string;
  canonical_identity: string;
  title: string;
  publisher?: string | null;
  publisher_organizations?: VerifiedGovernmentOrganization[];
  abstract_excerpt?: string | null;
  abstract_excerpt_retention_status?:
    | 'retained_item_license_verified_v1'
    | 'not_available'
    | 'not_retained_item_text_rights_unverified'
    | 'not_retained_rights_unclear'
    | 'retained_openalex_metadata_cc0_v1'
    | 'legacy_not_recorded';
  doi: string | null;
  url: string | null;
  published_year: number | null;
  query: string;
  ranking_order?: number | null;
  relevance_score?: number | null;
  source_governance?: Source['source_governance'];
  relevance?: {
    schema_version: number;
    algorithm: string;
    ranking_query_basis: 'user_research_question';
    score: number;
    score_scale: string;
    query_term_count: number;
    query_terms: string[];
    query_terms_truncated: boolean;
    matched_title_terms: string[];
    matched_abstract_terms: string[];
    title_coverage: number;
    abstract_coverage: number;
    weights: { title_coverage: number; abstract_coverage: number };
    explanation: string;
    planned_query_alignment?: {
      schema_version: number;
      algorithm: string;
      ranking_query_basis: 'recorded_provider_query';
      score: number;
      query_term_count: number;
      query_terms: string[];
      query_terms_truncated: boolean;
      matched_title_terms: string[];
      matched_abstract_terms: string[];
      title_coverage: number;
      abstract_coverage: number;
      weights: { title_coverage: number; abstract_coverage: number };
      explanation: string;
      interpretation_limit: string;
    } | null;
    selection_score?: number | null;
    selection_basis?: 'user_question' | 'recorded_provider_query' | 'tie' | null;
    topic_eligibility_basis?: 'original_question' | 'recorded_query_domain_expansion' | 'not_eligible' | null;
    interpretation_limit: string;
  } | null;
  planned_query_score?: number | null;
  selection_score?: number | null;
  disposition: 'selected' | 'excluded' | string;
  reason_code: string;
  canonical_source_id: string | null;
  discovered_at: string;
};

export type VerifiedGovernmentOrganization = {
  schema_version: 1;
  organization_id: string;
  canonical_name: string;
  content_id: string;
  organization_type: string;
  directory_status: string;
  identity_status: 'VERIFIED_ESTABLISHED' | 'PENDING_VERIFICATION';
  verification_method: 'govuk_organizations_api_exact_slug';
  verification_source: string;
  verification_timestamp: string;
  official_url: string;
  quality_assessment: 'not_assessed';
  limitations: string[];
  publication_ids: string[];
  discovery_result_count: number;
};

export type Passage = {
  id: string;
  source_id: string;
  document_id?: string | null;
  identity_version?: number;
  ordinal: number;
  locator: string;
  content: string;
  content_withheld_reason?: string | null;
  content_hash: string;
  access_level: string;
  truncated: boolean;
  document?: {
    id: string;
    schema_version: number;
    source_version: string;
    document_sha256: string;
    retrieved_at: string;
    locator: string;
    media_type: string;
    access_class: string;
    hash_scope: string;
    metadata?: {
      retrieval_origin?: string;
      pmcid?: string;
      doi?: string;
      rights_decision?: string;
      retention_display_rights?: string;
      license?: string;
      raw_license?: string;
      license_evidence?: string;
      representation_format?: string;
      parser_name?: string;
      parser_version?: string;
      extraction_status?: string;
      sections?: {
        section_id: string;
        original_heading: string;
        normalized_type: string;
        section_path: string[];
        ordinal: number | null;
        source_locator: string;
      }[];
      extraction_warnings?: string[];
      section_metadata_truncated?: boolean;
    } | null;
  } | null;
};

export type Claim = {
  id: string;
  source_id: string;
  passage_id: string;
  text: string;
  text_withheld_reason?: string | null;
  source_sentence?: string;
  span_start?: number | null;
  span_end?: number | null;
  span_offset_unit?: string;
  atomization_status?: string;
  atomization_version?: number;
  claim_type: string;
  evidence_status: string;
  appraisal: ClaimAppraisal;
  economic_facets?: {
    schema_version: number;
    status: string;
    evidence_kind: string;
    provider?: string | null;
    model?: string | null;
    facets: Record<string, { value: string; passage_ids: string[]; status: string }>;
  };
};

export type ClaimEvidence = {
  claim: Claim;
  source: Source;
  passage: Passage;
  methodology_passages: Passage[];
};

export type ResearchReport = {
  id: string;
  job_id: string;
  /** Schema version for this immutable run's report payload. */
  version: number;
  /** Storage-contract versions returned by the report API. */
  citation_map_schema_version?: number;
  verification_schema_version?: number;
  status: string;
  body_markdown: string;
  evidence_content_withheld?: boolean;
  content_withheld_reason?: string | null;
  citation_map: Record<string, { source_id: string; title: string; doi: string | null; url: string | null; passages: string[] }>;
  verification: Record<string, unknown> & {
    evidence_sufficiency_v1?: {
      schema_version: 1;
      status: 'EVIDENCE_VERIFIED' | 'PROVISIONAL' | 'INSUFFICIENT_EVIDENCE';
      rules_evaluated: string[];
      blocking_conditions: string[];
      warnings: string[];
      supporting_record_ids: string[];
      policy_version: string;
      decision_timestamp: string;
      human_review_status: 'not_performed';
    };
    evidence_sufficiency_v2?: {
      schema_version: 1;
      status: 'SUFFICIENT_FOR_SCOPE' | 'PRELIMINARY_EVIDENCE_MAP' | 'INSUFFICIENT_EVIDENCE';
      covered_requirement_ids: string[];
      uncovered_requirement_ids: string[];
      blocking_conditions: string[];
      question_plan: {
        question_kind: string;
        scope_breadth: string;
        material_requirements: Array<{ requirement_id: string; text: string; purpose?: string }>;
      };
      independence: {
        content_bearing_publication_groups: number;
        independent_investigations_confirmed: number;
        unknown_independence_publications: number;
      };
      material_requirement_evidence: Array<{
        requirement_id: string;
        linked_publication_identities: string[];
        supporting_publication_identities: string[];
        confirmed_independent_investigation_ids: string[];
        independence_unknown_publication_identities: string[];
        known_non_independent_publication_identities: string[];
      }>;
      human_review_status: 'not_performed';
      scientific_validation_status: 'not_independently_validated';
    };
    search_coverage?: {
      status?: string;
      discovery_completed_at_utc?: string | null;
      providers?: string[];
      queries_planned?: number;
      provider_queries_attempted?: number;
      provider_query_counts?: Record<string, number>;
      provider_result_counts?: Record<string, number>;
      provider_failures?: Record<string, number>;
      search_lens_counts?: { planned?: number; completed?: number; partial?: number; failed?: number; not_attempted?: number };
      search_lenses?: Array<{
        lens_id?: string;
        category?: string;
        purpose?: string;
        focus?: string;
        exact_query?: string;
        status?: string;
        pagination_state?: string;
        candidate_keys?: string[];
        selected_candidate_keys?: string[];
        providers?: Array<{ provider?: string; status?: string; results?: number; error_code?: string | null }>;
      }>;
      counterevidence_search_status?: string;
      retrieval_stopping_reason?: string;
      selected_sources?: number;
      candidate_ledger_records?: number;
      candidate_ledger_status?: string;
      candidate_exclusion_counts?: Record<string, number>;
      duplicate_records_excluded?: number;
      records_excluded_by_source_cap?: number;
      citation_expansion_status?: string;
      citation_expansion?: {
        status?: string;
        method?: string;
        requests_attempted?: number;
        seed_work_ids?: string[];
        omitted_backward_count?: number;
        reported_cost_status?: string;
        reported_cost_usd?: number | null;
        sampling_note?: string;
        errors?: Array<{ stage?: string; error_code?: string; retry_after_seconds?: number | null }>;
      };
      organization_discovery?: {
        schema_version?: number;
        strategy?: string;
        status?: string;
        seed_work_count?: number;
        identity_requests_attempted?: number;
        domain_identity_requests_attempted?: number;
        identity_requests_failed?: number;
        organizations?: Array<{
          organization_id?: string;
          openalex_ids?: string[];
          canonical_name?: string;
          aliases?: string[];
          organization_types?: string[];
          official_domains?: string[];
          official_urls?: string[];
          country_code?: string | null;
          identity_status?: string;
          verification_method?: string;
          verification_source?: string | null;
          verification_date?: string | null;
          verification_timestamp?: string | null;
          source_record_updated_at?: string | null;
          registry_match?: boolean;
          quality_assessment?: string;
          related_publications?: Array<{ title?: string; doi?: string | null; provider?: string }>;
          limitations?: string[];
        }>;
        publication_searches?: Array<{
          organization_id?: string;
          organization_name?: string;
          openalex_institution_id?: string;
          status?: string;
          provider?: string;
          filter?: string;
          query?: string;
          returned_count?: number;
          publication_ids?: string[];
          publications?: Array<{
            canonical_identity?: string;
            title?: string;
            doi?: string | null;
            publication_year?: number | null;
            provider?: string;
          }>;
          error_code?: string | null;
          homepage_url?: string | null;
          api_url?: string | null;
          discovery_link_source?: string | null;
          request_count?: number;
          request_dispatched?: boolean;
          content_fetched?: boolean;
          rights_status?: string;
        }>;
        selected_publications?: Array<{
          source_id?: string;
          title?: string;
          doi?: string | null;
          organization_id?: string;
          organization_name?: string;
          identity_status?: string;
          verification_source?: string | null;
        }>;
        interpretation_limit?: string;
      };
      conditional_statistics_routing?: {
        status?: string;
        schema_version?: number;
        world_bank_data360?: StatisticsRouteOutcome;
        ilostat?: StatisticsRouteOutcome;
      };
      government_publication_search?: {
        provider?: string;
        status?: string;
        geography?: string | null;
        query?: string | null;
        returned_count?: number;
        publication_ids?: string[];
        request_dispatched?: boolean;
        error_code?: string | null;
        linked_content_fetched?: boolean;
        metadata_only?: boolean;
        api_support_status?: string;
        organization_discovery?: {
          status?: string;
          verification_provider?: string;
          maximum_unique_organizations?: number;
          requests_attempted?: number;
          organizations?: VerifiedGovernmentOrganization[];
          errors?: Array<{ slug?: string; error_code?: string; request_dispatched?: boolean }>;
          interpretation_limit?: string;
        };
      };
      general_web_discovery?: {
        schema_version?: number;
        provider?: string;
        status?: string;
        account_plan?: string | null;
        account_balance_credits?: number | null;
        preflight_status?: string;
        preflight_request_count?: number;
        request_count?: number;
        queries_planned?: string[];
        hits?: Array<{
          query?: string;
          title?: string;
          url?: string;
          domain?: string;
          rank?: number;
          snippet_role?: string;
          organization_id?: string;
          candidate_status?: string;
        }>;
        searches?: Array<{
          query?: string;
          purpose?: string;
          organization_id?: string;
          verified_domain?: string;
          status?: string;
          result_count?: number;
          reported_cost_credits?: number | null;
          usage_status?: string;
        }>;
        domain_verifications?: Array<{
          domain?: string;
          candidate_domain?: string;
          publisher_search_lead_url?: string | null;
          status?: string;
          canonical_name?: string;
          verification_source?: string;
          organization_id?: string;
        }>;
        newly_discovered_organizations?: Array<{
          organization_id?: string;
          canonical_name?: string;
          official_domain?: string | null;
          publisher_linked_domain?: string;
          identity_status?: string;
          registry_match?: boolean;
          verification_source?: string;
          verification_method?: string;
        }>;
        official_publication_search?: {
          status?: string;
          organization_name?: string;
          returned_count?: number;
          homepage_url?: string;
          api_url?: string;
          rights_status?: string;
          content_fetched?: boolean;
        };
        verified_official_publications?: Array<{
          doi?: string | null;
          title?: string;
          publisher?: string;
          official_url?: string;
          publisher_domain_search_lead_url?: string;
          publisher_verification?: string;
          content_fetched?: boolean;
          rights_status?: string;
          selected?: boolean;
          organization_id?: string;
          source_id?: string;
          retrieval_status?: string;
          passage_count?: number;
        }>;
        reserved_credits?: number;
        reported_cost_credits?: number;
        unresolved_reserved_credits?: number;
        allowance_left_credits?: number | null;
      };
      source_governance?: {
        schema_version?: number;
        plan_status?: string;
        policy_version?: string;
        registry_version?: string;
        planned_classes?: string[];
        searched_classes?: string[];
        missing_classes?: string[];
        coverage_complete?: boolean;
        interpretation_limit?: string;
        class_status?: Record<string, { status?: string; candidate_count?: number; selected_count?: number }>;
        class_selection_reasons?: Record<string, string[]>;
      };
    };
    citation_link_integrity?: {
      schema_version: number;
      level: 'deterministic_link_integrity_only';
      status: 'passed' | 'needs_review';
      claims_checked: number;
      claims_with_valid_source_and_passage: number | null;
    };
    semantic_assessment?: {
      schema_version: number;
      method: 'not_performed' | 'model_assisted_not_independently_verified';
      support_check: string;
      uncited_material_claim_scan: string;
      provider: string | null;
      model: string | null;
      audit_schema_version: number | null;
      items: Record<string, unknown>[];
      uncited_claims: Record<string, unknown>[];
      rejected_records: number;
      input_truncated: boolean;
      skip_reason: string | null;
    };
    semantic_audit_batch_coverage?: {
      schema_version?: number;
      method?: string;
      report_characters?: number;
      expected_batches?: number;
      attempted_batches?: number;
      completed_batches?: number;
      complete?: boolean;
      expected_item_ids?: string[];
      assessed_item_ids?: string[];
      skipped_item_ids?: string[];
      scan_character_coverage?: number;
      scan_complete?: boolean;
      output_limit_batch_ids?: string[];
      unresolved_batch_ids?: string[];
      batches?: Array<{
        batch_id?: string;
        status?: string;
        scan_start?: number;
        scan_end?: number;
        provider?: string | null;
        model?: string | null;
        error_class?: string | null;
        usage?: Record<string, unknown> | null;
      }>;
    };
  };
  model_name: string | null;
  created_at: string;
};

export type StatisticsRouteOutcome = {
  schema_version?: number;
  status?: 'searched' | 'not_applicable' | 'not_attempted' | string;
  reason_code?: string | null;
  requests?: number;
  results?: number;
  failures?: number;
};

export type ReportHistory = {
  items: ReportHistoryItem[];
  total: number;
  limit: number;
  offset: number;
  has_more: boolean;
  version_semantics: string;
};

export type ReportHistoryItem = ResearchReport & {
  project_id: string;
  project_title: string;
  project_archived_at: string | null;
  question: string;
};

export type ReportInspection = {
  report: ResearchReport;
  job: ResearchJob;
  project: Project;
  sources: Source[];
  claims: Claim[];
};

export type EvidenceLink = {
  claim_id: string;
  passage_ids: string[];
};

export type EvidenceRelationship = {
  id: string;
  claim_a_id: string;
  claim_b_id: string;
  relationship_type: string;
  scope_alignment: 'same' | 'different' | 'unknown' | string;
  scope_differences: string[];
  rationale: string;
  evidence: EvidenceLink[];
  status: string;
  schema_version: number;
  provider: string | null;
  model: string | null;
  created_at: string;
};

export type CompetingHypothesis = {
  id: string;
  comparison_group_id: string;
  side: 'A' | 'B' | string;
  statement: string;
  evidence: EvidenceLink[];
  uncertainty: string;
  why_competing: string;
  status: string;
  schema_version: number;
  provider: string | null;
  model: string | null;
  created_at: string;
};

export type ComparisonCollection<T> = {
  items: T[];
  status: string;
  message?: string;
};

export type Conversation = {
  id: string;
  project_id: string;
  title: string;
  created_at: string;
};

export type ConversationMessage = {
  id: string;
  conversation_id: string;
  role: 'user' | 'assistant';
  content: string;
  related_job_id: string | null;
  created_at: string;
};

export type FollowUpContext = {
  status: string;
  parent: {
    job_id: string;
    question: string;
    report_id: string | null;
    report_status: string | null;
  } | null;
  reuse_method?: string | null;
  reuse_boundary?: string | null;
  claims: {
    claim: Claim;
    source: { id: string; title: string; retrieval_status: string };
    passage: { id: string; locator: string };
  }[];
};

