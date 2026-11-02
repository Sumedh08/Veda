import AxeBuilder from '@axe-core/playwright';
import { expect, test, type Page, type Route } from '@playwright/test';

const projectId = 'report-history-project';
const archivedProjectId = 'report-history-archived-project';
const jobId = 'report-history-job';
const reportId = 'report-history-report';
const archivedReportId = 'report-history-archived-report';
const passageText = 'The report history preserves this exact cited passage for inspection.';

const project = {
  id: projectId, title: 'Workforce automation', description: 'History fixture', domain: 'Labor economics',
  archived_at: null, created_at: '2026-10-28T09:00:00Z', updated_at: '2026-10-28T09:00:00Z',
};
const archivedProject = {
  ...project, id: archivedProjectId, title: 'Archived productivity review', archived_at: '2026-10-28T10:00:00Z',
};
const profile = {
  name: 'standard', max_queries: 4, max_records_per_provider_query: 20, max_sources: 12,
  max_html_pages: 2, max_pdf_documents: 2, max_html_passages: 20, max_passages: 40,
  max_model_calls: 8, max_prompt_characters_per_call: 24000, max_prompt_characters_total: 80000,
  max_prompt_tokens_per_call: 6000, max_prompt_token_budget_total: 20000,
  max_output_tokens_per_call: 1500, max_output_token_budget_total: 5000,
  max_retries: 1, max_step_seconds: 20,
};
const job = {
  schema_version: 1,
  id: jobId, project_id: projectId, parent_job_id: null, conversation_id: null,
  question: 'What evidence links automation to wages?', scope: { schema_version: 1, extensions: {} }, depth: 'standard',
  budget_ceiling_usd: 0, cost_spent_estimate_usd: 0, cost_reserved_usd: 0,
  model_calls_reserved: 0, prompt_characters_reserved: 0, prompt_token_budget_reserved: 0,
  output_token_budget_reserved: 0, resource_limits: profile, status: 'completed_with_limitations',
  current_stage: 'complete', version: 8, attempt: 1, error_class: null, error_message: null,
  created_at: '2026-10-28T09:10:00Z', updated_at: '2026-10-28T09:15:00Z',
};
const source = {
  id: 'report-history-source', title: 'Automation and wage outcomes', doi: '10.5555/history-fixture',
  url: 'https://example.org/history-fixture', authors: [{ name: 'Researcher' }], published_year: 2025,
  publisher: 'Example Journal', provider: 'fixture', source_type: 'scholarly_article',
  retrieval_status: 'abstract_only', retrieval: {}, abstract_excerpt: passageText, appraisal: {},
  passages: [{ id: 'report-history-passage', source_id: 'report-history-source', ordinal: 0,
    locator: 'abstract sentence 1', content: passageText, content_hash: 'fixture-hash',
    access_level: 'abstract_excerpt', truncated: false }],
};
const report = {
  id: reportId, job_id: jobId, version: 2, citation_map_schema_version: 1, verification_schema_version: 1,
  status: 'completed_with_limitations',
  body_markdown: '# Evidence map\n\nA source reports a bounded result [S1].\n\n## Limitations\n\nThis fixture is not a research finding.',
  citation_map: { S1: { source_id: source.id, title: source.title, doi: source.doi, url: source.url, passages: [source.passages[0].id] } },
  verification: {
    status: 'passed', report_schema_version: 2, level: 'deterministic_link_integrity_only',
    claims_checked: 1, claims_with_valid_source_and_passage: 1,
    semantic_support_check: 'not_performed', uncited_material_claim_scan: 'not_performed',
    citation_link_integrity: {
      schema_version: 1, level: 'deterministic_link_integrity_only', status: 'passed',
      claims_checked: 1, claims_with_valid_source_and_passage: 1,
    },
    semantic_assessment: {
      schema_version: 1, method: 'not_performed', support_check: 'not_performed',
      uncited_material_claim_scan: 'not_performed', provider: null, model: null,
      audit_schema_version: null, items: [], uncited_claims: [], rejected_records: 0,
      input_truncated: false, skip_reason: null,
    },
  },
  model_name: 'fixture-model',
  created_at: '2026-10-28T09:15:00Z',
};

function json(route: Route, body: unknown, status = 200) {
  return route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });
}

async function installReportHistoryApi(page: Page, scenario: 'default' | 'empty' | 'paged' | 'retry' = 'default') {
  const requestedExports: string[] = [];
  let failedReportRequests = scenario === 'retry' ? 2 : 0;
  await page.route('**/api/v1/**', async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname.replace('/api/v1', '');
    if (path === '/auth/dev-session') return json(route, { access_token: 'report-history-browser-fixture' });
    if (path === '/projects' && url.searchParams.get('archived_only') === 'true') {
      return json(route, { items: [archivedProject], limit: 100, offset: 0 });
    }
    if (path === '/projects') return json(route, { items: [project], limit: 100, offset: 0 });
    if (path === '/reports') {
      if (failedReportRequests > 0) {
        failedReportRequests -= 1;
        return json(route, { detail: 'Report service temporarily unavailable.' }, 503);
      }
      if (scenario === 'empty') return json(route, { items: [], total: 0, limit: 10, offset: 0, has_more: false, version_semantics: 'One report per immutable run.' });
      if (scenario === 'paged') {
        const offset = Number(url.searchParams.get('offset') || 0);
        const items = offset === 0
          ? Array.from({ length: 10 }, (_, index) => ({ ...reportItem(), id: `report-history-page-${index}`, question: `Page one research question ${index + 1}` }))
          : [{ ...reportItem(), id: 'report-history-page-final', question: 'Page two final report' }];
        return json(route, { items, total: 11, limit: 10, offset, has_more: offset === 0, version_semantics: 'One report per immutable run.' });
      }
      const includeArchived = url.searchParams.get('include_archived') === 'true';
      const projectFilter = url.searchParams.get('project_id');
      const allItems = includeArchived ? [reportItem(), archivedReportItem()] : [reportItem()];
      const items = projectFilter ? allItems.filter((item) => item.project_id === projectFilter) : allItems;
      return json(route, { items, total: items.length, limit: 10, offset: Number(url.searchParams.get('offset') || 0), has_more: false,
        version_semantics: 'Each immutable research run has one report; version is its report-schema version.' });
    }
    if (path === `/reports/${reportId}/inspection`) return json(route, { report, job, project, sources: [source], claims: [] });
    if (path === `/reports/${archivedReportId}/inspection`) return json(route, {
      report: { ...report, id: archivedReportId }, job: { ...job, id: 'archived-report-history-job', project_id: archivedProjectId },
      project: archivedProject, sources: [source], claims: [],
    });
    if (path.startsWith('/reports/') && path.endsWith('/export')) {
      requestedExports.push(path);
      return route.fulfill({ status: 200, contentType: 'text/markdown', body: report.body_markdown });
    }
    return json(route, { detail: `Unexpected fixture request: ${request.method()} ${path}` }, 404);
  });
  return requestedExports;
}

function reportItem() {
  return { ...report, project_id: projectId, project_title: project.title, project_archived_at: null, question: job.question };
}
function archivedReportItem() {
  return { ...report, id: archivedReportId, job_id: 'archived-report-history-job', project_id: archivedProjectId,
    project_title: archivedProject.title, project_archived_at: archivedProject.archived_at,
    question: 'What did the archived productivity review find?' };
}

async function openHistory(page: Page) {
  await installReportHistoryApi(page);
  await page.goto('/');
  await page.getByRole('button', { name: 'Continue to local workspace' }).click();
  if (await page.getByRole('button', { name: 'Open navigation' }).isVisible()) {
    await page.getByRole('button', { name: 'Open navigation' }).click();
  }
  await page.getByRole('button', { name: 'Reports' }).click();
  await expect(page.getByRole('heading', { name: 'Report history' })).toBeVisible();
}

async function expectNoAxeViolations(page: Page) {
  const results = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa']).analyze();
  expect(results.violations.map((item) => `${item.id}: ${item.help}`)).toEqual([]);
}

test('report history filters archived runs and opens citations and export for the selected immutable report', async ({ page }) => {
  const requestedExports = await installReportHistoryApi(page);
  await page.goto('/');
  await page.getByRole('button', { name: 'Continue to local workspace' }).click();
  if (await page.getByRole('button', { name: 'Open navigation' }).isVisible()) {
    await page.getByRole('button', { name: 'Open navigation' }).click();
  }
  await page.getByRole('button', { name: 'Reports' }).click();
  await expect(page.getByText(job.question)).toBeVisible();
  await expect(page.getByText(/Schema v2/)).toBeVisible();
  await page.getByLabel('Filter reports by project').selectOption(archivedProjectId);
  await expect(page.getByText('What did the archived productivity review find?')).toBeVisible();
  await expect(page.getByLabel('Include archived projects')).toBeChecked();
  await expect(page.getByText(job.question)).toHaveCount(0);
  await page.getByLabel('Filter reports by project').selectOption('');
  await page.getByLabel('Include archived projects').check();
  await expect(page.getByText('What did the archived productivity review find?')).toBeVisible();
  await page.getByRole('button', { name: 'Open report' }).first().click();
  await expect(page.getByRole('heading', { name: 'Preliminary evidence map' })).toBeVisible();
  const citation = page.getByRole('button', { name: 'Open source S1' });
  await expect(citation).toBeVisible();
  await citation.click();
  await expect(page.getByRole('dialog', { name: 'Automation and wage outcomes' })).toBeVisible();
  await expect(page.getByText(passageText, { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Close source inspector' }).click();
  const downloadPromise = page.waitForEvent('download');
  await page.getByRole('button', { name: 'Markdown' }).click();
  const download = await downloadPromise;
  expect(download.suggestedFilename()).toBe(`veda-report-${reportId}.md`);
  expect(requestedExports).toEqual([`/reports/${reportId}/export`]);
});

test('report history remains accessible and fits a narrow viewport', async ({ page }) => {
  await page.setViewportSize({ width: 360, height: 800 });
  await openHistory(page);
  await expectNoAxeViolations(page);
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth);
  expect(overflow).toBe(false);
});

test('report history navigates bounded pages in both directions with stable totals', async ({ page }) => {
  await installReportHistoryApi(page, 'paged');
  await page.goto('/');
  await page.getByRole('button', { name: 'Continue to local workspace' }).click();
  await page.getByRole('button', { name: 'Reports' }).click();
  await expect(page.getByRole('heading', { name: 'Page one research question 1', exact: true })).toBeVisible();
  await expect(page.getByText('Showing 1–10 of 11')).toBeVisible();
  await page.getByRole('button', { name: 'Next' }).click();
  await expect(page.getByText('Page two final report')).toBeVisible();
  await expect(page.getByText('Showing 11–11 of 11')).toBeVisible();
  await page.getByRole('button', { name: 'Previous' }).click();
  await expect(page.getByRole('heading', { name: 'Page one research question 1', exact: true })).toBeVisible();
});

test('report history shows an empty state with stable zero pagination', async ({ page }) => {
  await installReportHistoryApi(page, 'empty');
  await page.goto('/');
  await page.getByRole('button', { name: 'Continue to local workspace' }).click();
  await page.getByRole('button', { name: 'Reports' }).click();
  await expect(page.getByText('No saved reports yet. Completed research runs will appear here.')).toBeVisible();
  await expect(page.getByText('Showing 0–0 of 0')).toBeVisible();
});

test('report history recovers from a list API failure on retry', async ({ page }) => {
  await installReportHistoryApi(page, 'retry');
  await page.goto('/');
  await page.getByRole('button', { name: 'Continue to local workspace' }).click();
  await page.getByRole('button', { name: 'Reports' }).click();
  await expect(page.getByText('Report service temporarily unavailable.', { exact: true }).first()).toBeVisible();
  await page.getByRole('button', { name: 'Retry' }).click();
  await expect(page.getByText(job.question)).toBeVisible();
});
