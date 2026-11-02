import { expect, test } from '@playwright/test';

test.describe.configure({ lock: 'veda-real-api-sqlite' });

test.skip(
  process.env.VEDA_REAL_API_E2E !== '1',
  'Run with the isolated real API server enabled.',
);

test('continues a saved deferred publisher fetch into inspectable report evidence', async ({ page }) => {
  const parentJobId = process.env.VEDA_LIVE_DEFERRED_JOB_ID;
  const savedChildJobId = process.env.VEDA_LIVE_DEFERRED_CHILD_JOB_ID;
  test.skip(!parentJobId, 'Requires an isolated evaluation DB with a due deferred HTML fetch.');
  test.setTimeout(300_000);

  const apiOrigin = new URL(
    process.env.VEDA_E2E_API_BASE_URL ||
      `http://127.0.0.1:${process.env.VEDA_REAL_E2E_API_PORT || '8001'}/api/v1`,
  ).origin;
  const targetDoi = '10.3389/fenrg.2026.1779158';
  const apiResponses: Array<{ path: string; method: string; status: number }> = [];
  page.on('response', (response) => {
    const url = new URL(response.url());
    if (url.pathname.startsWith('/api/v1/')) {
      apiResponses.push({ path: url.pathname, method: response.request().method(), status: response.status() });
    }
  });

  await page.goto('/');
  await page.getByRole('button', { name: 'Continue to local workspace' }).click();
  await page.locator('.project-grid').getByRole('button', {
    name: /Local browser integration \(synthetic data\)/,
  }).click();
  let childJobId: string;
  let report: {
    id: string;
    status: string;
    citation_map: Record<string, { source_id?: string; doi?: string | null }>;
    verification: { semantic_support_check: string };
  };
  if (savedChildJobId) {
    const savedChild = await page.evaluate(async ({ apiOrigin, parentJobId, savedChildJobId }) => {
      const session = JSON.parse(sessionStorage.getItem('veda_local_session') || '{}') as { token?: string };
      const headers = session.token ? { Authorization: `Bearer ${session.token}` } : {};
      const response = await fetch(`${apiOrigin}/api/v1/research-jobs/${savedChildJobId}`, {
        headers,
      });
      if (!response.ok) return null;
      const job = await response.json() as {
        id: string;
        project_id: string;
        parent_job_id: string | null;
        question: string;
        status: string;
      };
      if (job.parent_job_id !== parentJobId || !['completed', 'completed_with_limitations'].includes(job.status)) {
        return null;
      }
      const listResponse = await fetch(`${apiOrigin}/api/v1/projects/${job.project_id}/research-jobs`, {
        headers: session.token ? { Authorization: `Bearer ${session.token}` } : {},
      });
      if (!listResponse.ok) return null;
      const jobs = await listResponse.json() as { items: Array<{ id: string }> };
      return { job, rowIndex: jobs.items.findIndex((item) => item.id === savedChildJobId) };
    }, { apiOrigin, parentJobId, savedChildJobId });
    expect(savedChild).toBeTruthy();
    expect(savedChild!.rowIndex).toBeGreaterThanOrEqual(0);
    childJobId = savedChildJobId;
    await page.locator('.job-row').nth(savedChild!.rowIndex).click();
    await expect(page.getByRole('heading', { name: savedChild!.job.question })).toBeVisible();
    const response = await page.evaluate(async ({ apiOrigin, childJobId }) => {
      const session = JSON.parse(sessionStorage.getItem('veda_local_session') || '{}') as { token?: string };
      const result = await fetch(`${apiOrigin}/api/v1/research-jobs/${childJobId}/report`, {
        headers: session.token ? { Authorization: `Bearer ${session.token}` } : {},
      });
      return { status: result.status, report: await result.json() };
    }, { apiOrigin, childJobId });
    expect(response.status).toBe(200);
    report = response.report;
  } else {
    const parentRow = page.locator('.job-row').filter({ hasText: parentJobId });
    if (await parentRow.count() === 0) {
      // The public UI labels runs by question, while the ID is kept for selecting
      // an exact historical run without accidentally resuming another report.
      const parent = await page.evaluate(async ({ apiOrigin, parentJobId }) => {
        const session = JSON.parse(sessionStorage.getItem('veda_local_session') || '{}') as { token?: string };
        const response = await fetch(`${apiOrigin}/api/v1/research-jobs/${parentJobId}`, {
          headers: session.token ? { Authorization: `Bearer ${session.token}` } : {},
        });
        if (!response.ok) return null;
        return await response.json() as { question: string };
      }, { apiOrigin, parentJobId });
      expect(parent).toBeTruthy();
      await page.locator('.job-row').filter({ hasText: parent!.question }).click();
    } else {
      await parentRow.click();
    }

    const continueButton = page.getByRole('button', { name: /Continue deferred retrieval/ });
    await expect(continueButton).toBeVisible();
    await expect(continueButton).toBeEnabled();
    const continuationResponsePromise = page.waitForResponse((response) =>
      response.request().method() === 'POST' &&
      new URL(response.url()).pathname === `/api/v1/research-jobs/${parentJobId}/retry-deferred`,
    );
    await continueButton.click();
    const continuationResponse = await continuationResponsePromise;
    expect(continuationResponse.status()).toBe(200);
    const continuation = await continuationResponse.json() as {
      job: { id: string; status: string; current_stage: string };
      queued_retry_count: number;
    };
    expect(continuation.queued_retry_count).toBeGreaterThan(0);
    childJobId = continuation.job.id;
    expect(childJobId).not.toBe(parentJobId);
    await expect(page.getByRole('heading', {
      name: 'What technical and grid-integration challenges affect offshore hybrid renewable energy systems, and what evidence describes real-world implementations?',
    })).toBeVisible();

    const childReportResponsePromise = page.waitForResponse((response) =>
      response.request().method() === 'GET' &&
      new URL(response.url()).pathname === `/api/v1/research-jobs/${childJobId}/report`,
      { timeout: 240_000 },
    );
    await page.getByRole('button', { name: 'Run while open' }).click();
    const childReportResponse = await childReportResponsePromise;
    expect(childReportResponse.status()).toBe(200);
    report = await childReportResponse.json() as typeof report;
  }
  expect(['completed', 'completed_with_limitations']).toContain(report.status);
  expect(report.verification.semantic_support_check).toBe('not_performed');

  const targetCitation = Object.entries(report.citation_map).find(([, citation]) =>
    citation.doi?.toLowerCase() === targetDoi,
  );
  expect(targetCitation, 'the continued report must cite the retrieved publisher source').toBeTruthy();
  const [citationKey, citation] = targetCitation!;
  expect(citation.source_id).toBeTruthy();
  const source = await page.evaluate(async ({ apiOrigin, sourceId }) => {
    const session = JSON.parse(sessionStorage.getItem('veda_local_session') || '{}') as { token?: string };
    const response = await fetch(`${apiOrigin}/api/v1/sources/${sourceId}`, {
      headers: session.token ? { Authorization: `Bearer ${session.token}` } : {},
    });
    return { status: response.status, body: await response.json() as {
      title: string;
      retrieval_status: string;
      retrieval: {
        status?: string;
        site_policy_status?: string;
        document_sha256?: string;
        license?: string;
        crawl4ai_page?: {
          request_count?: number;
          preflight_request_count?: number;
          reported_cost_credits?: number | null;
          reported_cost_status?: string;
          scrape_reported_cost_credits?: number | null;
          unresolved_reserved_credits?: number;
        };
      };
      passages: Array<{ content: string; locator: string }>;
    } };
  }, { apiOrigin, sourceId: citation.source_id! });
  expect(source.status).toBe(200);
  expect(source.body.retrieval_status).toBe('full_text_html');
  expect(source.body.retrieval.site_policy_status).toBe('allowed');
  expect(source.body.retrieval.document_sha256).toMatch(/^[a-f0-9]{64}$/);
  expect(source.body.retrieval.crawl4ai_page?.reported_cost_status).toBe('partial');
  expect(source.body.retrieval.crawl4ai_page?.scrape_reported_cost_credits).toBe(0.25);
  expect(source.body.retrieval.crawl4ai_page?.unresolved_reserved_credits).toBe(1);
  expect(source.body.passages.length).toBeGreaterThan(0);
  expect(source.body.passages.some((passage) =>
    /systematic review of literature and industry data|capacity factors of up to 45%/i.test(passage.content),
  )).toBe(true);
  expect(source.body.passages.some((passage) => /comprehensive research .* current state of the art/i.test(passage.content))).toBe(true);
  expect(source.body.passages.some((passage) => /grid stability|smart-grid integration/i.test(passage.content))).toBe(true);
  expect(source.body.passages.every((passage) =>
    !/^(?:Front\.|Energy Res\.|Sec\.|Volume\s+\d|Nisha Kaur|K\. Sudhakar|Faculty of|School of)/i.test(passage.content.trim()),
  )).toBe(true);

  await page.getByRole('tab', { name: /report/i }).click();
  await expect(page.locator('.report-content')).toContainText('Search coverage');
  await page.getByRole('button', { name: `Open source ${citationKey}` }).first().click();
  const inspector = page.locator('.evidence-drawer');
  await expect(inspector).toBeVisible();
  await expect(inspector).toContainText('full text html');
  await expect(inspector).toContainText('permitted');
  await expect(inspector).toContainText('frontiers-open-access-2026-11-01');
  await expect(inspector.locator('.passage-stack')).toContainText(
    /systematic review of literature and industry data|capacity factors of up to 45%/i,
  );
  await expect(inspector.locator('.passage-stack')).not.toContainText(/Nisha Kaur|Volume 14|Energy Res\./i);

  if (!savedChildJobId) {
    expect(apiResponses.some((response) =>
      response.path === `/api/v1/research-jobs/${parentJobId}/retry-deferred` && response.status === 200,
    )).toBe(true);
  }
  expect(apiResponses.some((response) =>
    response.path === `/api/v1/research-jobs/${childJobId}/report` && response.status === 200,
  )).toBe(true);
  expect(apiResponses.every((response) => response.status < 400)).toBe(true);
  console.info('Deferred publisher report inspected', JSON.stringify({
    parentJobId,
    childJobId,
    reportId: report.id,
    sourceId: citation.source_id,
    doi: targetDoi,
    retrievalStatus: source.body.retrieval_status,
    passageCount: source.body.passages.length,
    modelCalls: 0,
    crawl4aiContentRequests: source.body.retrieval.crawl4ai_page?.request_count ?? 0,
    crawl4aiPreflightRequests: source.body.retrieval.crawl4ai_page?.preflight_request_count ?? 0,
    crawl4aiReportedCredits: source.body.retrieval.crawl4ai_page?.scrape_reported_cost_credits ?? null,
    crawl4aiUnresolvedReservedCredits:
      source.body.retrieval.crawl4ai_page?.unresolved_reserved_credits ?? null,
  }));
});
