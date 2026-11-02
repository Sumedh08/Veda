import { afterEach, describe, expect, it, vi } from 'vitest';
import { API_BASE, ApiError, api, deleteVedaData, downloadAccountExport, downloadReport, getDataLifecycle, getDepthProfiles, getFollowUpContext, getHypotheses, getMessages, getPlan, getRelationships, getUserPreferences, inspectReport, listArchivedProjects, listConversations, listReports, resetUserPreferences, restoreProject, setTokenProvider, updateUserPreferences } from './api';

afterEach(() => {
  setTokenProvider(async () => null);
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe('API client', () => {
  it('sends the current bearer token and JSON request body', async () => {
    let captured: { url: RequestInfo | URL; init?: RequestInit } | undefined;
    vi.stubGlobal('fetch', vi.fn(async (url: RequestInfo | URL, init?: RequestInit) => {
      captured = { url, init };
      return new Response(JSON.stringify({ id: 'project-1' }), {
        status: 201,
        headers: { 'Content-Type': 'application/json' },
      });
    }));
    setTokenProvider(async () => 'session-token');

    const result = await api<{ id: string }>('/projects', {
      method: 'POST',
      body: JSON.stringify({ title: 'AI adoption' }),
    });

    expect(captured?.url).toBe(`${API_BASE}/projects`);
    const headers = new Headers(captured?.init?.headers);
    expect(headers.get('Authorization')).toBe('Bearer session-token');
    expect(headers.get('Content-Type')).toBe('application/json');
    expect(captured?.init?.body).toBe('{"title":"AI adoption"}');
    expect(result).toEqual({ id: 'project-1' });
  });

  it('does not invent an auth header when there is no session', async () => {
    let captured: RequestInit | undefined;
    vi.stubGlobal('fetch', vi.fn(async (_url: RequestInfo | URL, init?: RequestInit) => {
      captured = init;
      return new Response(JSON.stringify({ items: [] }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      });
    }));

    await api('/projects');

    expect(new Headers(captured?.headers).has('Authorization')).toBe(false);
  });

  it('returns undefined for an empty successful response', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response(null, { status: 204 })));
    await expect(api<void>('/projects/project-1', { method: 'DELETE' })).resolves.toBeUndefined();
  });

  it('uses the API error message without leaking provider payload details', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({
      error: { code: 'validation_error', message: 'The request did not pass validation.' },
      upstream: 'private diagnostic',
    }), { status: 422, headers: { 'Content-Type': 'application/json' } })));

    await expect(api('/projects')).rejects.toThrow('The request did not pass validation.');
  });

  it('preserves a validated response-header request ID and exposes a support reference', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({
      error: { code: 'storage_unavailable', message: 'Storage is temporarily unavailable. Please retry.', request_id: 'body-id' },
      upstream: 'private diagnostic',
    }), {
      status: 503,
      headers: { 'Content-Type': 'application/json', 'X-Request-ID': 'server:request-123' },
    })));

    const error = await api('/projects').catch((cause: unknown) => cause);
    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({ status: 503, code: 'storage_unavailable', requestId: 'server:request-123' });
    expect((error as Error).message).toContain('Reference ID: server:request-123');
    expect((error as Error).message).not.toContain('private diagnostic');
  });

  it('falls back to the validated JSON request ID if the header is absent or invalid', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({
      error: { code: 'internal_error', message: 'The request could not be completed.', request_id: 'valid.body-id' },
    }), {
      status: 500,
      headers: { 'Content-Type': 'application/json', 'X-Request-ID': 'invalid header' },
    })));

    const error = await api('/projects').catch((cause: unknown) => cause);
    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({ status: 500, code: 'internal_error', requestId: 'valid.body-id' });
    expect((error as Error).message).toContain('Reference ID: valid.body-id');
  });

  it('rejects malformed IDs and keeps the status fallback when no safe ID exists', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({
      error: { code: 'storage_error', message: 'The storage operation could not be completed.', request_id: '<script>alert(1)</script>' },
      upstream: 'private diagnostic',
    }), {
      status: 500,
      headers: { 'Content-Type': 'application/json', 'X-Request-ID': 'bad id' },
    })));

    const error = await api('/projects').catch((cause: unknown) => cause);
    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({ status: 500, code: 'storage_error', requestId: null });
    expect((error as Error).message).toBe('The storage operation could not be completed.');
    expect((error as Error).message).not.toContain('private diagnostic');
  });

  it('uses the same request-reference contract for account export failures', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({
      error: { code: 'storage_unavailable', message: 'Storage is temporarily unavailable. Please retry.', request_id: 'export-failure-1' },
    }), { status: 503, headers: { 'Content-Type': 'application/json' } })));

    const error = await downloadAccountExport().catch((cause: unknown) => cause);
    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({ status: 503, code: 'storage_unavailable', requestId: 'export-failure-1' });
    expect((error as Error).message).toContain('Reference ID: export-failure-1');
  });

  it('preserves the request reference for report export failures', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({
      error: { code: 'storage_unavailable', message: 'Storage is temporarily unavailable. Please retry.', request_id: 'report-export-1' },
    }), { status: 503, headers: { 'Content-Type': 'application/json' } })));

    const report = { id: 'report-1' } as Parameters<typeof downloadReport>[0];
    const error = await downloadReport(report, 'markdown').catch((cause: unknown) => cause);
    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({ status: 503, code: 'storage_unavailable', requestId: 'report-export-1' });
    expect((error as Error).message).toContain('Reference ID: report-export-1');
  });

  it('loads owner-protected comparison and hypothesis contracts for a research job', async () => {
    const urls: string[] = [];
    vi.stubGlobal('fetch', vi.fn(async (url: RequestInfo | URL) => {
      urls.push(String(url));
      return new Response(JSON.stringify({ items: [], status: 'not_assessed', message: 'Comparison has not run.' }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      });
    }));

    const [relationships, hypotheses] = await Promise.all([
      getRelationships('job-123'),
      getHypotheses('job-123'),
    ]);

    expect(urls).toEqual([
      `${API_BASE}/research-jobs/job-123/relationships`,
      `${API_BASE}/research-jobs/job-123/hypotheses`,
    ]);
    expect(relationships.status).toBe('not_assessed');
    expect(hypotheses.items).toEqual([]);
  });

  it('loads a bounded report history with project and archive filters', async () => {
    let capturedUrl = '';
    vi.stubGlobal('fetch', vi.fn(async (url: RequestInfo | URL) => {
      capturedUrl = String(url);
      return new Response(JSON.stringify({
        items: [], total: 0, limit: 10, offset: 20, has_more: false,
        version_semantics: 'Each immutable run has one report.',
      }), { status: 200, headers: { 'Content-Type': 'application/json' } });
    }));

    const page = await listReports({ projectId: 'project 123', includeArchived: true, limit: 10, offset: 20 });

    expect(capturedUrl).toBe(`${API_BASE}/reports?project_id=project+123&include_archived=true&limit=10&offset=20`);
    expect(page).toMatchObject({ total: 0, limit: 10, offset: 20, has_more: false });
  });

  it('loads a report with its archived-safe citation inspection bundle', async () => {
    let capturedUrl = '';
    vi.stubGlobal('fetch', vi.fn(async (url: RequestInfo | URL) => {
      capturedUrl = String(url);
      return new Response(JSON.stringify({ report: { id: 'report-123' }, job: { id: 'job-123' }, project: { id: 'project-123', archived_at: '2026-10-29T00:00:00Z' }, sources: [], claims: [] }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      });
    }));

    const inspection = await inspectReport('report-123');

    expect(capturedUrl).toBe(`${API_BASE}/reports/report-123/inspection`);
    expect(inspection.project.archived_at).toBe('2026-10-29T00:00:00Z');
  });

  it('loads persistent conversations, paged messages, and linked follow-up provenance', async () => {
    const urls: string[] = [];
    vi.stubGlobal('fetch', vi.fn(async (url: RequestInfo | URL) => {
      urls.push(String(url));
      return new Response(JSON.stringify({ items: [], status: 'not_a_follow_up', parent: null, claims: [] }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      });
    }));

    await Promise.all([
      listConversations('project-123'),
      getMessages('conversation-456'),
      getFollowUpContext('job-789'),
    ]);

    expect(urls).toEqual([
      `${API_BASE}/projects/project-123/conversations`,
      `${API_BASE}/conversations/conversation-456/messages?limit=200&offset=0`,
      `${API_BASE}/research-jobs/job-789/follow-up-context`,
    ]);
  });

  it('loads server-authoritative depth profiles for the research composer', async () => {
    const profiles = {
      quick: { name: 'quick', max_queries: 3, max_sources: 8 },
      standard: { name: 'standard', max_queries: 4, max_sources: 14 },
      deep: { name: 'deep', max_queries: 5, max_sources: 24 },
    };
    let capturedUrl = '';
    vi.stubGlobal('fetch', vi.fn(async (url: RequestInfo | URL) => {
      capturedUrl = String(url);
      return new Response(JSON.stringify({ profiles }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      });
    }));

    await expect(getDepthProfiles()).resolves.toEqual(profiles);
    expect(capturedUrl).toBe(`${API_BASE}/settings/depth-profiles`);
  });

  it('maps an uncreated plan to pending instead of an invalid plan object', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({ status: 'not_created' }), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    })));

    await expect(getPlan('job-123')).resolves.toBeNull();
  });

  it('loads a versioned decision-scoped plan with scope warnings and query rationale', async () => {
    const plan = {
      schema_version: 2,
      version: 2,
      planning_mode: 'deterministic_bounded_no_model',
      decision_context: { decision_objective: null, context: null, population: 'small firms', geography: 'India', time_horizon: null },
      scope_status: 'underspecified',
      missing_scope_fields: ['decision_objective', 'time_horizon'],
      scope_notice: 'Missing scope is not inferred.',
      queries: ['AI productivity counterevidence'],
      query_rationales: [{ query: 'AI productivity counterevidence', purpose: 'Search null findings.', focus: 'counterevidence' }],
      subquestions: [{ text: 'What evidence exists?', purpose: 'Answer within scope.' }],
      stopping_criteria: {
        execution: 'Use bounded queries.', insufficient_evidence: 'Abstain without evidence.',
        incomparability: 'Describe separately.', counterevidence: 'No hit does not prove none exists.',
      },
      resource_limits: { max_queries: 3 },
    };
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify(plan), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    })));

    await expect(getPlan('job-123')).resolves.toMatchObject({
      version: 2,
      scope_status: 'underspecified',
      query_rationales: [{ focus: 'counterevidence' }],
    });
  });

  it('loads preferences and lifecycle capabilities and saves, resets, restores archived data', async () => {
    const requests: Array<{ url: string; method: string }> = [];
    vi.stubGlobal('fetch', vi.fn(async (url: RequestInfo | URL, init?: RequestInit) => {
      requests.push({ url: String(url), method: init?.method || 'GET' });
      return new Response(JSON.stringify({ items: [] }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      });
    }));

    await Promise.all([
      getUserPreferences(), getDataLifecycle(), listArchivedProjects(),
        updateUserPreferences({ default_depth: 'deep', default_budget_ceiling_usd: 1, retention_days: 30 }),
      resetUserPreferences(), restoreProject('archived-project'), deleteVedaData('DELETE VEDA DATA'),
    ]);

    expect(requests).toEqual([
      { url: `${API_BASE}/me/preferences`, method: 'GET' },
      { url: `${API_BASE}/me/data-lifecycle`, method: 'GET' },
      { url: `${API_BASE}/projects?archived_only=true&limit=100&offset=0`, method: 'GET' },
      { url: `${API_BASE}/me/preferences`, method: 'PATCH' },
      { url: `${API_BASE}/me/preferences`, method: 'DELETE' },
      { url: `${API_BASE}/projects/archived-project/restore`, method: 'POST' },
      { url: `${API_BASE}/me/data`, method: 'DELETE' },
    ]);
  });
});
