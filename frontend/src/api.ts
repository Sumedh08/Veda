import type { Claim, ClaimEvidence, ComparisonCollection, CompetingHypothesis, Conversation, ConversationMessage, DataLifecycle, DepthProfile, DiscoveryCandidate, EvidenceRelationship, FollowUpContext, JobEvent, Passage, Project, ReportHistory, ReportInspection, ResearchJob, ResearchPlan, ResearchReport, Source, UserPreferences, VedaDataPurgeResult } from './types';

const env = (import.meta as ImportMeta & { env: Record<string, string | undefined> }).env;
export const API_BASE = (env.VITE_API_BASE_URL || 'http://localhost:8000/api/v1').replace(/\/$/, '');

let tokenProvider: () => Promise<string | null> = async () => null;
let unauthorizedHandler: (() => void) | null = null;
const REQUEST_ID_PATTERN = /^[A-Za-z0-9._:-]{1,128}$/;

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly code: string | null,
    readonly requestId: string | null,
  ) {
    super(requestId ? `${message} (Reference ID: ${requestId})` : message);
    this.name = 'ApiError';
  }
}

function safeRequestId(value: unknown): string | null {
  return typeof value === 'string' && REQUEST_ID_PATTERN.test(value) ? value : null;
}

async function apiErrorFromResponse(response: Response, fallback: string): Promise<ApiError> {
  let body: Record<string, unknown> = {};
  try {
    const parsed: unknown = await response.json();
    if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) body = parsed as Record<string, unknown>;
  } catch {
    // Preserve the HTTP status when a service returns a non-JSON error page.
  }
  const error = body.error && typeof body.error === 'object' && !Array.isArray(body.error)
    ? body.error as Record<string, unknown>
    : {};
  const rawMessage = typeof error.message === 'string'
    ? error.message
    : typeof body.detail === 'string'
      ? body.detail
      : fallback;
  const message = rawMessage.replace(/[\u0000-\u001f\u007f]/g, ' ').trim().slice(0, 500) || fallback;
  const rawCode = error.code;
  const code = typeof rawCode === 'string' && /^[a-z][a-z0-9_]{0,63}$/.test(rawCode) ? rawCode : null;
  const requestId = safeRequestId(response.headers.get('X-Request-ID')) ?? safeRequestId(error.request_id);
  return new ApiError(message, response.status, code, requestId);
}

export function setTokenProvider(provider: () => Promise<string | null>) {
  tokenProvider = provider;
}
export function setUnauthorizedHandler(handler: (() => void) | null) {
  unauthorizedHandler = handler;
}

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = await tokenProvider();
  const headers = new Headers(init.headers);
  if (init.body && !headers.has('Content-Type')) headers.set('Content-Type', 'application/json');
  if (token) headers.set('Authorization', `Bearer ${token}`);
  const response = await fetch(`${API_BASE}${path}`, { ...init, headers });
  if (!response.ok) {
    if (response.status === 401 && token) unauthorizedHandler?.();
    throw await apiErrorFromResponse(response, `Request failed (${response.status})`);
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export const listProjects = async () => (await api<{ items: Project[] }>('/projects')).items;
export const listArchivedProjects = async () => {
  const archived: Project[] = [];
  const limit = 100;
  for (let offset = 0; ; offset += limit) {
    const page = await api<{ items: Project[] }>(`/projects?archived_only=true&limit=${limit}&offset=${offset}`);
    archived.push(...page.items);
    if (page.items.length < limit) return archived;
  }
};
export const createProject = (data: { title: string; description: string; domain: string }) =>
  api<Project>('/projects', { method: 'POST', body: JSON.stringify(data) });
export const updateProject = (id: string, data: { title: string; description: string; domain: string }) =>
  api<Project>(`/projects/${id}`, { method: 'PATCH', body: JSON.stringify(data) });
export const archiveProject = (id: string) => api<void>(`/projects/${id}`, { method: 'DELETE' });
export const restoreProject = (id: string) => api<Project>(`/projects/${id}/restore`, { method: 'POST' });
export const permanentlyDeleteProject = (id: string, projectTitle: string) =>
  api<void>(`/projects/${id}/permanent`, {
    method: 'DELETE',
    body: JSON.stringify({ confirmation: 'DELETE', project_title: projectTitle }),
  });
export const getUserPreferences = () => api<UserPreferences>('/me/preferences');
export const updateUserPreferences = (data: Pick<UserPreferences, 'default_depth' | 'default_budget_ceiling_usd' | 'retention_days'>) =>
  api<UserPreferences>('/me/preferences', { method: 'PATCH', body: JSON.stringify(data) });
export const resetUserPreferences = () => api<UserPreferences>('/me/preferences', { method: 'DELETE' });
export const getDataLifecycle = () => api<DataLifecycle>('/me/data-lifecycle');
export const deleteVedaData = (confirmation: 'DELETE VEDA DATA') =>
  api<VedaDataPurgeResult>('/me/data', {
    method: 'DELETE',
    body: JSON.stringify({ confirmation }),
  });
export async function downloadAccountExport(): Promise<void> {
  const token = await tokenProvider();
  const headers = new Headers();
  if (token) headers.set('Authorization', `Bearer ${token}`);
  const response = await fetch(`${API_BASE}/me/export`, { headers });
  if (!response.ok) {
    if (response.status === 401 && token) unauthorizedHandler?.();
    throw await apiErrorFromResponse(response, `Request failed (${response.status})`);
  }
  const blob = await response.blob();
  const disposition = response.headers.get('Content-Disposition') || '';
  const filename = disposition.match(/filename="?([^";]+)"?/i)?.[1] || 'veda-account-export.json';
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  link.click();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}
export const listJobs = async (projectId: string) =>
  (await api<{ items: ResearchJob[] }>(`/projects/${projectId}/research-jobs`)).items;
export const listConversations = async (projectId: string) =>
  (await api<{ items: Conversation[] }>(`/projects/${projectId}/conversations`)).items;
export const getMessages = (conversationId: string, offset = 0) =>
  api<{ items: ConversationMessage[]; limit: number; offset: number; has_more: boolean }>(`/conversations/${conversationId}/messages?limit=200&offset=${offset}`);
export const getFollowUpContext = (jobId: string) =>
  api<FollowUpContext>(`/research-jobs/${jobId}/follow-up-context`);
export const getDepthProfiles = async () =>
  (await api<{ profiles: Record<DepthProfile['name'], DepthProfile> }>('/settings/depth-profiles')).profiles;
export const createJob = (projectId: string, data: Record<string, unknown>) =>
  api<ResearchJob>(`/projects/${projectId}/research-jobs`, { method: 'POST', body: JSON.stringify(data) });
export const getJob = (id: string) => api<ResearchJob>(`/research-jobs/${id}`);
export const advanceJob = (id: string, operationKey: string) =>
  api<ResearchJob>(`/research-jobs/${id}/advance`, { method: 'POST', body: JSON.stringify({ operation_key: operationKey }) });
export const resumeJob = (id: string) => api<ResearchJob>(`/research-jobs/${id}/resume`, { method: 'POST' });
export const retryDeferredRetrieval = (id: string) =>
  api<{ job: ResearchJob; queued_retry_count: number; idempotent_replay: boolean }>(
    `/research-jobs/${id}/retry-deferred`, { method: 'POST' },
  );
export const pauseJob = (id: string) => api<ResearchJob>(`/research-jobs/${id}/pause`, { method: 'POST' });
export const cancelJob = (id: string) => api<ResearchJob>(`/research-jobs/${id}/cancel`, { method: 'POST' });
function isUncreatedPlan(response: ResearchPlan | { status: 'not_created' }): response is { status: 'not_created' } {
  return 'status' in response && response.status === 'not_created';
}
export const getPlan = async (id: string): Promise<ResearchPlan | null> => {
  const response = await api<ResearchPlan | { status: 'not_created' }>(`/research-jobs/${id}/plan`);
  return isUncreatedPlan(response) ? null : response;
};
export const getEvents = async (id: string) => (await api<{ items: JobEvent[] }>(`/research-jobs/${id}/events`)).items;
export const getSources = async (id: string) => (await api<{ items: Source[] }>(`/research-jobs/${id}/sources`)).items;
export const getCandidates = async (id: string) => (await api<{ items: DiscoveryCandidate[] }>(`/research-jobs/${id}/candidates?limit=200`)).items;
export const getClaims = async (id: string) => (await api<{ items: Claim[] }>(`/research-jobs/${id}/claims`)).items;
export const getRelationships = (id: string) => api<ComparisonCollection<EvidenceRelationship>>(`/research-jobs/${id}/relationships`);
export const getHypotheses = (id: string) => api<ComparisonCollection<CompetingHypothesis>>(`/research-jobs/${id}/hypotheses`);
export const getReport = (id: string) => api<ResearchReport>(`/research-jobs/${id}/report`);
export const listReports = (options: { projectId?: string; includeArchived?: boolean; limit?: number; offset?: number } = {}) => {
  const query = new URLSearchParams();
  if (options.projectId) query.set('project_id', options.projectId);
  if (options.includeArchived) query.set('include_archived', 'true');
  if (options.limit !== undefined) query.set('limit', String(options.limit));
  if (options.offset !== undefined) query.set('offset', String(options.offset));
  const suffix = query.size ? `?${query.toString()}` : '';
  return api<ReportHistory>(`/reports${suffix}`);
};
export const inspectReport = (reportId: string) => api<ReportInspection>(`/reports/${reportId}/inspection`);
export const getSource = (id: string) => api<Source>(`/sources/${id}`);
export const getPassage = (id: string) => api<Passage>(`/passages/${id}`);
export const getClaimEvidence = (id: string) => api<ClaimEvidence>(`/claims/${id}/evidence`);

export async function downloadReport(report: ResearchReport, format: 'markdown' | 'json') {
  const token = await tokenProvider();
  const response = await fetch(`${API_BASE}/reports/${report.id}/export?format=${format}`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (response.status === 401 && token) unauthorizedHandler?.();
  if (!response.ok) throw await apiErrorFromResponse(response, 'Could not export this report.');
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = `veda-report-${report.id}.${format === 'json' ? 'json' : 'md'}`;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

