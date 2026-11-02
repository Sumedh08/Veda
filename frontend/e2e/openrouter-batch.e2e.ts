import { expect, test } from '@playwright/test';
import { mkdir, writeFile } from 'node:fs/promises';
import { dirname, resolve } from 'node:path';
import { auditOpenRouterFreeUsage } from '../src/openrouterFreeAudit';

type ResearchCase = {
  id: string;
  question: string;
  context: string;
  geography: string;
  population: string;
  time_horizon: string;
  decision_objective: string;
  comparator: string;
  target_outcome: string;
  denominator: string;
  assumptions_to_test: string;
};

const researchCases: ResearchCase[] = [
  {
    id: 'startup-hr-screening',
    question: 'For a 200-employee US software startup hiring 40 engineers and customer-support staff over six months, does an AI-assisted résumé screen reduce recruiter time-to-shortlist without worsening job-relevant selection quality or adverse impact?',
    context: 'Evaluate a hypothetical startup with a 3-person recruiting team. Compare an AI-assisted screen plus human review against the prior human-only workflow. Do not invent company outcomes. Separate screening throughput from later hiring performance and legal/fairness risk.',
    geography: 'United States', population: 'Applicants to a 200-employee software startup; engineering and customer-support roles',
    time_horizon: 'Recruiting funnel and outcomes through six months after hire', decision_objective: 'Decide whether to pilot AI-assisted résumé screening with human review',
    comparator: 'Human-only résumé screening using the same job criteria', target_outcome: 'Recruiter hours per qualified shortlist, job-related selection validity, subgroup selection rates, and six-month retention/performance',
    denominator: 'All eligible applicants by role and relevant demographic subgroup; hires followed for six months',
    assumptions_to_test: 'Historical screening labels may encode bias; recruiter time saved may shift work downstream; predictive scores may not generalize across roles or applicant groups.',
  },
  {
    id: 'startup-hr-onboarding',
    question: 'In a 200-employee startup onboarding 30 customer-support hires per quarter, does a generative-AI onboarding assistant shorten time to independent work and improve 90-day retention versus the existing mentor-led program without increasing policy errors?',
    context: 'Hypothetical US company; compare teams or a stepped rollout while accounting for hiring cohort and manager differences. Distinguish self-reported confidence from verified task quality. No company-level outcome data are supplied.',
    geography: 'United States', population: 'New customer-support hires at a 200-employee startup',
    time_horizon: 'First 90 days after hire', decision_objective: 'Estimate whether a bounded onboarding pilot merits expansion',
    comparator: 'Existing documentation and mentor-led onboarding', target_outcome: 'Days to independently resolve cases, audited policy-error rate, and 90-day retention',
    denominator: 'All hires starting in each cohort, with attrition retained in the denominator where appropriate',
    assumptions_to_test: 'AI access may vary by shift and prior experience; mentors may change their effort; early productivity may trade off with quality or learning.',
  },
  {
    id: 'support-agent-assist',
    question: 'For a 120-agent customer-support center handling 50,000 monthly tickets, does an agent-facing generative-AI reply assistant improve resolution time and customer satisfaction compared with the same agents without suggestions, after accounting for case mix and escalation?',
    context: 'Hypothetical B2B software support operation with English-language ticket data and human approval of every reply. Evaluate randomized or phased assignment, repeat contacts, escalations, hallucinated policy, and differences by ticket complexity.',
    geography: 'United States and Canada', population: 'Support agents and incoming customer tickets at a 120-agent center',
    time_horizon: 'Eight-week pilot plus a four-week follow-up for repeat contacts', decision_objective: 'Determine whether agent-assist should be deployed beyond a controlled pilot',
    comparator: 'Agent workflow with existing macros and knowledge search but no generated reply', target_outcome: 'Time to resolution, first-contact resolution, customer satisfaction, escalation, and audited factual-error rates',
    denominator: 'All eligible tickets assigned to each condition, reported by case type and agent experience',
    assumptions_to_test: 'Automation may shift work to review; satisfaction may reflect case severity; agent-level spillovers and selective use may bias comparisons.',
  },
  {
    id: 'developer-copilot',
    question: 'At a 60-engineer product company, does access to an AI coding copilot increase independently reviewed, production-accepted work per engineer-week over 12 weeks without raising rework, security defects, or code-review burden?',
    context: 'Hypothetical company considering staged team rollout. Distinguish code volume, accepted work, cycle time, and quality. Account for task difficulty, team collaboration, learning effects, and repository/security policy. Do not treat lines of code as productivity.',
    geography: 'United States', population: 'Software engineers and production changes at a 60-engineer product company',
    time_horizon: 'Twelve-week rollout with at least four weeks of post-merge defect follow-up', decision_objective: 'Assess the net productivity and risk case for organization-wide copilot access',
    comparator: 'Matched or randomized team-weeks without copilot access', target_outcome: 'Production-accepted tasks per engineer-week, cycle time, rework, defects, security findings, and review time',
    denominator: 'Engineer-weeks and eligible work items, stratified by task type and seniority',
    assumptions_to_test: 'Self-selection into tool use, team spillovers, novelty effects, task-mix shifts, and unobserved review labor may distort apparent gains.',
  },
  {
    id: 'sales-personalization',
    question: 'For a 35-person SaaS sales team contacting 8,000 qualified leads monthly, does generative-AI account research and email personalization increase held qualified meetings per eligible lead versus the current sales sequence, net of research, editing, and compliance time?',
    context: 'Hypothetical B2B team using human-approved outreach. Evaluate a randomized lead-level test with guardrails for deliverability, inaccurate personalization, opt-outs, and rep-level clustering. A higher open rate alone is not the business outcome.',
    geography: 'United States', population: 'Qualified inbound and outbound leads handled by a 35-person SaaS sales team',
    time_horizon: 'Ten-week experiment with a 30-day conversion window per lead', decision_objective: 'Decide whether AI-assisted research is worth operationalizing for the sales team',
    comparator: 'Current templated outreach plus manual account research', target_outcome: 'Held qualified meetings and downstream opportunities per eligible lead, plus net rep time and error rate',
    denominator: 'All eligible leads randomized before outreach, with assignment and non-contact tracked',
    assumptions_to_test: 'Lead quality and seasonality may differ; generated claims may be inaccurate; more meetings may not yield revenue; rep editing time may offset drafting gains.',
  },
  {
    id: 'marketing-content',
    question: 'At a 25-person B2B marketing team publishing 40 technical articles monthly, does a human-edited generative-AI drafting workflow improve publication throughput and qualified organic conversions per editor-hour versus the existing workflow without reducing factual accuracy or brand quality?',
    context: 'Hypothetical content operation. Compare comparable topics and authors, account for search ranking lag and distribution, and use blinded editorial scoring plus factual checks. Traffic and publication count are not interchangeable with qualified demand.',
    geography: 'English-language US market', population: 'Technical marketing writers, editors, and published articles at a 25-person team',
    time_horizon: 'Twelve-week production window plus a 90-day search/conversion follow-up', decision_objective: 'Set a safe, evidence-based policy for AI-assisted technical content',
    comparator: 'Existing writer-led drafting and editing process', target_outcome: 'Accepted articles per editor-hour, blinded quality score, verified factual-error rate, and qualified organic conversions',
    denominator: 'All article assignments and editor-hours, stratified by topic complexity and traffic potential',
    assumptions_to_test: 'Search ranking delays, topic selection, disclosure, author learning, and editor rework can confound observed output.',
  },
  {
    id: 'accounts-payable',
    question: 'For a 500-employee US manufacturer processing 6,000 invoices monthly, does AI-assisted invoice extraction and exception routing reduce cost and cycle time per correctly paid invoice versus the current accounts-payable process while preserving approval controls and fraud detection?',
    context: 'Hypothetical finance function. Distinguish OCR/extraction from autonomous payment, keep payment approval human-controlled, and examine vendor, invoice-format, and exception subgroups. Evaluate false matches, duplicate payments, auditability, and implementation costs.',
    geography: 'United States', population: 'Invoices processed by a 500-employee manufacturing company',
    time_horizon: 'Six-month controlled rollout with a subsequent audit period', decision_objective: 'Assess whether to expand AI-assisted invoice processing under existing financial controls',
    comparator: 'Current AP clerk entry, validation, and exception queue', target_outcome: 'Cost and time per correctly paid invoice, extraction accuracy, exception rate, duplicate/fraud detection, and control failures',
    denominator: 'All invoices received, including exceptions, rejected invoices, and duplicate attempts',
    assumptions_to_test: 'Automation may shift hidden exception work; vendor mix may change; low average error can hide costly rare failures; savings may omit software and oversight costs.',
  },
  {
    id: 'knowledge-assistant',
    question: 'In a 1,000-employee professional-services firm with 20,000 internal knowledge queries monthly, does a retrieval-grounded generative-AI assistant reduce employee search time and improve answer accuracy relative to the existing intranet search without increasing unsupported or stale-policy answers?',
    context: 'Hypothetical firm deploying only over permission-filtered internal documents. Compare against current search and human helpdesk escalation. Assess answer correctness against document versions, access-control leakage, task completion, and subgroup differences in terminology or location.',
    geography: 'United States, with offices in three states', population: 'Employees using internal policy, process, and project knowledge systems',
    time_horizon: 'Twelve-week pilot after a two-week baseline', decision_objective: 'Decide whether to extend a permission-aware internal knowledge assistant',
    comparator: 'Existing intranet search and human helpdesk channel', target_outcome: 'Time to correct answer, independently adjudicated accuracy, task completion, stale-answer and access-control incidents',
    denominator: 'All sampled eligible queries and employees invited to use each condition',
    assumptions_to_test: 'Self-selection and query difficulty can bias use metrics; answer acceptance is not correctness; document quality and freshness may dominate model choice.',
  },
  {
    id: 'analyst-copilot',
    question: 'For a 24-analyst public-health research unit completing 300 descriptive analyses per quarter, does a generative-AI data-analysis copilot improve reproducible, independently checked analyses per analyst-week compared with current scripts and peer support without increasing coding, interpretation, or privacy errors?',
    context: 'Hypothetical unit using de-identified datasets and a human-reviewed analysis workflow. Assess task completion, reproducibility from saved code, statistical correctness, analyst verification time, and privacy/security incidents. Separate drafting assistance from autonomous interpretation.',
    geography: 'United States', population: 'Analysts and de-identified public-health datasets in a 24-person research unit',
    time_horizon: 'One quarter with a four-week reproducibility follow-up', decision_objective: 'Determine whether the copilot merits a bounded, governed extension',
    comparator: 'Current programming workflow with scripts, documentation, and peer consultation', target_outcome: 'Independently reproduced analyses per analyst-week, correction rate, reproducibility, review time, and privacy/security errors',
    denominator: 'All assigned analyses and analyst-weeks, stratified by complexity and data source',
    assumptions_to_test: 'Analysts may delegate verification effort; easier tasks may be selected for the tool; code execution success does not ensure statistical validity.',
  },
  {
    id: 'organization-wide-rollout',
    question: 'For a 750-employee US services company considering a 12-week generative-AI rollout across HR, support, engineering, finance, and marketing, what evidence would establish net productivity, quality, cost, equity, and safety effects against a staggered-control design, and which outcomes should gate expansion?',
    context: 'Hypothetical company has no baseline results supplied. Design an evidence-grounded evaluation rather than forecast company-specific ROI. Address staggered team rollout, spillovers, worker experience, workload displacement, training, inference/software costs, evaluation labor, data protection, and heterogeneous effects.',
    geography: 'United States', population: 'Employees and work products across five functions in a 750-employee services company',
    time_horizon: 'Twelve-week pilot, with 90-day quality/retention follow-up', decision_objective: 'Define evidence thresholds and stop/go criteria for staged expansion',
    comparator: 'Matched not-yet-treated teams and within-team baseline periods', target_outcome: 'Function-specific output per paid hour jointly assessed with quality, rework, customer/worker outcomes, cost, and equity',
    denominator: 'All assigned employees, teams, and eligible work items; include non-use, attrition, and downstream review time',
    assumptions_to_test: 'Function-specific measures may not aggregate; staggered adoption may create spillovers; adoption and worker selection are non-random; short-run gains may fade or shift costs.',
  },
];

test('ten-case OpenRouter free-only Veda run persists, audits, and opens every cited report', async ({ page }) => {
  test.setTimeout(1_800_000);
  test.skip(process.env.VEDA_OPENROUTER_LIVE_E2E !== '1', 'Requires the separate process-only OpenRouter credential runner.');
  expect(process.env.VEDA_OPENROUTER_LIVE_E2E).toBe('1');
  expect(process.env.OPENAI_API_KEY || '').toBe('');
  expect(researchCases).toHaveLength(10);

  await page.goto('/');
  await page.getByRole('button', { name: 'Continue to local workspace' }).click();
  await page.waitForFunction(() => {
    const session = JSON.parse(sessionStorage.getItem('veda_local_session') || '{}') as { token?: string };
    return Boolean(session.token);
  });
  const seededProject = page.locator('.project-grid').getByRole('button', { name: /Local browser integration \(synthetic data\)/ });
  await expect(seededProject).toBeVisible();
  await seededProject.click();
  if (await page.getByRole('button', { name: 'Open navigation' }).isVisible()) {
    await page.getByRole('button', { name: 'Open navigation' }).click();
  }

  const apiOrigin = new URL(process.env.VEDA_E2E_API_BASE_URL || 'http://127.0.0.1:8001/api/v1').origin;
  const batch = await page.evaluate(async ({ apiOrigin, cases }) => {
    const session = JSON.parse(sessionStorage.getItem('veda_local_session') || '{}') as { token?: string };
    if (!session.token) throw new Error('Local browser session token was unavailable.');
    const headers = { Authorization: `Bearer ${session.token}`, 'Content-Type': 'application/json' };
    const api = async (path: string, init: RequestInit = {}) => {
      const response = await fetch(`${apiOrigin}/api/v1${path}`, { ...init, headers });
      const body = response.status === 204 ? null : await response.json();
      if (!response.ok) throw new Error(`Veda API ${init.method || 'GET'} ${path} returned ${response.status}: ${JSON.stringify(body).slice(0, 500)}`);
      return body as Record<string, any>;
    };
    const projectList = await api('/projects') as { items: Record<string, any>[] };
    const project = projectList.items.find((item) => item.title === 'Local browser integration (synthetic data)');
    if (!project) throw new Error('The isolated live-test project was not seeded.');
    const results: Record<string, any>[] = [];

    for (let index = 0; index < cases.length; index += 1) {
      const researchCase = cases[index];
      const record: Record<string, any> = { case_id: researchCase.id, question: researchCase.question, scope: researchCase, advances: [], errors: [] };
      try {
        let job = await api(`/projects/${project.id}/research-jobs`, {
          method: 'POST',
          body: JSON.stringify({
            ...researchCase,
            context: researchCase.context,
            depth: 'standard',
            budget_ceiling_usd: 0.25,
            idempotency_key: `or-batch-20261029-${researchCase.id}`,
          }),
        });
        record.job = job;
        if (job.status !== 'queued') throw new Error(`New job started in unexpected state ${job.status}.`);
        for (let step = 0; step < 8 && !['completed', 'completed_with_limitations', 'failed', 'cancelled'].includes(job.status); step += 1) {
          const previousModelCalls = Number(job.model_calls_reserved || 0);
          job = await api(`/research-jobs/${job.id}/advance`, {
            method: 'POST',
            body: JSON.stringify({ operation_key: `or-batch-${index + 1}-${step + 1}` }),
          });
          record.advances.push({ status: job.status, current_stage: job.current_stage, model_calls_reserved: job.model_calls_reserved, cost_spent_estimate_usd: job.cost_spent_estimate_usd, error_class: job.error_class, error_message: job.error_message });
          record.job = job;
          if (job.status === 'failed') break;
          if (Number(job.model_calls_reserved || 0) > previousModelCalls) {
            // OpenRouter free routes may be rate-limited per minute. Throttle
            // model calls so this bounded 50-call batch stays below 20/min.
            await new Promise((resolve) => window.setTimeout(resolve, 4200));
          }
        }
        if (['completed', 'completed_with_limitations'].includes(job.status)) {
          const report = await api(`/research-jobs/${job.id}/report`);
          const [inspection, plan, events, relationships, hypotheses, claims, sources, candidates] = await Promise.all([
            api(`/reports/${report.id}/inspection`),
            api(`/research-jobs/${job.id}/plan`),
            api(`/research-jobs/${job.id}/events`),
            api(`/research-jobs/${job.id}/relationships`),
            api(`/research-jobs/${job.id}/hypotheses`),
            api(`/research-jobs/${job.id}/claims`),
            api(`/research-jobs/${job.id}/sources`),
            api(`/research-jobs/${job.id}/candidates?limit=200`),
          ]);
          record.report = report;
          record.inspection = inspection;
          record.plan = plan;
          record.events = events.items;
          record.relationships = relationships;
          record.hypotheses = hypotheses;
          record.claims = claims.items;
          record.sources = sources.items;
          record.candidates = candidates.items;
          record.source_counts = {
            selected: report.verification?.search_coverage?.selected_sources ?? sources.items.length,
            candidates: report.verification?.search_coverage?.candidate_ledger_records ?? candidates.items.length,
            citation_count: Object.keys(report.citation_map || {}).length,
            claim_count: claims.items.length,
            relationship_count: relationships.items?.length || 0,
            hypothesis_count: hypotheses.items?.length || 0,
            provider_queries: report.verification?.search_coverage?.provider_query_counts || {},
            provider_results: report.verification?.search_coverage?.provider_result_counts || {},
          };
        }
      } catch (error) {
        record.errors.push(error instanceof Error ? error.message : String(error));
      }
      results.push(record);
    }

    const exported = await api('/me/export') as { collections: Record<string, any[]> };
    const jobIds = new Set(results.map((item) => item.job?.id).filter(Boolean));
    const usage = (exported.collections.usage_ledger || []).filter((entry) => jobIds.has(entry.job_id));
    for (const item of results) {
      item.provider_usage = usage.filter((entry) => entry.job_id === item.job?.id);
    }
    const projectUsage = await api(`/projects/${project.id}/usage`);
    return {
      project_id: project.id,
      started_cases: cases.length,
      results,
      provider_usage: usage,
      project_usage: projectUsage,
    };
  }, { apiOrigin, cases: researchCases });
  batch.usage_invariants = auditOpenRouterFreeUsage(batch.provider_usage || [], 50);

  const resultPath = process.env.VEDA_OPENROUTER_OUTPUT_PATH || resolve(process.cwd(), '../evaluation/openrouter-live-batch-result.json');
  await mkdir(dirname(resultPath), { recursive: true });
  await writeFile(resultPath, `${JSON.stringify({ generated_at: new Date().toISOString(), route: 'openrouter/free', max_usage_records: 50, retries: 0, ...batch }, null, 2)}\n`, 'utf8');

  const completed = batch.results.filter((item) => ['completed', 'completed_with_limitations'].includes(item.job.status));
  await page.getByRole('button', { name: 'Reports' }).click();
  await expect(page.getByRole('heading', { name: 'Report history' })).toBeVisible();
  for (const item of completed) {
    const row = page.locator('.report-history-row').filter({ has: page.getByRole('heading', { name: item.question, exact: true }) });
    await expect(row).toHaveCount(1);
    await row.getByRole('button', { name: 'Open report' }).click();
    await expect(page.getByRole('heading', { name: item.question, exact: true })).toBeVisible();
    await expect(page.locator('.report-content')).toBeVisible();
    const citationIds = Object.keys(item.report.citation_map || {});
    if (citationIds.length > 0) {
      const citation = page.getByRole('button', { name: `Open source ${citationIds[0]}` }).first();
      await expect(citation).toBeVisible();
      await citation.click();
      const drawer = page.locator('.evidence-drawer');
      await expect(drawer).toBeVisible();
      await expect(drawer.locator('.drawer-bottom')).toContainText(/Source metadata from (Crossref|OpenAlex|World Bank Data360|ILOSTAT)/);
      await page.getByRole('button', { name: 'Close source inspector' }).click();
    }
    await page.getByRole('button', { name: 'Report history' }).click();
    await expect(page.getByRole('heading', { name: 'Report history' })).toBeVisible();
  }

  // Keep browser inspection evidence even when some or all jobs failed. A
  // missing report is recorded as incomplete workflow coverage, not as a
  // fabricated report-level success.
  expect(batch.started_cases).toBe(10);
  expect(batch.usage_invariants.total_usage_records_at_or_below_free_test_cap).toBe(true);
  expect(batch.usage_invariants.no_reported_nonzero_cost).toBe(true);
  expect(batch.usage_invariants.accepted_response_count).toBeGreaterThan(0);
  expect(batch.usage_invariants.accepted_responses_report_zero_cost).toBe(true);
  expect(batch.usage_invariants.all_entries_openrouter).toBe(true);
  expect(batch.results.every((item) => item.job)).toBe(true);
  expect(batch.provider_usage.length).toBeGreaterThan(0);
  expect(batch.usage_invariants.model_ids.length).toBeGreaterThan(0);
  expect(batch.usage_invariants.model_ids.every((model: string) => model === 'openrouter/free' || model.endsWith(':free'))).toBe(true);
  expect(completed.length).toBe(10);

  console.info('OpenRouter free-only ten-case Veda result', JSON.stringify({
    outputPath: resultPath,
    completed_jobs: completed.length,
    attempted_jobs: batch.results.length,
    status_counts: batch.results.reduce((counts: Record<string, number>, item: Record<string, any>) => {
      const status = item.job?.status || 'not_created';
      counts[status] = (counts[status] || 0) + 1;
      return counts;
    }, {}),
    provider_calls: batch.provider_usage.length,
    model_ids: batch.usage_invariants.model_ids,
    reported_costs_usd: [...new Set(batch.provider_usage.map((entry: Record<string, any>) => entry.reported_cost_usd))],
    unknown_reported_cost_entries: batch.usage_invariants.unknown_reported_cost_entries,
    total_project_calls: batch.project_usage.model_calls,
    project_estimated_cost_usd: batch.project_usage.estimated_cost_usd,
  }));
});
