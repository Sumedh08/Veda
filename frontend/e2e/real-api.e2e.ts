import { expect, test } from '@playwright/test';

// These journeys share one ephemeral SQLite API server in real-API mode.
test.describe.configure({ lock: 'veda-real-api-sqlite' });

test.skip(
  process.env.VEDA_REAL_API_E2E !== '1',
  'Run with VEDA_REAL_API_E2E=1 to boot the isolated SQLite-backed local API.',
);

test('browser receives a validated server request reference through real CORS', async ({ page }) => {
  await page.goto('/');
  const failure = await page.evaluate(async () => {
    const { api } = await import('/src/api.ts');
    try {
      await api('/__request_reference_contract_probe__');
      return null;
    } catch (error) {
      const apiError = error as Error & { status?: number; code?: string | null; requestId?: string | null };
      return {
        name: apiError.name,
        message: apiError.message,
        status: apiError.status,
        code: apiError.code,
        requestId: apiError.requestId,
      };
    }
  });

  expect(failure).not.toBeNull();
  expect(failure).toMatchObject({ name: 'ApiError', status: 404, code: null });
  expect(failure?.requestId).toMatch(/^[A-Za-z0-9._:-]{1,128}$/);
  expect(failure?.message).toContain(`Reference ID: ${failure?.requestId}`);
});

test('browser receives a consistent request reference for an oversized request through real CORS', async ({ page }) => {
  await page.goto('/');
  const failure = await page.evaluate(async () => {
    const { api } = await import('/src/api.ts');
    const requestId = 'e2e-body-limit-96';
    try {
      await api('/projects', {
        method: 'POST',
        headers: { 'X-Request-ID': requestId },
        body: JSON.stringify({ title: 'x'.repeat(1_048_576 + 10), domain: 'test' }),
      });
      return null;
    } catch (error) {
      const apiError = error as Error & {
        status?: number;
        code?: string | null;
        requestId?: string | null;
      };
      return {
        name: apiError.name,
        message: apiError.message,
        status: apiError.status,
        code: apiError.code,
        requestId: apiError.requestId,
      };
    }
  });

  expect(failure).toMatchObject({
    name: 'ApiError',
    status: 413,
    code: 'request_too_large',
    requestId: 'e2e-body-limit-96',
  });
  expect(failure?.message).toContain(`Reference ID: ${failure?.requestId}`);
});

test('real browser session opens a persisted synthetic report citation through the API', async ({ page }) => {
  const expectedApiOrigin = new URL(
    process.env.VEDA_E2E_API_BASE_URL ||
      `http://127.0.0.1:${process.env.VEDA_REAL_E2E_API_PORT || '8001'}/api/v1`,
  ).origin;
  const apiResponses: { url: string; status: number }[] = [];
  page.on('response', (response) => {
    const url = new URL(response.url());
    if (url.pathname.startsWith('/api/v1/')) {
      apiResponses.push({ url: response.url(), status: response.status() });
    }
  });

  // No route interception is installed in this journey. Every API response
  // must come from the isolated Veda process started by Playwright config.
  await page.goto('/');
  await page.getByRole('button', { name: 'Continue to local workspace' }).click();
  await expect(page.locator('.project-grid')).toContainText('Local browser integration (synthetic data)');
  await page.getByRole('button', { name: 'Reports' }).click();
  await expect(page.getByRole('heading', { name: /Synthetic browser\/API citation-inspection test/ })).toBeVisible();
  await page.getByRole('button', { name: 'Open report' }).click();
  await expect(page.getByRole('heading', { name: 'Synthetic Browser Integration Fixture' })).toBeVisible();
  await expect(page.getByText('It contains no research finding. Citation checks are marked needs review.')).toBeVisible();

  const citation = page.getByRole('button', { name: 'Open source S1' });
  await expect(citation).toBeVisible();
  await citation.click();
  const inspector = page.getByRole('dialog', { name: 'Synthetic Browser Integration Source — TEST DATA' });
  await expect(inspector).toBeVisible();
  await expect(inspector.getByText(
    'Synthetic integration text for checking the real API-to-browser citation inspector. This is not a paper excerpt or a research finding.',
    { exact: true },
  )).toBeVisible();

  const apiPaths = apiResponses.map(({ url }) => new URL(url).pathname);
  expect(apiPaths).toContain('/api/v1/auth/dev-session');
  expect(apiPaths).toContain('/api/v1/reports');
  expect(apiPaths.some((path) => /^\/api\/v1\/reports\/[^/]+\/inspection$/.test(path))).toBe(true);
  expect(apiResponses.every(({ url, status }) => new URL(url).origin === expectedApiOrigin && status < 400)).toBe(true);
});

test('browser inspects the preserved ORE Catapult discovery report and full-text passage', async ({ page }) => {
  test.skip(
    !process.env.VEDA_REAL_E2E_REUSE_DATABASE_PATH || !process.env.VEDA_REAL_E2E_REPORT_ID,
    'Set an existing evaluation database path and report ID to inspect a preserved real report.',
  );
  const expectedApiOrigin = new URL(
    process.env.VEDA_E2E_API_BASE_URL ||
      `http://127.0.0.1:${process.env.VEDA_REAL_E2E_API_PORT || '8001'}/api/v1`,
  ).origin;
  const reportId = process.env.VEDA_REAL_E2E_REPORT_ID!;
  const question = process.env.VEDA_REAL_E2E_REPORT_QUESTION!;
  const apiResponses: { url: string; status: number; method: string }[] = [];
  page.on('response', (response) => {
    const url = new URL(response.url());
    if (url.pathname.startsWith('/api/v1/')) {
      apiResponses.push({ url: response.url(), status: response.status(), method: response.request().method() });
    }
  });

  await page.goto('/');
  await page.getByRole('button', { name: 'Continue to local workspace' }).click();
  await expect(page.locator('.project-grid')).toBeVisible();
  const savedReport = await page.evaluate(async ({ apiOrigin, expectedReportId }) => {
    const session = JSON.parse(sessionStorage.getItem('veda_local_session') || '{}') as { token?: string };
    const response = await fetch(`${apiOrigin}/api/v1/reports?limit=50`, {
      headers: session.token ? { Authorization: `Bearer ${session.token}` } : {},
    });
    if (!response.ok) throw new Error(`Saved report listing returned ${response.status}`);
    const body = await response.json() as { items: Array<{ id: string; question: string }> };
    return body.items.find((item) => item.id === expectedReportId) || null;
  }, { apiOrigin: expectedApiOrigin, expectedReportId: reportId });
  expect(savedReport?.question).toBe(question);

  await page.getByRole('button', { name: 'Reports' }).click();
  const reportRow = page.locator('.report-history-row').filter({ hasText: question });
  await expect(reportRow).toBeVisible();
  await reportRow.getByRole('button', { name: 'Open report' }).click();
  await expect(page.locator('.historical-report-heading')).toContainText(question);
  await expect(page.locator('.report-content')).toContainText('Preliminary evidence map');
  await expect(page.locator('.report-content')).toContainText('converter topology');

  await page.getByRole('button', { name: 'Open source S1' }).first().click();
  const inspector = page.getByRole('dialog', {
    name: 'Hybrid, Multi-Megawatt HVDC Transformer Topology Comparison for Future Offshore Wind Farms',
  });
  await expect(inspector).toBeVisible();
  await expect(inspector).toContainText('PDF page 1, sentence 2');
  await expect(inspector).toContainText(
    'HVDC transformer substations are not optimized for the offshore industry though',
  );
  await expect(inspector).toContainText('Document SHA-256');
  await expect(inspector).toContainText('strathprints.strath.ac.uk');
  await expect(inspector).toContainText('exact DOI/title OpenAIRE instance');
  await expect(inspector).toContainText('REQUIRES_REVIEW');
  await expect(inspector).toContainText(/15 extracted \/ 15.*capped/);
  await inspector.getByRole('button', { name: 'Close source inspector' }).click();

  await page.getByRole('button', { name: 'Open source S12' }).first().click();
  const officialInspector = page.getByRole('dialog', {
    name: 'Offshore wind net zero investment roadmap',
  });
  await expect(officialInspector).toBeVisible();
  await expect(officialInspector).toContainText('Official publication metadata');
  await expect(officialInspector).toContainText(
    'Department for Energy Security and Net Zero · VERIFIED ESTABLISHED · publisher identity only; quality not assessed.',
  );
  await expect(officialInspector).toContainText(
    'The linked report attachment was not fetched',
  );
  await expect(officialInspector.getByText('Not performed', { exact: true })).toBeVisible();
  await expect(
    officialInspector.getByRole('link', { name: 'Official directory' }),
  ).toHaveAttribute(
    'href',
    'https://www.gov.uk/government/organisations/department-for-energy-security-and-net-zero',
  );

  expect(apiResponses.some((item) => new URL(item.url).pathname === '/api/v1/reports')).toBe(true);
  expect(apiResponses.some((item) => new URL(item.url).pathname === `/api/v1/reports/${reportId}/inspection`)).toBe(true);
  expect(apiResponses.every((item) => new URL(item.url).origin === expectedApiOrigin && item.status < 400)).toBe(true);
  expect(apiResponses.filter((item) => item.method !== 'GET').map((item) => new URL(item.url).pathname))
    .toEqual(['/api/v1/auth/dev-session']);
});

test('real browser project name and user-authored brief persist through create, edit, and reload', async ({ page }) => {
  const expectedApiOrigin = new URL(
    process.env.VEDA_E2E_API_BASE_URL ||
      `http://127.0.0.1:${process.env.VEDA_REAL_E2E_API_PORT || '8001'}/api/v1`,
  ).origin;
  const apiResponses: { url: string; status: number; method: string }[] = [];
  page.on('response', (response) => {
    const url = new URL(response.url());
    if (url.pathname.startsWith('/api/v1/')) {
      apiResponses.push({ url: response.url(), status: response.status(), method: response.request().method() });
    }
  });

  // This test also makes no route interception or API substitution.
  await page.goto('/');
  await page.getByRole('button', { name: 'Continue to local workspace' }).click();
  await expect(page.locator('.project-grid')).toContainText('Local browser integration (synthetic data)');
  await page.locator('.section-actions').getByRole('button', { name: 'New project' }).click();

  const originalTitle = 'Real API project persistence';
  const updatedTitle = 'Real API project persistence after edit';
  const originalBrief = 'Synthetic user-authored brief before an edit.';
  const updatedBrief = 'Synthetic user-authored brief saved by the real API and checked after reload.';
  const createDialog = page.getByRole('dialog', { name: 'Create a research project' });
  await createDialog.getByLabel('Project name').fill(originalTitle);
  await createDialog.getByLabel('Persistent project brief').fill(originalBrief);
  await createDialog.getByRole('button', { name: 'Create project' }).click();
  await expect(page.getByRole('heading', { name: originalTitle, exact: true })).toBeVisible();

  await page.getByRole('button', { name: 'Edit project' }).click();
  const editDialog = page.getByRole('dialog', { name: 'Edit research project' });
  await editDialog.getByLabel('Project name').fill(updatedTitle);
  await editDialog.getByLabel('Persistent project brief').fill(updatedBrief);
  await editDialog.getByRole('button', { name: 'Save changes' }).click();
  await expect(page.getByRole('heading', { name: updatedTitle, exact: true })).toBeVisible();
  await expect(page.getByText(updatedBrief, { exact: true })).toBeVisible();

  await page.reload();
  const savedProject = page.locator('.project-grid').getByRole('button', { name: new RegExp(updatedTitle) });
  await expect(savedProject).toBeVisible();
  await savedProject.click();
  await expect(page.getByRole('heading', { name: updatedTitle, exact: true })).toBeVisible();
  await expect(page.getByText(updatedBrief, { exact: true })).toBeVisible();

  const responses = apiResponses.map(({ url, method, status }) => ({
    path: new URL(url).pathname,
    origin: new URL(url).origin,
    method,
    status,
  }));
  expect(responses.some((item) => item.method === 'POST' && item.path === '/api/v1/projects' && item.status === 201)).toBe(true);
  expect(responses.some((item) => item.method === 'PATCH' && /^\/api\/v1\/projects\/[\da-f-]+$/.test(item.path) && item.status === 200)).toBe(true);
  expect(responses.filter((item) => item.method === 'GET' && item.path === '/api/v1/projects').length).toBeGreaterThan(1);
  expect(responses.every((item) => item.origin === expectedApiOrigin && item.status < 400)).toBe(true);
});

test('real browser saves one deterministic plan and restores it after refresh without starting discovery', async ({ page }) => {
  const expectedApiOrigin = new URL(
    process.env.VEDA_E2E_API_BASE_URL ||
      `http://127.0.0.1:${process.env.VEDA_REAL_E2E_API_PORT || '8001'}/api/v1`,
  ).origin;
  const apiResponses: { url: string; status: number; method: string }[] = [];
  page.on('response', (response) => {
    const url = new URL(response.url());
    if (url.pathname.startsWith('/api/v1/')) {
      apiResponses.push({ url: response.url(), status: response.status(), method: response.request().method() });
    }
  });

  // The API server is provider-disabled. This journey stops at planning and
  // does not install route handlers or advance into external scholarly search.
  await page.goto('/');
  await page.getByRole('button', { name: 'Continue to local workspace' }).click();
  const seededProject = page.locator('.project-grid').getByRole('button', { name: /Local browser integration \(synthetic data\)/ });
  await expect(seededProject).toBeVisible();
  await seededProject.click();
  await page.getByRole('button', { name: 'Start research' }).click();

  const question = 'Synthetic plan checkpoint recovery test — not a research question';
  const composer = page.locator('.modal-card');
  await composer.getByLabel('Research question').fill(question);
  await composer.getByLabel(/Decision context/).fill('Synthetic browser/API workflow test data only.');
  await composer.getByRole('button', { name: 'Start research' }).click();
  await expect(page.getByRole('heading', { name: question })).toBeVisible();
  await expect(page.getByText('The plan will appear after the first research step is saved.')).toBeVisible();

  await page.getByRole('button', { name: 'Next step' }).click();
  await expect(page.locator('.plan-card')).toContainText('Questions to investigate');
  await expect(page.locator('.plan-method')).toContainText(/Deterministic/);
  await expect(page.locator('.job-view')).toContainText('Discovering scholarly sources');
  await expect(page.locator('.coverage-number')).toContainText('0');

  const advanceRequests = () => apiResponses.filter(({ url, method }) =>
    method === 'POST' && new URL(url).pathname.match(/^\/api\/v1\/research-jobs\/[^/]+\/advance$/),
  );
  expect(advanceRequests()).toHaveLength(1);

  await page.reload();
  await page.locator('.project-grid').getByRole('button', { name: /Local browser integration \(synthetic data\)/ }).click();
  const savedRun = page.locator('.job-list').getByRole('button', { name: new RegExp(question) });
  await expect(savedRun).toBeVisible();
  await savedRun.click();
  await expect(page.getByRole('heading', { name: question })).toBeVisible();
  await expect(page.locator('.plan-method')).toContainText(/Deterministic/);
  await expect(page.locator('.plan-card')).toContainText('Synthetic browser/API workflow test data only.');
  await expect(page.locator('.job-view')).toContainText('Discovering scholarly sources');
  await expect(page.locator('.coverage-number')).toContainText('0');
  expect(advanceRequests()).toHaveLength(1);

  const responses = apiResponses.map(({ url, method, status }) => ({
    path: new URL(url).pathname,
    origin: new URL(url).origin,
    method,
    status,
  }));
  expect(responses.some((item) => item.method === 'POST' && /^\/api\/v1\/projects\/[^/]+\/research-jobs$/.test(item.path) && item.status === 201)).toBe(true);
  expect(responses.some((item) => item.method === 'GET' && /^\/api\/v1\/research-jobs\/[^/]+\/plan$/.test(item.path) && item.status === 200)).toBe(true);
  expect(responses.some((item) => item.method === 'GET' && /^\/api\/v1\/research-jobs\/[^/]+\/events$/.test(item.path) && item.status === 200)).toBe(true);
  expect(responses.every((item) => item.origin === expectedApiOrigin && item.status < 400)).toBe(true);
});

test('real browser follow-up preserves parent lineage and conversation context after reload', async ({ page }) => {
  const expectedApiOrigin = new URL(
    process.env.VEDA_E2E_API_BASE_URL ||
      `http://127.0.0.1:${process.env.VEDA_REAL_E2E_API_PORT || '8001'}/api/v1`,
  ).origin;
  const apiResponses: { url: string; status: number; method: string }[] = [];
  page.on('response', (response) => {
    const url = new URL(response.url());
    if (url.pathname.startsWith('/api/v1/')) {
      apiResponses.push({ url: response.url(), status: response.status(), method: response.request().method() });
    }
  });

  // Use the real local API and the isolated provider-disabled database. Both
  // questions are synthetic integration labels, not research findings.
  await page.goto('/');
  await page.getByRole('button', { name: 'Continue to local workspace' }).click();
  const projectButton = page.locator('.project-grid').getByRole('button', { name: /Local browser integration \(synthetic data\)/ });
  await expect(projectButton).toBeVisible();
  await projectButton.click();
  await page.getByRole('button', { name: 'Start research' }).click();

  const parentQuestion = 'Synthetic parent run for persistent follow-up lineage verification';
  const composer = page.locator('.modal-card');
  await composer.getByLabel('Research question').fill(parentQuestion);
  await composer.getByLabel(/Decision context/).fill('Synthetic parent context; no evidence claim.');
  const parentCreatePromise = page.waitForResponse((response) =>
    response.request().method() === 'POST' && new URL(response.url()).pathname.match(/^\/api\/v1\/projects\/[^/]+\/research-jobs$/) !== null,
  );
  await composer.getByRole('button', { name: 'Start research' }).click();
  const parentResponse = await parentCreatePromise;
  expect(parentResponse.status()).toBe(201);
  const parent = await parentResponse.json() as { id: string; conversation_id: string };
  expect(parent.id).toBeTruthy();
  expect(parent.conversation_id).toBeTruthy();
  await expect(page.getByRole('heading', { name: parentQuestion })).toBeVisible();

  await page.getByRole('button', { name: 'Next step' }).click();
  await expect(page.locator('.plan-card')).toContainText('Questions to investigate');
  await expect(page.locator('.job-view')).toContainText('Discovering scholarly sources');
  await expect(page.locator('.coverage-number')).toContainText('0');

  const childQuestion = 'Synthetic follow-up lineage persistence check after refresh';
  await page.getByRole('button', { name: 'Follow up' }).click();
  const followUpComposer = page.getByRole('dialog', { name: 'Continue this research' });
  await followUpComposer.getByLabel('Research question').fill(childQuestion);
  await followUpComposer.getByLabel(/Decision context/).fill('Synthetic child context; do not infer parent claims.');
  const childCreatePromise = page.waitForResponse((response) =>
    response.request().method() === 'POST' && new URL(response.url()).pathname.match(/^\/api\/v1\/projects\/[^/]+\/research-jobs$/) !== null,
  );
  const followUpContextPromise = page.waitForResponse((response) =>
    new URL(response.url()).pathname.match(/^\/api\/v1\/research-jobs\/[^/]+\/follow-up-context$/) !== null,
  );
  await followUpComposer.getByRole('button', { name: 'Start follow-up' }).click();
  const childResponse = await childCreatePromise;
  expect(childResponse.status()).toBe(201);
  const child = await childResponse.json() as { id: string; parent_job_id: string; conversation_id: string };
  expect(child.parent_job_id).toBe(parent.id);
  expect(child.conversation_id).toBe(parent.conversation_id);
  const contextResponse = await followUpContextPromise;
  expect(contextResponse.status()).toBe(200);
  const context = await contextResponse.json() as {
    status: string;
    parent: { job_id: string; question: string };
    claims: unknown[];
    reuse_boundary: string;
  };
  expect(context.status).toBe('context_no_relevant_claims');
  expect(context.parent).toMatchObject({ job_id: parent.id, question: parentQuestion });
  expect(context.claims).toEqual([]);
  expect(context.reuse_boundary).toContain('not copied into this run\'s claims or citations');
  await expect(page.getByRole('heading', { name: childQuestion })).toBeVisible();
  await page.getByRole('tab', { name: /conversation/i }).click();
  const conversation = page.locator('.conversation-history');
  await expect(conversation).toContainText(parentQuestion);
  await expect(conversation).toContainText(childQuestion);
  const contextCard = page.locator('.follow-up-context-card');
  await expect(contextCard.getByRole('heading', { name: 'What informed this follow-up' })).toBeVisible();
  await expect(contextCard).toContainText(parentQuestion);
  await expect(contextCard).toContainText('No parent claims matched this follow-up question.');
  await expect(contextCard).toContainText('not automatically carried into this run’s citations');

  await page.reload();
  await page.locator('.project-grid').getByRole('button', { name: /Local browser integration \(synthetic data\)/ }).click();
  const savedChild = page.locator('.job-list').getByRole('button', { name: new RegExp(childQuestion) });
  await expect(savedChild).toBeVisible();
  await savedChild.click();
  await expect(page.getByRole('heading', { name: childQuestion })).toBeVisible();
  await page.getByRole('tab', { name: /conversation/i }).click();
  const restoredConversation = page.locator('.conversation-history');
  await expect(restoredConversation).toContainText(parentQuestion);
  await expect(restoredConversation).toContainText(childQuestion);
  await expect(page.locator('.follow-up-context-card')).toContainText(parentQuestion);
  await expect(page.locator('.follow-up-context-card')).toContainText('No parent claims matched this follow-up question.');

  const responses = apiResponses.map(({ url, method, status }) => ({
    path: new URL(url).pathname,
    origin: new URL(url).origin,
    method,
    status,
  }));
  expect(responses.filter((item) => item.method === 'POST' && item.path.match(/^\/api\/v1\/projects\/[^/]+\/research-jobs$/) && item.status === 201)).toHaveLength(2);
  expect(responses.some((item) => item.method === 'GET' && item.path === `/api/v1/conversations/${parent.conversation_id}/messages` && item.status === 200)).toBe(true);
  expect(responses.some((item) => item.method === 'GET' && item.path === `/api/v1/research-jobs/${child.id}/follow-up-context` && item.status === 200)).toBe(true);
  expect(responses.every((item) => item.origin === expectedApiOrigin && item.status < 400)).toBe(true);
});

test('real browser erases Veda data through the API while keeping the local sign-in usable', async ({ page }) => {
  const apiResponses: { path: string; status: number; method: string }[] = [];
  page.on('response', (response) => {
    const url = new URL(response.url());
    if (url.pathname.startsWith('/api/v1/')) {
      apiResponses.push({ path: url.pathname, status: response.status(), method: response.request().method() });
    }
  });

  // This is a disposable provider-disabled SQLite API. No route interception
  // substitutes for the real owner-scoped erasure endpoint.
  await page.goto('/');
  await page.getByRole('button', { name: 'Continue to local workspace' }).click();
  const project = page.locator('.project-grid').getByRole('button', { name: /Local browser integration \(synthetic data\)/ });
  await expect(project).toBeVisible();
  await project.click();
  await page.locator('.job-list').getByRole('button', { name: /Synthetic browser\/API citation-inspection test/ }).click();
  await expect(page.locator('.breadcrumb')).toContainText('Research run');
  await page.getByRole('button', { name: 'Preferences and data' }).click();

  const preferences = page.getByRole('dialog', { name: 'Preferences and data' });
  await expect(preferences).toContainText('The Veda-data purge does not remove your sign-in account');
  await preferences.getByRole('button', { name: 'Delete all Veda data' }).click();
  const confirmation = preferences.getByLabel('Type DELETE VEDA DATA to confirm');
  const eraseButton = preferences.getByRole('button', { name: 'Permanently delete Veda data' });
  await expect(eraseButton).toBeDisabled();
  await confirmation.fill('DELETE EVERYTHING');
  await expect(eraseButton).toBeDisabled();
  await confirmation.fill('DELETE VEDA DATA');
  const projectsBeforeDeletion = await page.evaluate(async () => {
    const { api } = await import('/src/api.ts');
    const projects = await api<{ items: unknown[] }>('/projects');
    return projects.items.length;
  });
  expect(projectsBeforeDeletion).toBeGreaterThan(0);
  await eraseButton.click();

  await expect(preferences.getByRole('status')).toContainText(
    `Deleted ${projectsBeforeDeletion} Veda project(s)`,
  );
  await expect(preferences.getByRole('status')).toContainText('your sign-in account remains active');
  await expect(page.locator('.breadcrumb')).toContainText('Overview');
  const remaining = await page.evaluate(async () => {
    const { api } = await import('/src/api.ts');
    const identity = await api<{ provider: string }>('/me');
    const projects = await api<{ items: unknown[] }>('/projects');
    const savedPreferences = await api<{ is_customized: boolean }>('/me/preferences');
    return { provider: identity.provider, projectCount: projects.items.length, customized: savedPreferences.is_customized };
  });
  expect(remaining).toEqual({ provider: 'local-development', projectCount: 0, customized: false });
  expect(apiResponses.some(({ path, method, status }) =>
    path === '/api/v1/me/data' && method === 'DELETE' && status === 200,
  )).toBe(true);
  expect(apiResponses.some(({ path, method, status }) => path === '/api/v1/me' && method === 'GET' && status === 200)).toBe(true);
  expect(apiResponses.some(({ path, method, status }) => path === '/api/v1/projects' && method === 'GET' && status === 200)).toBe(true);
  expect(apiResponses.some(({ path, method, status }) => path === '/api/v1/me/preferences' && method === 'GET' && status === 200)).toBe(true);
});

test('live scholarly/model smoke completes a bounded Veda browser run', async ({ page }) => {
  const openRouterLiveMode = process.env.VEDA_OPENROUTER_LIVE_E2E === '1';
  const govukLiveMode = process.env.VEDA_GOVUK_LIVE_E2E === '1';
  const crawl4aiLiveMode = process.env.VEDA_CRAWL4AI_LIVE_E2E === '1';
  const requireUnseededSpecialist = process.env.VEDA_REQUIRE_UNSEEDED_SPECIALIST === '1';
  const requireWebPublisherFullText = process.env.VEDA_REQUIRE_WEB_PUBLISHER_FULLTEXT === '1';
  const requireOfficialPageMetadata = process.env.VEDA_REQUIRE_OFFICIAL_PAGE_METADATA === '1';
  const liveDepth = process.env.VEDA_LIVE_SCHOLARLY_DEPTH || 'quick';
  test.skip(
    !openRouterLiveMode && process.env.VEDA_LIVE_SCHOLARLY_E2E !== '1',
    'Requires explicit opt-in for public metadata retrieval or the guarded OpenRouter free-model run.',
  );
  test.setTimeout(
    crawl4aiLiveMode
      ? 420_000
      : process.env.VEDA_OPENAIRE_FULLTEXT_TARGET_DOI
      ? 540_000
      : liveDepth === 'standard'
        ? 360_000
        : 240_000,
  );

  const expectedApiOrigin = new URL(
    process.env.VEDA_E2E_API_BASE_URL ||
      `http://127.0.0.1:${process.env.VEDA_REAL_E2E_API_PORT || '8001'}/api/v1`,
  ).origin;
  const liveQuestion = process.env.VEDA_LIVE_SCHOLARLY_QUESTION ||
    'How does workplace AI adoption affect worker productivity outcomes?';
  const fullTextTargetDoi = process.env.VEDA_EUROPEPMC_FULLTEXT_TARGET_DOI || null;
  const repositoryFullTextTargetDoi = process.env.VEDA_OPENAIRE_FULLTEXT_TARGET_DOI || null;
  const inspectedFullTextTargetDoi = repositoryFullTextTargetDoi || fullTextTargetDoi;
  const worldBankTermsConfirmed =
    process.env.VEDA_WORLD_BANK_DOCUMENTS_NONCOMMERCIAL_USE_CONFIRMED === '1';
  const apiResponses: { url: string; status: number; method: string }[] = [];
  page.on('response', (response) => {
    const url = new URL(response.url());
    if (url.pathname.startsWith('/api/v1/')) {
      apiResponses.push({ url: response.url(), status: response.status(), method: response.request().method() });
    }
  });

  // Both modes use a non-sensitive synthetic question and actual public
  // scholarly providers. The OpenRouter mode is separately gated, free-only,
  // and uses the isolated server's temporary database and bounded call quota.
  await page.goto('/');
  await page.getByRole('button', { name: 'Continue to local workspace' }).click();
  await page.locator('.project-grid').getByRole('button', { name: /Local browser integration \(synthetic data\)/ }).click();
  const providerSettingsPromise = page.waitForResponse((response) =>
    new URL(response.url()).pathname === '/api/v1/settings/providers',
  );
  await page.getByRole('button', { name: 'Start research' }).click();

  const composer = page.locator('.modal-card');
  await expect(composer.locator('.budget-note')).toContainText('Crossref and OpenAlex');
  await expect(composer.locator('.budget-note')).toContainText('World Bank Data360');
  await expect(composer.locator('.budget-note')).toContainText('World Bank Documents & Reports API');
  await expect(composer.locator('.budget-note')).toContainText('when you supply a supported geography');
  await expect(composer.locator('.budget-note')).toContainText('ILOSTAT');
  await expect(composer.locator('.budget-note')).toContainText(
    'Employment questions with an explicitly supplied World geography',
  );
  if (openRouterLiveMode) {
    await expect(composer.locator('.budget-note')).toContainText('Only free model routes are accepted');
  } else {
    await expect(composer.locator('.budget-note')).toContainText('Model processing. No model provider is enabled.');
  }
  await composer.getByLabel('Research question').fill(
    liveQuestion,
  );
  if (govukLiveMode) {
    await composer.getByLabel('Geography').fill('United Kingdom');
    await expect(composer.locator('.budget-note')).toContainText('unsupported best-effort GOV.UK Search API');
  }
  // The seeded project description is test-only context. Clear it so it is not
  // appended to actual scholarly searches and does not contaminate relevance.
  await composer.getByLabel(/Decision context/).fill('');
  await composer.getByLabel('Research depth').selectOption(liveDepth);
  await composer.getByLabel(/Maximum model spend/).fill(openRouterLiveMode ? '0.25' : '0');
  const providerSettingsResponse = await providerSettingsPromise;
  expect(providerSettingsResponse.status()).toBe(200);
  await expect(providerSettingsResponse.json()).resolves.toMatchObject({
    active_provider: openRouterLiveMode ? 'openrouter' : 'disabled',
    provider_ready: true,
    paid_calls_allowed: false,
    ...(openRouterLiveMode ? {} : { model: null }),
  });

  const createPromise = page.waitForResponse((response) =>
    response.request().method() === 'POST' && new URL(response.url()).pathname.match(/^\/api\/v1\/projects\/[^/]+\/research-jobs$/) !== null,
  );
  await composer.getByRole('button', { name: 'Start research' }).click();
  const createResponse = await createPromise;
  expect(createResponse.status()).toBe(201);
  let savedJob = await createResponse.json() as {
    id: string;
    project_id: string;
    status: string;
    current_stage: string;
    model_calls_reserved: number;
    cost_spent_estimate_usd: number;
  };
  expect(savedJob.model_calls_reserved).toBe(0);
  const reportResponsePromise = page.waitForResponse((response) =>
    response.request().method() === 'GET' && new URL(response.url()).pathname === `/api/v1/research-jobs/${savedJob.id}/report`,
    { timeout: crawl4aiLiveMode ? 360_000 : repositoryFullTextTargetDoi ? 480_000 : 180_000 },
  );

  for (let step = 0; step < 8 && !['completed', 'completed_with_limitations'].includes(savedJob.status); step += 1) {
    const advancePromise = page.waitForResponse((response) =>
      response.request().method() === 'POST' && new URL(response.url()).pathname === `/api/v1/research-jobs/${savedJob.id}/advance`,
      { timeout: crawl4aiLiveMode || repositoryFullTextTargetDoi ? 150_000 : 30_000 },
    );
    await page.getByRole('button', { name: 'Next step' }).click();
    const advanceResponse = await advancePromise;
    expect(advanceResponse.status()).toBe(200);
    savedJob = await advanceResponse.json() as typeof savedJob;
    if (openRouterLiveMode) {
      expect(savedJob.model_calls_reserved).toBeLessThanOrEqual(4);
      expect(savedJob.cost_spent_estimate_usd).toBe(0);
    } else {
      expect(savedJob.model_calls_reserved).toBe(0);
    }
    // Stop at a failed checkpoint. Immediate replay can consume provider quota
    // and hide the original failure behind a later origin cooldown/defer result.
    if (['retryable_failure', 'terminal_failure'].includes(savedJob.status)) break;
  }

  expect(['completed', 'completed_with_limitations']).toContain(savedJob.status);
  expect(savedJob.current_stage).toBe('complete');
  if (openRouterLiveMode) {
    expect(savedJob.model_calls_reserved).toBeGreaterThan(0);
    expect(savedJob.cost_spent_estimate_usd).toBe(0);
    const usage = await page.evaluate(async ({ apiOrigin, projectId }) => {
      const session = JSON.parse(sessionStorage.getItem('veda_local_session') || '{}') as { token?: string };
      const response = await fetch(`${apiOrigin}/api/v1/projects/${projectId}/usage`, {
        headers: session.token ? { Authorization: `Bearer ${session.token}` } : {},
      });
      return { status: response.status, body: await response.json() };
    }, { apiOrigin: expectedApiOrigin, projectId: savedJob.project_id }) as {
      status: number;
      body: { model_calls: number; estimated_cost_usd: number };
    };
    expect(usage.status).toBe(200);
    expect(usage.body.model_calls).toBeGreaterThan(0);
    expect(usage.body.estimated_cost_usd).toBe(0);
  }
  const reportResponse = await reportResponsePromise;
  expect(reportResponse.status()).toBe(200);
  const report = await reportResponse.json() as {
    id: string;
    status: string;
    citation_map: Record<string, { source_id?: string; doi?: string | null }>;
    verification: {
      semantic_support_check: string;
      citation_link_integrity: { status: string };
      search_coverage: {
        selected_sources: number;
        candidate_ledger_records: number;
        provider_query_counts: Record<string, number>;
        provider_result_counts: Record<string, number>;
        provider_failures: Record<string, number>;
        general_web_discovery?: {
          status: string;
          preflight_status: string;
          request_count: number;
          reserved_credits: number;
          reported_cost_credits: number;
          unresolved_reserved_credits: number;
          allowance_left_credits: number | null;
          searches: Array<{ purpose?: string; status: string; result_count: number }>;
          hits: Array<{
            title: string;
            url: string;
            domain: string;
            snippet_role: string;
            organization_id?: string;
          }>;
          newly_discovered_organizations: Array<{
            organization_id: string;
            canonical_name: string;
            official_domain: string;
            identity_status: string;
            registry_match: boolean;
            verification_source: string;
          }>;
          verified_official_publications: Array<{
            organization_id: string;
            title: string;
            doi: string | null;
            official_url: string;
            publisher_verification: string;
            content_fetched: boolean;
            rights_status: string;
            source_id?: string | null;
            selected?: boolean;
            retrieval_status?: string;
            passage_count?: number;
            page_body_retained?: boolean;
          }>;
          official_publication_search: {
            status: string;
            returned_count: number;
            content_fetched: boolean;
            rights_status: string;
            publications?: Array<{ title: string; url: string }>;
          };
        };
        institutional_publication_search: {
          status: string;
          query: string | null;
          returned_count: number;
          publication_ids: string[];
          request_dispatched: boolean;
          content_fetched: boolean;
          rights_status: string;
        };
        government_publication_search: {
          provider: string;
          status: string;
          geography: string | null;
          query: string | null;
          returned_count: number;
          publication_ids: string[];
          request_dispatched: boolean;
          linked_content_fetched: boolean;
          metadata_only: boolean;
          api_support_status: string;
          organization_discovery: {
            status: string;
            verification_provider: string;
            maximum_unique_organizations: number;
            requests_attempted: number;
            organizations: Array<{
              organization_id: string;
              canonical_name: string;
              identity_status: string;
              verification_source: string;
              quality_assessment: string;
              publication_ids: string[];
            }>;
            errors: Array<{ slug: string; error_code: string; request_dispatched?: boolean }>;
          };
        };
        organization_discovery: {
          schema_version: number;
          status: string;
          seed_work_count: number;
          openaire_search: {
            status: string;
            mode: string;
            query: string;
            returned_count: number;
            error_code: string | null;
            request_dispatched: boolean;
          };
          identity_requests_attempted: number;
          organizations: Array<{
            organization_id: string;
            canonical_name: string;
            identity_status: string;
            registry_match: boolean;
            official_domains: string[];
            organization_types: string[];
            quality_assessment: string;
          }>;
          publication_searches: Array<{
            organization_id: string;
            organization_name?: string;
            provider?: string;
            status: string;
            query?: string;
            returned_count: number;
            publications: Array<{
              title: string;
              doi: string | null;
              provider?: string;
              official_url?: string;
              content_fetched?: boolean;
              retrieval_status?: string;
              passage_count?: number;
            }>;
            homepage_url?: string | null;
            api_url?: string | null;
            request_count?: number;
            request_dispatched?: boolean;
            content_fetched?: boolean;
            rights_status?: string;
          }>;
          selected_publications: Array<{
            source_id: string;
            title: string;
            doi: string | null;
            organization_id?: string;
            organization_id?: string;
            organization_name: string;
            identity_status: string;
            verification_source: string | null;
            retrieval_status?: string;
            passage_count?: number;
          }>;
          publication_verification_attempts?: Array<{
            official_url: string;
            search_title: string;
            status: string;
            verification_method?: string;
            error_code?: string;
            request_count?: number;
            body_retained?: boolean;
          }>;
        };
        conditional_statistics_routing: {
          status: string;
          world_bank_data360: { status: string; reason_code: string | null; requests: number };
          ilostat: { status: string; reason_code: string | null; requests: number };
        };
      };
    };
  };
  expect(['completed', 'completed_with_limitations']).toContain(report.status);
  if (!openRouterLiveMode) expect(report.verification.semantic_support_check).toBe('not_performed');
  expect(report.verification.citation_link_integrity.status).toBe('passed');
  expect(report.verification.search_coverage.provider_query_counts.Crossref).toBeGreaterThan(0);
  expect(report.verification.search_coverage.provider_query_counts.OpenAlex).toBeGreaterThan(0);
  const openAireCoverage = report.verification.search_coverage.organization_discovery.openaire_search;
  if (openAireCoverage.mode === 'topic_organization_discovery') {
    expect(report.verification.search_coverage.provider_query_counts['OpenAIRE organization discovery'])
      .toBe(1);
  } else {
    expect(report.verification.search_coverage.provider_query_counts.OpenAIRE).toBe(1);
  }
  expect(report.verification.search_coverage.provider_query_counts['World Bank Documents & Reports'] || 0)
    .toBe(worldBankTermsConfirmed ? 1 : 0);
  expect(report.verification.search_coverage.provider_result_counts.Crossref).toBeGreaterThan(0);
  const generalWebDiscovery = report.verification.search_coverage.general_web_discovery;
  const officialPageMetadataPublication = generalWebDiscovery?.verified_official_publications.find(
    (publication) => publication.publisher_verification === 'official_page_metadata_verified',
  );
  const blockedOfficialPageMetadataAttempt = generalWebDiscovery?.publication_verification_attempts?.find(
    (attempt) => attempt.status === 'not_verified' && attempt.error_code === 'access_denied',
  );
  const blockedOfficialPageDomain = blockedOfficialPageMetadataAttempt
    ? new URL(blockedOfficialPageMetadataAttempt.official_url).hostname
    : null;
  const blockedOfficialPageOrganization = blockedOfficialPageDomain
    ? generalWebDiscovery?.newly_discovered_organizations.find((organization) =>
      blockedOfficialPageDomain === organization.official_domain
      || blockedOfficialPageDomain.endsWith(`.${organization.official_domain}`),
    )
    : undefined;
  if (crawl4aiLiveMode) {
    expect(generalWebDiscovery).toBeTruthy();
    expect(generalWebDiscovery?.preflight_status).toBe('reported');
    expect(generalWebDiscovery?.request_count).toBeLessThanOrEqual(2);
    expect(generalWebDiscovery?.reserved_credits).toBeLessThanOrEqual(2);
    expect(generalWebDiscovery?.reported_cost_credits).toBeLessThanOrEqual(
      generalWebDiscovery?.reserved_credits || 0,
    );
    expect(generalWebDiscovery?.unresolved_reserved_credits).toBe(0);
    expect(generalWebDiscovery?.hits.every((hit) =>
      hit.snippet_role === 'unverified_discovery_lead_not_evidence',
    )).toBe(true);
    expect(generalWebDiscovery?.searches.some((search) =>
      search.purpose === 'verified_official_domain_publication_discovery',
    )).toBe(generalWebDiscovery?.newly_discovered_organizations.length > 0);
  }
  if (requireOfficialPageMetadata) {
    if (officialPageMetadataPublication) {
      expect(officialPageMetadataPublication.selected).toBe(true);
      expect(officialPageMetadataPublication.source_id).toBeTruthy();
      expect(officialPageMetadataPublication.doi).toBeNull();
      expect(officialPageMetadataPublication.content_fetched).toBe(false);
      expect(officialPageMetadataPublication.page_body_retained).toBe(false);
      expect(officialPageMetadataPublication.rights_status).toBe('not_assessed_metadata_only');
      expect(officialPageMetadataPublication.retrieval_status).toBe('metadata_only');
      expect(officialPageMetadataPublication.passage_count).toBe(0);
      expect(Object.values(report.citation_map).some((citation) =>
        citation.source_id === officialPageMetadataPublication.source_id,
      )).toBe(true);
    } else {
      expect(
        blockedOfficialPageMetadataAttempt,
        'a denied page must be recorded as a terminal access restriction, not as a missing success',
      ).toBeTruthy();
      expect(blockedOfficialPageMetadataAttempt?.request_count).toBeGreaterThan(0);
      expect(blockedOfficialPageMetadataAttempt?.body_retained).toBe(false);
      expect(blockedOfficialPageMetadataAttempt?.search_title.toLowerCase()).toContain('food price');
      expect(new URL(blockedOfficialPageMetadataAttempt!.official_url).pathname).toContain('/publication/');
      expect(blockedOfficialPageOrganization).toBeTruthy();
      const metadataOnlyFallback = generalWebDiscovery?.verified_official_publications.find(
        (publication) => publication.selected
          && publication.organization_id === blockedOfficialPageOrganization?.organization_id
          && publication.source_id
          && publication.publisher_verification === 'verified'
          && publication.rights_status === 'metadata_only_not_assessed',
      );
      expect(metadataOnlyFallback, 'a separately verified publication should remain reportable').toBeTruthy();
      expect(Object.values(report.citation_map).some((citation) =>
        citation.source_id === metadataOnlyFallback?.source_id,
      )).toBe(true);
    }
  }
  const institutionalPublicationSearch =
    report.verification.search_coverage.institutional_publication_search;
  if (worldBankTermsConfirmed) {
    expect(institutionalPublicationSearch).toMatchObject({
      status: 'completed',
      request_dispatched: true,
      content_fetched: false,
      rights_status: 'not_assessed',
    });
  } else {
    // The source planner may correctly omit this connector for a question that
    // does not warrant it, or record the explicit terms gate when it does.
    expect([
      'not_planned',
      'not_attempted_terms_confirmation_required',
    ]).toContain(institutionalPublicationSearch.status);
    expect(institutionalPublicationSearch).toMatchObject({
      request_dispatched: false,
      content_fetched: false,
      rights_status: 'not_assessed',
    });
  }
  expect(report.verification.search_coverage.government_publication_search).toMatchObject({
    status: govukLiveMode ? 'completed' : 'not_applicable_explicit_uk_geography_required',
    provider: 'GOV.UK Search API',
    geography: govukLiveMode ? 'United Kingdom' : null,
    request_dispatched: govukLiveMode,
    linked_content_fetched: false,
    metadata_only: true,
    api_support_status: 'unsupported_best_effort',
  });
  expect(report.verification.search_coverage.provider_query_counts['GOV.UK Search API'] || 0)
    .toBe(govukLiveMode ? 1 : 0);
  expect(report.verification.search_coverage.provider_query_counts['GOV.UK Organizations API'] || 0)
    .toBeLessThanOrEqual(govukLiveMode ? 2 : 0);
  if (govukLiveMode) {
    expect(report.verification.search_coverage.government_publication_search.returned_count)
      .toBeGreaterThan(0);
    expect(report.verification.search_coverage.government_publication_search.organization_discovery
      .requests_attempted).toBeGreaterThan(0);
    expect(report.verification.search_coverage.government_publication_search.organization_discovery
      .organizations.every((item) => item.quality_assessment === 'not_assessed')).toBe(true);
    if (liveQuestion.toLowerCase().includes('battery storage')) {
      expect(report.verification.search_coverage.government_publication_search.query)
        .toBe('renewable energy deployment battery storage investment');
    }
    const govukCandidate = await page.evaluate(async ({ apiOrigin, jobId }) => {
      const session = JSON.parse(sessionStorage.getItem('veda_local_session') || '{}') as { token?: string };
      const response = await fetch(`${apiOrigin}/api/v1/research-jobs/${jobId}/candidates`, {
        headers: session.token ? { Authorization: `Bearer ${session.token}` } : {},
      });
      if (!response.ok) return null;
      const body = await response.json() as { items: Array<{
        provider: string;
        provider_record_id: string;
        title: string;
        publisher: string | null;
        publisher_organizations: Array<{
          organization_id: string;
          canonical_name: string;
          content_id: string;
          directory_status: string;
          identity_status: string;
          verification_method: string;
          verification_source: string;
          official_url: string;
          quality_assessment: string;
        }>;
        disposition: string;
        reason_code: string;
        source_governance?: { source_classes: string[]; identity_status: string } | null;
      }> };
      return body.items.find((item) => item.provider === 'GOV.UK Search API'
        && item.publisher_organizations.length > 0) || null;
    }, { apiOrigin: expectedApiOrigin, jobId: savedJob.id });
    expect(govukCandidate).toBeTruthy();
    expect(report.verification.search_coverage.government_publication_search.publication_ids)
      .toContain(govukCandidate?.provider_record_id);
    expect(govukCandidate?.source_governance?.source_classes).toContain('government');
    expect(govukCandidate?.source_governance?.identity_status).toBe('verified');
    const verifiedPublisher = govukCandidate?.publisher_organizations.find(
      (item) => item.identity_status === 'VERIFIED_ESTABLISHED',
    );
    expect(verifiedPublisher).toBeTruthy();
    expect(verifiedPublisher?.organization_id).toMatch(/^govuk:[a-z0-9-]+$/);
    expect(verifiedPublisher?.content_id).toMatch(/^[0-9a-f-]{36}$/i);
    expect(verifiedPublisher?.directory_status).toBe('live');
    expect(verifiedPublisher?.verification_method).toBe('govuk_organizations_api_exact_slug');
    expect(verifiedPublisher?.verification_source).toMatch(
      /^https:\/\/www\.gov\.uk\/api\/organisations\/[a-z0-9-]+$/,
    );
    expect(verifiedPublisher?.official_url).toMatch(
      /^https:\/\/www\.gov\.uk\/government\/organisations\/[a-z0-9-]+$/,
    );
    expect(verifiedPublisher?.quality_assessment).toBe('not_assessed');
    expect(['selected', 'excluded']).toContain(govukCandidate?.disposition);
    if (govukCandidate?.disposition === 'selected') {
      await page.getByRole('tab', { name: /sources/i }).click();
      const selectedSource = page.locator('.source-row').filter({ hasText: govukCandidate.title });
      await expect(selectedSource).toBeVisible();
      await selectedSource.click();
      const govukInspector = page.getByRole('dialog', { name: govukCandidate.title });
      await expect(govukInspector).toContainText('Official publication metadata');
      await expect(govukInspector).toContainText('linked report attachment was not fetched');
      const pageBodyPassage = govukInspector.getByText(/GOV\.UK page body paragraph/).first();
      if (await pageBodyPassage.count()) {
        await expect(govukInspector).toContainText('GOV.UK publication page');
        await expect(govukInspector).toContainText('official publication page body');
        await expect(pageBodyPassage).toBeVisible();
      } else {
        // A selected government record may remain metadata-only when its page
        // body is unavailable or not retrieved; publisher identity alone does
        // not imply content access.
        await expect(govukInspector).toContainText(/publication metadata only/i);
        await expect(govukInspector).not.toContainText('GOV.UK page body paragraph');
      }
      await govukInspector.getByRole('button', { name: 'Close source inspector' }).click();
      await page.getByRole('tab', { name: /report/i }).click();
    } else if (govukCandidate) {
      await page.getByRole('tab', { name: /sources/i }).click();
      await page.getByRole('tab', { name: /all candidates/i }).click();
      const candidateRow = page.locator('.candidate-row').filter({ hasText: govukCandidate.title });
      await expect(candidateRow).toContainText('GOV.UK Search API');
      expect(govukCandidate.publisher).toContain('Department for');
      await expect(candidateRow).toContainText(`Publisher: ${govukCandidate.publisher}`);
      await expect(candidateRow).toContainText('government · identity verified');
      await expect(candidateRow).toContainText(govukCandidate.reason_code.replace(/_/g, ' '));
      expect(govukCandidate.publisher_organizations.length).toBeGreaterThan(0);
      expect(govukCandidate.publisher_organizations[0].quality_assessment).toBe('not_assessed');
      await expect(candidateRow).toContainText('Publisher identity:');
      await expect(candidateRow.getByRole('link', { name: 'Official directory record' }).first())
        .toHaveAttribute('href', govukCandidate.publisher_organizations[0].official_url);
    }
  }
  if (worldBankTermsConfirmed) {
    expect(report.verification.search_coverage.institutional_publication_search.returned_count)
      .toBeGreaterThan(0);
  } else {
    expect(report.verification.search_coverage.institutional_publication_search.returned_count)
      .toBe(0);
  }
  expect(report.verification.search_coverage.organization_discovery.schema_version).toBe(1);
  expect(report.verification.search_coverage.organization_discovery.status).toBeTruthy();
  expect(report.verification.search_coverage.organization_discovery.openaire_search).toMatchObject({
    status: 'completed',
    request_dispatched: true,
  });
  if (openAireCoverage.mode === 'topic_organization_discovery') {
    expect(openAireCoverage.returned_count).toBeGreaterThan(0);
    expect(report.verification.search_coverage.provider_query_counts['Crossref organization-affiliation publications'] || 0)
      .toBeLessThanOrEqual(1);
  } else {
    // A completed topic publication search may legitimately return zero. The
    // stronger unseeded-organization smoke asserts discovery and a selected
    // publication explicitly below, instead of treating any HTTP 200 as proof.
    expect(openAireCoverage.mode).toBe('publication_search');
  }
  const openAlexResults = report.verification.search_coverage.provider_result_counts.OpenAlex || 0;
  expect(report.verification.search_coverage.provider_query_counts.OpenAlex || 0).toBeGreaterThan(0);
  if (openAlexResults === 0) {
    // Public indexes can rate-limit a bounded live run. A zero-result route is
    // acceptable only when Veda records the provider failure rather than
    // presenting it as a successful empty search.
    expect(report.verification.search_coverage.provider_failures.OpenAlex || 0).toBeGreaterThan(0);
  }
  const statisticsRouting = report.verification.search_coverage.conditional_statistics_routing;
  expect(statisticsRouting.status).toBe('recorded');
  const reportTab = page.getByRole('tab', { name: 'report', exact: true });
  await reportTab.click();
  await expect(reportTab).toHaveAttribute('aria-selected', 'true');
  for (const [provider, label, outcome] of [
    ['World Bank Data360', 'World Bank Data360', statisticsRouting.world_bank_data360],
    ['ILOSTAT', 'ILOSTAT', statisticsRouting.ilostat],
  ] as const) {
    const requests = report.verification.search_coverage.provider_query_counts[provider] || 0;
    const results = report.verification.search_coverage.provider_result_counts[provider] || 0;
    expect(requests).toBe(outcome.status === 'searched' ? outcome.requests : 0);
    expect(results).toBe(outcome.status === 'searched' ? outcome.results : 0);
    if (govukLiveMode && provider === 'World Bank Data360') {
      expect(outcome.status).toBe('searched');
    }
    const statusText = outcome.status.replace(/_/g, ' ');
    await expect(page.locator('.report-content')).toContainText(`${label} route: ${statusText}`);
    await expect(page.locator('.audit-card')).toContainText(`${label} · ${statusText}`);
  }
  expect(report.verification.search_coverage.selected_sources).toBeGreaterThan(0);
  expect(report.verification.search_coverage.candidate_ledger_records).toBeGreaterThan(0);
  const citationKeys = Object.keys(report.citation_map);
  expect(citationKeys.length).toBeGreaterThan(0);

  await expect(page.getByRole('heading', { name: liveQuestion })).toBeVisible();
  await page.getByRole('tab', { name: /report/i }).click();
  await expect(page.locator('.report-content')).toContainText('Search coverage');
  await expect(page.locator('.report-content')).toContainText(
    govukLiveMode
      ? 'GOV.UK policy-paper metadata: completed'
      : 'GOV.UK policy-paper metadata: not_applicable_explicit_uk_geography_required',
  );
  await expect(page.locator('.report-content')).toContainText('Dynamic organization discovery');
  await expect(page.locator('.report-content')).toContainText(
    worldBankTermsConfirmed
      ? 'World Bank Documents & Reports publication metadata'
      : 'World Bank Documents & Reports publication metadata: not_attempted_terms_confirmation_required',
  );
  const worldBankCandidate = await page.evaluate(async ({ apiOrigin, jobId }) => {
    const session = JSON.parse(sessionStorage.getItem('veda_local_session') || '{}') as { token?: string };
    const response = await fetch(`${apiOrigin}/api/v1/research-jobs/${jobId}/candidates`, {
      headers: session.token ? { Authorization: `Bearer ${session.token}` } : {},
    });
    if (!response.ok) return null;
    const body = await response.json() as {
      items: Array<{
        id: string;
        title: string;
        provider: string;
        query: string;
        disposition: string;
        reason_code: string;
        source_governance?: { source_classes: string[]; identity_status: string } | null;
      }>;
    };
    return body.items.find((source) => source.provider === 'World Bank Documents & Reports') || null;
  }, { apiOrigin: expectedApiOrigin, jobId: savedJob.id });
  if (process.env.VEDA_EXPECT_WORLD_BANK_DOCUMENT === '1') {
    expect(worldBankCandidate).toBeTruthy();
    expect(worldBankCandidate?.source_governance?.source_classes).toContain('multilateral');
    expect(worldBankCandidate?.source_governance?.identity_status).toBe('verified');
    expect(worldBankCandidate?.query).toBe(
      report.verification.search_coverage.institutional_publication_search.query,
    );
    expect(['selected', 'excluded']).toContain(worldBankCandidate?.disposition);
    if (worldBankCandidate?.disposition === 'excluded') {
      expect(['source_limit', 'insufficient_topic_overlap']).toContain(worldBankCandidate.reason_code);
    }
    await page.getByRole('tab', { name: /^sources/i }).click();
    await page.getByRole('tab', { name: /All candidates/ }).click();
    const worldBankCandidateRow = page
      .locator('.candidate-row')
      .filter({ hasText: worldBankCandidate!.title })
      .filter({ hasText: 'World Bank Documents & Reports' })
      .filter({ hasText: `Repository record ${worldBankCandidate!.provider_record_id.replace(/^worldbank:/, '')}` });
    await expect(worldBankCandidateRow).toContainText('World Bank Documents & Reports');
    await expect(worldBankCandidateRow).toContainText(
      `Repository record ${worldBankCandidate!.provider_record_id.replace(/^worldbank:/, '')}`,
    );
    await expect(worldBankCandidateRow).toContainText(
      worldBankCandidate?.disposition === 'selected' ? 'SELECTED' : 'EXCLUDED',
    );
    await expect(worldBankCandidateRow).toContainText('multilateral');
    if (worldBankCandidate?.disposition === 'excluded') {
      await expect(worldBankCandidateRow).toContainText(worldBankCandidate.reason_code.replace(/_/g, ' '));
    }
  } else if (!worldBankTermsConfirmed) {
    expect(worldBankCandidate).toBeNull();
  }
  await page.getByRole('tab', { name: /report/i }).click();
  if (requireOfficialPageMetadata && officialPageMetadataPublication) {
    await page.getByRole('button', {
      name: `Inspect organization-discovered publication ${officialPageMetadataPublication.title}`,
    }).click();
    const pageMetadataInspector = page.locator('.evidence-drawer');
    await expect(pageMetadataInspector).toContainText('Organization discovery provenance');
    await expect(pageMetadataInspector).toContainText('official page metadata verified');
    await expect(pageMetadataInspector).toContainText('Publication rights');
    await expect(pageMetadataInspector).toContainText('not assessed metadata only');
    await expect(pageMetadataInspector).toContainText('not retrieved');
    await expect(pageMetadataInspector).not.toContainText('Passages in evidence ledger');
    await pageMetadataInspector.getByRole('button', { name: 'Close source inspector' }).click();
  } else if (requireOfficialPageMetadata && blockedOfficialPageMetadataAttempt) {
    const metadataOnlyFallback = generalWebDiscovery?.verified_official_publications.find(
      (publication) => publication.selected
        && publication.organization_id === blockedOfficialPageOrganization?.organization_id
        && publication.source_id
        && publication.publisher_verification === 'verified'
        && publication.rights_status === 'metadata_only_not_assessed',
    );
    expect(metadataOnlyFallback).toBeTruthy();
    await page.getByRole('button', {
      name: `Inspect organization-discovered publication ${metadataOnlyFallback!.title}`,
    }).click();
    const metadataOnlyInspector = page.locator('.evidence-drawer');
    await expect(metadataOnlyInspector).toContainText('Organization discovery provenance');
    await expect(metadataOnlyInspector).toContainText('Publication publisher check');
    await expect(metadataOnlyInspector).toContainText('verified organization domain');
    await expect(metadataOnlyInspector).toContainText('Publication rights');
    await expect(metadataOnlyInspector).toContainText('metadata only not assessed');
    await expect(metadataOnlyInspector).toContainText('not retrieved');
    await expect(metadataOnlyInspector).not.toContainText('Passages in evidence ledger');
    await metadataOnlyInspector.getByRole('button', { name: 'Close source inspector' }).click();
  }
  const organizationPublication = report.verification.search_coverage.organization_discovery.selected_publications[0];
  if (requireUnseededSpecialist) {
    const searchCoverage = report.verification.search_coverage;
    const generalWeb = searchCoverage.general_web_discovery;
    const selectedOfficialOrganizationId = generalWeb?.official_site_target_selection?.organization_id;
    const newlyDiscoveredOrganization = generalWeb?.newly_discovered_organizations.find((item) =>
      item.identity_status === 'VERIFIED_ESTABLISHED'
      && item.registry_match === false
      && item.organization_id === selectedOfficialOrganizationId,
    );
    expect(newlyDiscoveredOrganization, 'the live web search must find an unseeded organization').toBeTruthy();
    expect(newlyDiscoveredOrganization?.verification_source).toContain('api.ror.org');
    expect(newlyDiscoveredOrganization?.official_domain).toMatch(/^[a-z0-9.-]+\.[a-z]{2,}$/i);
    const discoveredOrganization = searchCoverage.organization_discovery.organizations.find(
      (organization) => organization.organization_id === newlyDiscoveredOrganization?.organization_id,
    );
    expect(discoveredOrganization?.identity_status).toBe('VERIFIED_ESTABLISHED');
    expect(discoveredOrganization?.registry_match).toBe(false);
    const officialSiteSearch = searchCoverage.organization_discovery.publication_searches.find((search) =>
      search.organization_id === newlyDiscoveredOrganization?.organization_id
      && search.provider?.startsWith('Official website search plus Crossref') === true
      && search.status === 'completed'
      && search.returned_count > 0,
    );
    expect(officialSiteSearch, 'a verified organization must yield a Crossref-verified official-site publication').toBeTruthy();
    expect(officialSiteSearch?.query).toContain(`site:${newlyDiscoveredOrganization?.official_domain}`);
    expect(officialSiteSearch?.request_count).toBeGreaterThan(0);
    const verifiedPublication = generalWeb?.verified_official_publications.find((publication) =>
      publication.organization_id === newlyDiscoveredOrganization?.organization_id
      && publication.publisher_verification === 'verified'
      && (requireWebPublisherFullText
        ? publication.content_fetched && (publication.passage_count || 0) > 0
        : !publication.content_fetched
          && publication.rights_status === 'metadata_only_not_assessed'),
    );
    expect(verifiedPublication, 'the official publication must pass publisher identity and acquisition checks').toBeTruthy();
    const verifiedPublicationHost = new URL(verifiedPublication!.official_url).hostname.toLowerCase();
    const verifiedOrganizationDomain = newlyDiscoveredOrganization!.official_domain.toLowerCase();
    expect(
      verifiedPublicationHost === verifiedOrganizationDomain
      || verifiedPublicationHost.endsWith(`.${verifiedOrganizationDomain}`),
    ).toBe(true);
    const verifiedSelectedPublication = searchCoverage.organization_discovery.selected_publications.find(
      (publication) => publication.source_id && publication.doi === verifiedPublication?.doi
        && publication.organization_id === newlyDiscoveredOrganization?.organization_id,
    );
    expect(verifiedSelectedPublication, 'the verified publication must enter the persisted selected sources').toBeTruthy();
    if (requireWebPublisherFullText) {
      expect(verifiedPublication?.selected).toBe(true);
      expect(verifiedPublication?.retrieval_status).toBe('full_text_html');
      expect(verifiedPublication?.rights_status).toBe('permitted');
      expect(verifiedPublication?.passage_count).toBeGreaterThan(0);
      expect(verifiedSelectedPublication?.retrieval_status).toBe('full_text_html');
      expect(verifiedSelectedPublication?.passage_count).toBeGreaterThan(0);
    }
    expect(Object.values(report.citation_map).some((citation) =>
      citation.source_id === verifiedSelectedPublication?.source_id,
    )).toBe(true);
    const selectedCandidate = await page.evaluate(async ({ apiOrigin, jobId, sourceId }) => {
      const session = JSON.parse(sessionStorage.getItem('veda_local_session') || '{}') as { token?: string };
      const response = await fetch(`${apiOrigin}/api/v1/research-jobs/${jobId}/candidates`, {
        headers: session.token ? { Authorization: `Bearer ${session.token}` } : {},
      });
      if (!response.ok) return null;
      const body = await response.json() as { items: Array<{
        title: string;
        provider: string;
        disposition: string;
        reason_code: string;
        canonical_source_id: string | null;
      }> };
      return body.items.find((item) => item.canonical_source_id === sourceId) || null;
    }, { apiOrigin: expectedApiOrigin, jobId: savedJob.id, sourceId: verifiedSelectedPublication!.source_id });
    expect(selectedCandidate).toBeTruthy();
    expect(selectedCandidate?.provider).toBe('Crossref');
    expect(selectedCandidate?.disposition).toBe('selected');
    expect(selectedCandidate?.reason_code).toBe('selected_by_relevance');
    expect(selectedCandidate?.canonical_source_id).toBe(verifiedSelectedPublication?.source_id);
    await page.getByRole('button', { name: `Inspect organization-discovered publication ${verifiedSelectedPublication!.title}` }).click();
    const siteInspector = page.locator('.evidence-drawer');
    await expect(siteInspector).toContainText('Organization discovery provenance');
    await expect(siteInspector).toContainText(newlyDiscoveredOrganization!.canonical_name);
    await expect(siteInspector).toContainText('verified organization domain and crossref publisher identity');
    await expect(siteInspector).toContainText('Publication content');
    if (requireWebPublisherFullText) {
      await expect(siteInspector).toContainText('full text html');
      await expect(siteInspector).toContainText('permitted');
      const inspectedPassages = siteInspector.locator('.passage-stack');
      await expect(inspectedPassages.locator('.passage-chip')).not.toHaveCount(0);
      await expect(inspectedPassages).toContainText(/Crawl4AI Cloud Markdown section (abstract|methods|results)/i);
      const passageText = (await inspectedPassages.innerText()).toLowerCase();
      const genericQuestionTerms = new Set([
        'about', 'after', 'also', 'among', 'because', 'between', 'could', 'does', 'effect',
        'effects', 'evidence', 'from', 'have', 'having', 'into', 'more', 'most', 'outcome',
        'outcomes', 'result', 'results', 'show', 'shows', 'study', 'studies', 'that', 'their',
        'then', 'them', 'there', 'these', 'this', 'those', 'through', 'using', 'were', 'what',
        'when', 'where', 'which', 'while', 'with', 'work', 'would', 'why',
      ]);
      const topicTerms = [...new Set(liveQuestion.toLowerCase().match(/\b[a-z]{4,}\b/g) || [])]
        .filter((term) => !genericQuestionTerms.has(term));
      const matchedTopicTerms = topicTerms.filter((term) => passageText.includes(term));
      expect(matchedTopicTerms.length, 'the inspected source passage should overlap the live question').toBeGreaterThanOrEqual(2);
    } else {
      await expect(siteInspector).toContainText('not retrieved');
      await expect(siteInspector).toContainText('metadata only not assessed');
    }
    await expect(siteInspector.getByRole('link', { name: 'Open verified-domain page' }))
      .toHaveAttribute('href', verifiedPublication!.official_url);
    await siteInspector.getByRole('button', { name: 'Close source inspector' }).click();
  }
  if (organizationPublication) {
    await page.getByRole('button', { name: `Inspect organization-discovered publication ${organizationPublication.title}` }).click();
    const organizationSourceInspector = page.locator('.evidence-drawer');
    await expect(organizationSourceInspector).toContainText('Organization discovery provenance');
    await expect(organizationSourceInspector).toContainText(organizationPublication.organization_name);
    await expect(organizationSourceInspector).toContainText('Publication quality');
    await organizationSourceInspector.getByRole('button', { name: 'Close source inspector' }).click();
  }
  if (!openRouterLiveMode) {
    await expect(page.locator('.report-content')).toContainText('Model-generated synthesis and semantic citation checks did not run for this report.');
  }
  const targetCitationKey = inspectedFullTextTargetDoi
    ? citationKeys.find((key) => report.citation_map[key]?.doi?.toLowerCase() === inspectedFullTextTargetDoi.toLowerCase())
    : citationKeys[0];
  expect(targetCitationKey, `Expected a cited source with DOI ${inspectedFullTextTargetDoi || 'from the report'}`).toBeTruthy();
  const citation = page.getByRole('button', { name: `Open source ${targetCitationKey}` }).first();
  await expect(citation).toBeVisible();
  await citation.click();
  const sourceInspector = page.locator('.evidence-drawer');
  await expect(sourceInspector).toBeVisible();
  await expect(sourceInspector).toContainText('Evidence access class');
  await expect(sourceInspector.locator('.drawer-bottom')).toContainText(/Source metadata from (Crossref|OpenAlex|OpenAIRE|Official site WordPress search|World Bank Documents & Reports|GOV\.UK Search API)/);
  if (fullTextTargetDoi) {
    await expect(sourceInspector).toContainText('Europe PMC full-text status');
    await expect(sourceInspector).toContainText('retrieved');
    await expect(sourceInspector).toContainText('PERMITTED');
    await expect(sourceInspector.locator('.detail-list')).toContainText('Methods/Results available');
    await expect(sourceInspector.locator('.passage-stack')).toContainText('JATS Methods');
    await expect(sourceInspector.locator('.passage-stack')).toContainText('JATS Results');
  }
  if (repositoryFullTextTargetDoi) {
    await expect(sourceInspector).toContainText('OpenAIRE repository resolution');
    await expect(sourceInspector).toContainText('exact match');
    await expect(sourceInspector).toContainText('Strathprints');
    await expect(sourceInspector).toContainText('CC-BY');
    await expect(sourceInspector).toContainText('strathprints-research-copy-2026-11-01');
    await expect(sourceInspector.getByRole('link', { name: 'Open selected repository PDF' }))
      .toHaveAttribute('href', /^https:\/\/strathprints\.strath\.ac\.uk\/.+\.pdf$/);
    await expect(sourceInspector.locator('.passage-stack')).toContainText(/HVDC|transformer|offshore wind/i);
    await expect(sourceInspector.locator('.passage-chip small').first()).toContainText('SHA-256');
  }

  console.info('Live Veda report summary', JSON.stringify({
    jobId: savedJob.id,
    reportId: report.id,
    status: report.status,
    selectedSources: report.verification.search_coverage.selected_sources,
    candidateRecords: report.verification.search_coverage.candidate_ledger_records,
    citationCount: citationKeys.length,
    providerQueryCounts: report.verification.search_coverage.provider_query_counts,
    providerResultCounts: report.verification.search_coverage.provider_result_counts,
    organizationDiscovery: report.verification.search_coverage.organization_discovery,
    conditionalStatisticsRouting: report.verification.search_coverage.conditional_statistics_routing,
    governmentPublicationSearch: report.verification.search_coverage.government_publication_search,
    modelCallsReserved: savedJob.model_calls_reserved,
    estimatedCostUsd: savedJob.cost_spent_estimate_usd,
    openRouterLiveMode,
    fullTextTargetDoi,
    repositoryFullTextTargetDoi,
  }));

  const responses = apiResponses.map(({ url, method, status }) => ({
    path: new URL(url).pathname,
    origin: new URL(url).origin,
    method,
    status,
  }));
  expect(responses.some((item) => item.method === 'POST' && item.path === `/api/v1/research-jobs/${savedJob.id}/advance` && item.status === 200)).toBe(true);
  expect(responses.some((item) => item.method === 'GET' && item.path === `/api/v1/research-jobs/${savedJob.id}/report` && item.status === 200)).toBe(true);
  expect(responses.every((item) => item.origin === expectedApiOrigin && item.status < 400)).toBe(true);
});
