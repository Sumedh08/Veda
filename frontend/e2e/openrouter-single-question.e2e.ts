import { expect, test } from '@playwright/test';
import { mkdir, readFile, writeFile } from 'node:fs/promises';
import { dirname } from 'node:path';
import { auditOpenRouterFreeUsage } from '../src/openrouterFreeAudit';

const modelId = process.env.VEDA_OPENROUTER_EXPECTED_MODEL || 'nvidia/nemotron-3.5-super-vl:free';
const runId = process.env.VEDA_OPENROUTER_RUN_ID || 't112';
const question = {
  id: 't112-developer-productivity',
  question: 'Does generative AI improve software developer productivity, and why do empirical studies sometimes report different findings?',
  context:
    'Synthesize empirical studies of generative-AI coding assistants and related developer tools. Compare controlled experiments, field studies, and repository or survey analyses without treating them as interchangeable. Separate task completion time, accepted output, throughput, code quality, rework, and review burden. Do not invent outcomes for a hypothetical company or infer causal effects from abstracts alone. Explain differences by task type and difficulty, developer experience, tool/version, study setting, outcome definition, adoption, and follow-up duration when the retrieved evidence supports those distinctions. Preserve nulls where methods or results are not available.',
  geography: 'International; identify study locations when reported',
  population: 'Software developers, programming tasks, and software teams studied in empirical generative-AI research',
  time_horizon: 'Studies published 2022 onward, including follow-up duration where reported',
  decision_objective: 'Explain whether observed productivity changes are consistent across empirical settings and what a 60-engineer product company could safely infer',
  comparator: 'Comparable developer tasks or teams with and without generative-AI coding assistance, as defined in each study',
  target_outcome: 'Task completion time, accepted work per developer time, code quality, rework, defects, review burden, and developer experience',
  denominator: 'Study-specific developers, tasks, commits, or engineer-time; do not pool unlike denominators',
  assumptions_to_test:
    'Task choice and difficulty, participant experience, tool and model version, novelty and learning, selection into use, team spillovers, outcome measurement, reviewer effort, code-quality follow-up, and publication or reporting bias may explain heterogeneous findings.',
};

const requiredOperations = {
  planning: 'veda_research_plan_selection_v1',
  appraisal: 'veda_appraisal_batch_v2',
  comparison: 'veda_comparison_batch_v1',
  synthesis: 'veda_report_draft_v3',
  semantic_support: 'veda_semantic_report_audit_v1',
} as const;

test('one bounded free-model research job completes and its saved evidence is inspected', async ({ page }) => {
  test.setTimeout(1_200_000);
  test.skip(process.env.VEDA_OPENROUTER_LIVE_E2E !== '1', 'Requires explicit process-only live-run opt-in and a local credential.');
  expect(process.env.OPENAI_API_KEY || '').toBe('');
  expect(process.env.OPENROUTER_MODEL).toBe(modelId);
  expect(process.env.VEDA_OPENROUTER_OUTPUT_PATH).toBeTruthy();
  expect(process.env.VEDA_OPENROUTER_PREFLIGHT_PATH).toBeTruthy();
  expect(process.env.VEDA_OPENROUTER_REQUEST_COUNTER_PATH).toBeTruthy();

  await page.goto('/');
  await page.getByRole('button', { name: 'Continue to local workspace' }).click();
  await page.waitForFunction(() => {
    const session = JSON.parse(sessionStorage.getItem('veda_local_session') || '{}') as { token?: string };
    return Boolean(session.token);
  });
  const seededProject = page
    .locator('.project-grid')
    .getByRole('button', { name: /Local browser integration \(synthetic data\)/ });
  await expect(seededProject).toBeVisible();
  await seededProject.click();
  if (await page.getByRole('button', { name: 'Open navigation' }).isVisible()) {
    await page.getByRole('button', { name: 'Open navigation' }).click();
  }

  const apiOrigin = new URL(process.env.VEDA_E2E_API_BASE_URL || 'http://127.0.0.1:8001/api/v1').origin;
  const resumeJobId = process.env.VEDA_OPENROUTER_RESUME_JOB_ID || '';
  const run = await page.evaluate(async ({ apiOrigin, researchQuestion, resumeJobId, runId }) => {
    type SafeFailure = { stage: string; class: string; http_status?: number };
    const session = JSON.parse(sessionStorage.getItem('veda_local_session') || '{}') as { token?: string };
    if (!session.token) throw new Error('Local browser session was unavailable.');
    const headers = { Authorization: `Bearer ${session.token}`, 'Content-Type': 'application/json' };
    const api = async (path: string, init: RequestInit = {}) => {
      // Each POST is issued once. This harness never resends an uncertain operation.
      const response = await fetch(`${apiOrigin}/api/v1${path}`, { ...init, headers });
      const body = response.status === 204 ? null : await response.json();
      if (!response.ok) {
        const error = new Error('Veda local API operation failed.') as Error & { status?: number; apiCode?: string };
        error.status = response.status;
        const detail = body?.detail;
        error.apiCode = typeof detail?.code === 'string' ? detail.code : undefined;
        throw error;
      }
      return body as Record<string, any>;
    };

    const result: Record<string, any> = {
      question: researchQuestion.question,
      scope: researchQuestion,
      completed_all_ai_stages: false,
      report_saved: false,
      browser_inspection: { attempted: false, report_opened: false, citation_opened: false, original_passage_visible: false, methodological_assessment_visible: false },
      errors: [] as SafeFailure[],
      resumed_existing_job: Boolean(resumeJobId),
    };
    let jobId: string | null = null;
    try {
      const terminalStatuses = new Set(['completed', 'completed_with_limitations', 'failed', 'cancelled']);
      const projectList = await api('/projects') as { items: Record<string, any>[] };
      const project = projectList.items.find((item) => item.title === 'Local browser integration (synthetic data)');
      if (!project) throw new Error('The isolated local test project was unavailable.');
      result.project_id = project.id;
      result.project = { id: project.id, title: project.title };
      let job: Record<string, any>;
      if (resumeJobId) {
        job = await api(`/research-jobs/${resumeJobId}`);
        if (
          job.project_id !== project.id
          || job.question !== researchQuestion.question
          || job.status !== 'queued'
          || Number(job.model_calls_reserved || 0) !== 0
        ) {
          throw new Error('The existing T-112 job is no longer safe to resume.');
        }
      } else {
        job = await api(`/projects/${project.id}/research-jobs`, {
          method: 'POST',
          body: JSON.stringify({
            ...researchQuestion,
            depth: 'standard',
            budget_ceiling_usd: 0,
            idempotency_key: `veda-${runId}-${Date.now()}`,
          }),
        });
      }
      jobId = job.id;
      result.job_id = jobId;
      result.job = job;
      result.advances = [];
      if (job.status !== 'queued') throw new Error('The research job did not enter its queued state.');

      for (let step = 0; step < 16 && !terminalStatuses.has(job.status); step += 1) {
        const operationKey = `veda-${runId}-step-${step + 1}`;
        // A transport error ends the test; the same POST is never retried.
        job = await api(`/research-jobs/${jobId}/advance`, {
          method: 'POST',
          body: JSON.stringify({ operation_key: operationKey }),
        });
        result.job = job;
        result.advances.push({
          status: job.status,
          current_stage: job.current_stage,
          model_calls_reserved: job.model_calls_reserved,
          error_class: job.error_class,
        });
        if (Number(job.model_calls_reserved || 0) > 6) {
          result.errors.push({ stage: job.current_stage || 'unknown', class: 'local_model_call_limit_exceeded' });
          break;
        }
      }
    } catch (error) {
      const safe = error as Error & { status?: number; apiCode?: string };
      result.errors.push({
        stage: result.job?.current_stage || 'job_creation_or_advance',
        class: safe.apiCode || safe.name || 'browser_api_error',
        ...(safe.status ? { http_status: safe.status } : {}),
      });
      if (jobId) {
        try {
          result.job = await api(`/research-jobs/${jobId}`);
        } catch {
          // The provider operation is not repeated; retain the last confirmed state.
        }
      }
    }

    if (jobId) {
      result.current_stage = result.job?.current_stage || null;
      result.job_status = result.job?.status || null;
      result.model_calls_reserved = Number(result.job?.model_calls_reserved || 0);
      try {
        const exported = await api('/me/export') as { collections: Record<string, any[]> };
        result.provider_usage = (exported.collections.usage_ledger || []).filter((entry) => entry.job_id === jobId);
      } catch {
        result.provider_usage = [];
        result.errors.push({ stage: 'usage_collection', class: 'usage_export_unavailable' });
      }
      try {
        result.events = (await api(`/research-jobs/${jobId}/events`) as { items: any[] }).items;
        result.plan = await api(`/research-jobs/${jobId}/plan`);
        result.candidates = (await api(`/research-jobs/${jobId}/candidates?limit=200`) as { items: any[] }).items;
        result.sources = (await api(`/research-jobs/${jobId}/sources`) as { items: any[] }).items;
        result.claims = (await api(`/research-jobs/${jobId}/claims`) as { items: any[] }).items;
        result.relationships_record = await api(`/research-jobs/${jobId}/relationships`);
        result.relationships = result.relationships_record.items || [];
        result.hypotheses_record = await api(`/research-jobs/${jobId}/hypotheses`);
        result.hypotheses = result.hypotheses_record.items || [];
      } catch (error) {
        const safe = error as Error & { status?: number; apiCode?: string };
        result.errors.push({ stage: 'evidence_inspection', class: safe.apiCode || safe.name || 'inspection_error', ...(safe.status ? { http_status: safe.status } : {}) });
      }
      if (['completed', 'completed_with_limitations'].includes(result.job_status)) {
        try {
          result.report = await api(`/research-jobs/${jobId}/report`);
          result.report_saved = Boolean(result.report?.id);
          result.report_inspection = await api(`/reports/${result.report.id}/inspection`);
        } catch (error) {
          const safe = error as Error & { status?: number; apiCode?: string };
          result.errors.push({ stage: 'report_inspection_api', class: safe.apiCode || safe.name || 'report_inspection_error', ...(safe.status ? { http_status: safe.status } : {}) });
        }
      }
    }

    const operations = new Set((result.provider_usage || []).filter((entry: Record<string, any>) => entry.succeeded === true).map((entry: Record<string, any>) => entry.operation));
    result.required_ai_operations = Object.fromEntries(Object.entries({
      planning: 'veda_research_plan_selection_v1',
      appraisal: 'veda_appraisal_batch_v2',
      comparison: 'veda_comparison_batch_v1',
      synthesis: 'veda_report_draft_v3',
      semantic_support: 'veda_semantic_report_audit_v1',
    }).map(([stage, operation]) => [stage, operations.has(operation)]));
    result.completed_all_ai_stages = Object.values(result.required_ai_operations).every(Boolean);
    result.source_counts = {
      candidates: result.candidates?.length || 0,
      selected: result.sources?.length || 0,
      claims: result.claims?.length || 0,
      citations: Object.keys(result.report?.citation_map || {}).length,
      relationships: result.relationships?.length || 0,
      hypotheses: result.hypotheses?.length || 0,
      providers_queried: result.report?.verification?.search_coverage?.provider_query_counts || {},
      provider_results: result.report?.verification?.search_coverage?.provider_result_counts || {},
    };
    result.source_access_classes = (result.sources || []).map((source: Record<string, any>) => ({
      source_id: source.id,
      title: source.title,
      retrieval_status: source.retrieval_status,
      passage_access_levels: (source.passages || []).map((passage: Record<string, any>) => passage.access_level),
      source_appraisal: source.appraisal,
    }));
    result.claim_appraisals = (result.claims || []).map((claim: Record<string, any>) => ({
      claim_id: claim.id,
      source_id: claim.source_id,
      text: claim.text,
      passage_ids: claim.passage_ids,
      appraisal: claim.appraisal,
    }));
    result.study_design_contrasts = (result.relationships || []).map((item: Record<string, any>) => ({
      relationship_type: item.relationship_type,
      scope_alignment: item.scope_alignment,
      scope_differences: item.scope_differences,
      rationale: item.rationale,
      evidence: item.evidence,
    }));
    result.competing_hypotheses = result.hypotheses || [];
    const reportVerification = result.report?.verification || {};
    const successfulOperation = (stage: string) => Boolean(result.required_ai_operations?.[stage]);
    result.stage_coverage = {
      planning: successfulOperation('planning'),
      scholarly_discovery: (result.sources?.length || 0) > 0,
      claim_extraction: (result.claims || []).some((claim: Record<string, any>) => Boolean(
        claim.source_id && (claim.passage_id || (Array.isArray(claim.passage_ids) && claim.passage_ids.length > 0)),
      )),
      methodological_appraisal: successfulOperation('appraisal'),
      claim_comparison_and_contradiction_analysis: successfulOperation('comparison'),
      competing_hypothesis_analysis_recorded: result.hypotheses_record?.status !== undefined
        && result.hypotheses_record?.status !== 'not_assessed',
      deterministic_citation_integrity: Boolean(reportVerification.status)
        && (result.source_counts?.citations || 0) > 0,
      semantic_support_assessment: successfulOperation('semantic_support')
        && String(reportVerification.semantic_support_check || '').startsWith('performed_'),
      model_synthesis: successfulOperation('synthesis') && result.report?.model_name === modelId,
      report_persistence: Boolean(result.report_saved && result.report_inspection?.report?.id),
    };
    return result;
  }, { apiOrigin, researchQuestion: question, resumeJobId, runId });

  let preflight: Record<string, any> | null = null;
  if (process.env.VEDA_OPENROUTER_PREFLIGHT_PATH) {
    preflight = JSON.parse(await readFile(process.env.VEDA_OPENROUTER_PREFLIGHT_PATH, 'utf8')) as Record<string, any>;
  }
  const providerUsage = Array.isArray(run.provider_usage) ? run.provider_usage : [];
  let providerRequestAttempts: number | null = null;
  try {
    const counter = await readFile(process.env.VEDA_OPENROUTER_REQUEST_COUNTER_PATH!, 'utf8');
    if (/^\d+\s*$/.test(counter)) providerRequestAttempts = Number(counter.trim());
  } catch {
    // Keep the missing counter visible in the final artifact and fail the strict guard below.
  }
  const requestCountMatchesUsage = providerRequestAttempts === providerUsage.length;
  const usageAudit = auditOpenRouterFreeUsage(providerUsage, 6);
  const actualModelIds = usageAudit.model_ids;
  const exactModelRoute = actualModelIds.length > 0 && actualModelIds.every((model) => model === modelId);
  const artifactPath = process.env.VEDA_OPENROUTER_OUTPUT_PATH!;
  const artifact = {
    generated_at: new Date().toISOString(),
    authorization_scope: 'one question only; no OpenAI, paid route, batch, or deployment',
    question: question.question,
    database_path: process.env.VEDA_OPENROUTER_DATABASE_PATH || null,
    resumed_from_attempt: process.env.VEDA_OPENROUTER_RESUME_FROM || null,
    configured_model: modelId,
    preflight,
    provider_request_hard_cap: 6,
    provider_request_attempts: providerRequestAttempts,
    request_count_matches_usage: requestCountMatchesUsage,
    provider_rate_limit_retries: 0,
    uncertain_post_resends: 0,
    exact_model_route: exactModelRoute,
    usage_audit: usageAudit,
    ...run,
  };
  await mkdir(dirname(artifactPath), { recursive: true });
  await writeFile(artifactPath, `${JSON.stringify(artifact, null, 2)}\n`, 'utf8');

  if (run.report_saved) {
    const browserInspection = run.browser_inspection;
    browserInspection.attempted = true;
    try {
      await page.getByRole('button', { name: 'Reports' }).click();
      await expect(page.getByRole('heading', { name: 'Report history' })).toBeVisible();
      const row = page.locator('.report-history-row').filter({ has: page.getByRole('heading', { name: question.question, exact: true }) });
      await expect(row).toHaveCount(1);
      await row.getByRole('button', { name: 'Open report' }).click();
      await expect(page.getByRole('heading', { name: question.question, exact: true })).toBeVisible();
      await expect(page.locator('.report-content')).toBeVisible();
      browserInspection.report_opened = true;

      const citationIds = Object.keys(run.report?.citation_map || {});
      if (citationIds.length) {
        const citation = page.getByRole('button', { name: `Open source ${citationIds[0]}` }).first();
        await expect(citation).toBeVisible();
        await citation.click();
        const sourceDrawer = page.locator('.evidence-drawer');
        await expect(sourceDrawer).toBeVisible();
        const passage = sourceDrawer.locator('.passage-chip p').first();
        if (await passage.count()) {
          const text = (await passage.innerText()).trim();
          browserInspection.original_passage_visible = text.length > 0;
          browserInspection.first_visible_passage_excerpt = text.slice(0, 400);
        }
        browserInspection.source_metadata_visible = /Source metadata from (Crossref|OpenAlex|World Bank Data360|ILOSTAT)/.test(await sourceDrawer.innerText());
        browserInspection.source_methodological_appraisal_visible = /Methodological appraisal/.test(await sourceDrawer.innerText());
        browserInspection.citation_opened = true;
        await page.getByRole('button', { name: 'Close source inspector' }).click();
      }

      const claimUnitDetails = page.locator('.claim-unit-manifest');
      if (await claimUnitDetails.count()) {
        await claimUnitDetails.locator('summary').click();
        const inspectClaim = page.getByRole('button', { name: 'Inspect exact source span' }).first();
        if (await inspectClaim.count()) {
          await inspectClaim.click();
          const claimDrawer = page.locator('.evidence-drawer');
          await expect(claimDrawer).toBeVisible();
          const content = await claimDrawer.innerText();
          browserInspection.methodological_assessment_visible = /Methodological (appraisal|relationship)/.test(content);
          browserInspection.claim_inspector_excerpt = content.slice(0, 1200);
          await page.getByRole('button', { name: 'Close evidence inspector' }).click();
        }
      }
    } catch {
      browserInspection.error_class = 'browser_report_inspection_failed';
    }
  }

  artifact.browser_inspection = run.browser_inspection;
  artifact.operational_success = Boolean(
    run.report_saved
      && run.job_status === 'completed'
      && run.completed_all_ai_stages
      && Object.values(run.stage_coverage || {}).every(Boolean)
      && usageAudit.all_entries_openrouter
      && usageAudit.all_reported_models_free
      && exactModelRoute
      && usageAudit.accepted_response_count > 0
      && providerRequestAttempts !== null
      && providerRequestAttempts <= 6
      && requestCountMatchesUsage
      && usageAudit.no_reported_nonzero_cost
      && usageAudit.unknown_reported_cost_entries === 0
      && usageAudit.accepted_responses_report_zero_cost
      && usageAudit.total_usage_records_at_or_below_free_test_cap
      && run.browser_inspection.report_opened
      && run.browser_inspection.citation_opened
      && run.browser_inspection.original_passage_visible
      && run.browser_inspection.source_methodological_appraisal_visible
  );
  await writeFile(artifactPath, `${JSON.stringify(artifact, null, 2)}\n`, 'utf8');

  expect(run.job_id).toBeTruthy();
  expect(run.model_calls_reserved).toBeLessThanOrEqual(6);
  expect(providerRequestAttempts).not.toBeNull();
  expect(providerRequestAttempts).toBeLessThanOrEqual(6);
  expect(requestCountMatchesUsage).toBe(true);
  expect(providerUsage.length).toBeLessThanOrEqual(6);
  expect(usageAudit.all_entries_openrouter).toBe(true);
  expect(usageAudit.all_reported_models_free).toBe(true);
  expect(exactModelRoute).toBe(true);
  expect(usageAudit.accepted_response_count).toBeGreaterThan(0);
  expect(usageAudit.no_reported_nonzero_cost).toBe(true);
  expect(usageAudit.accepted_responses_report_zero_cost).toBe(true);
  expect(run.report_saved).toBe(true);
  expect(run.completed_all_ai_stages).toBe(true);
  expect(Object.values(run.stage_coverage || {}).every(Boolean)).toBe(true);
  expect(run.job_status).toBe('completed');
  expect(run.browser_inspection.report_opened).toBe(true);
  expect(run.browser_inspection.citation_opened).toBe(true);
  expect(run.browser_inspection.original_passage_visible).toBe(true);
  expect(run.browser_inspection.source_methodological_appraisal_visible).toBe(true);
  expect(artifact.operational_success).toBe(true);
});
