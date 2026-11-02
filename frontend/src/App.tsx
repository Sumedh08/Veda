import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { createClient, type Session, type SupabaseClient } from '@supabase/supabase-js';
import {
  Activity, ArrowLeft, ArrowRight, Archive, BookOpen, Check, ChevronDown, CircleHelp,
  Clipboard, Download, ExternalLink, FileText, FlaskConical, FolderKanban, KeyRound,
  Layers3, LoaderCircle, LockKeyhole, LogOut, Menu, MessageSquareText, Pause, Pencil, Plus, RefreshCw, Search, ShieldCheck,
  Settings2, Sparkles, X,
} from 'lucide-react';
import * as apiClient from './api';
import { API_BASE, api, setTokenProvider, setUnauthorizedHandler } from './api';
import { linkifyCitationMarkers } from './citations';
import { latestModelExecutionPlan, type ModelExecutionPlan } from './executionPlan';
import type { Claim, ClaimEvidence, Conversation, ConversationMessage, DataLifecycle, DepthProfile, DiscoveryCandidate, EvidenceLink, EvidenceRelationship, CompetingHypothesis, FollowUpContext, JobEvent, Passage, Project, ReportHistoryItem, ReportInspection, ResearchJob, ResearchPlan, ResearchReport, Source, StatisticsRouteOutcome, UserPreferences } from './types';

const env = (import.meta as ImportMeta & { env: Record<string, string | undefined> }).env;
const supabaseUrl = env.VITE_SUPABASE_URL || '';
const supabaseAnonKey = env.VITE_SUPABASE_ANON_KEY || '';
const supabaseConfigIncomplete = Boolean(supabaseUrl) !== Boolean(supabaseAnonKey);
const supabase: SupabaseClient | null = supabaseUrl && supabaseAnonKey
  ? createClient(supabaseUrl, supabaseAnonKey, { auth: { persistSession: true, autoRefreshToken: true, detectSessionInUrl: true } })
  : null;

type Identity = { token: string; provider: 'local-development' | 'supabase'; email?: string };
type Toast = { kind: 'error' | 'success'; text: string };

const terminal = (job?: ResearchJob | null) => !!job && ['completed', 'completed_with_limitations', 'canceled', 'terminal_failure', 'budget_exhausted'].includes(job.status);
const stages = ['planning', 'discovery', 'extraction', 'appraisal', 'comparison', 'verification', 'synthesis', 'complete'];

function useIdentity() {
  const [identity, setIdentity] = useState<Identity | null>(() => readLocalDevelopmentIdentity(!!supabase || supabaseConfigIncomplete));
  const [authReady, setAuthReady] = useState(!supabase);
  const [authError, setAuthError] = useState('');

  useEffect(() => {
    if (!supabase) return;
    let live = true;
    supabase.auth.getSession().then(({ data, error }) => {
      if (!live) return;
      if (error) setAuthError(error.message);
      setIdentityFromSession(data.session, setIdentity);
      setAuthReady(true);
    }).catch(() => {
      if (!live) return;
      setIdentity(null);
      setAuthError('Could not read the managed sign-in session.');
      setAuthReady(true);
    });
    const { data: listener } = supabase.auth.onAuthStateChange((_event, session) => setIdentityFromSession(session, setIdentity));
    return () => { live = false; listener.subscription.unsubscribe(); };
  }, []);

  const getToken = useCallback(async () => {
    if (!supabase) return identity?.token || null;
    const { data } = await supabase.auth.getSession();
    return data.session?.access_token || null;
  }, [identity]);
  useEffect(() => { setTokenProvider(getToken); }, [getToken]);
  useEffect(() => {
    setUnauthorizedHandler(() => {
      sessionStorage.removeItem('veda_local_session');
      setIdentity(null);
      if (supabase) void supabase.auth.signOut();
    });
    return () => setUnauthorizedHandler(null);
  }, []);

  const signIn = async (email?: string) => {
    setAuthError('');
    if (!supabase) {
      try {
        const response = await fetch(`${API_BASE}/auth/dev-session`, { method: 'POST' });
        if (!response.ok) throw new Error('Local sign-in is disabled. Enable it only for development in the backend environment.');
        const data = await response.json();
        const next: Identity = { token: data.access_token, provider: 'local-development' };
        sessionStorage.setItem('veda_local_session', JSON.stringify(next));
        setIdentity(next);
      } catch (error) { setAuthError(error instanceof Error ? error.message : 'Could not start a local session.'); }
      return;
    }
    sessionStorage.removeItem('veda_local_session');
    if (!email?.trim()) { setAuthError('Enter your email to receive a sign-in link.'); return; }
    const { error } = await supabase.auth.signInWithOtp({
      email: email.trim(),
      options: { emailRedirectTo: window.location.origin },
    });
    if (error) setAuthError(error.message);
    else setAuthError('Check your inbox for a secure sign-in link.');
  };

  const signOut = async () => {
    if (supabase) await supabase.auth.signOut();
    sessionStorage.removeItem('veda_local_session');
    setIdentity(null);
  };

  return {
    identity,
    authReady,
    authError,
    signIn,
    signOut,
    managed: !!supabase,
    configurationError: supabaseConfigIncomplete
      ? 'Managed authentication is partially configured. Set both VITE_SUPABASE_URL and VITE_SUPABASE_ANON_KEY, or clear both to use local development authentication.'
      : '',
  };
}

function readLocalDevelopmentIdentity(managedAuthConfigured: boolean): Identity | null {
  try {
    if (managedAuthConfigured) {
      sessionStorage.removeItem('veda_local_session');
      return null;
    }
    const saved = sessionStorage.getItem('veda_local_session');
    if (!saved) return null;
    const parsed = JSON.parse(saved) as Partial<Identity>;
    if (parsed.provider !== 'local-development' || typeof parsed.token !== 'string' || !parsed.token.trim()) {
      sessionStorage.removeItem('veda_local_session');
      return null;
    }
    return { token: parsed.token, provider: 'local-development', ...(typeof parsed.email === 'string' ? { email: parsed.email } : {}) };
  } catch {
    try { sessionStorage.removeItem('veda_local_session'); } catch { /* Storage may be unavailable in restricted browser contexts. */ }
    return null;
  }
}

function setIdentityFromSession(session: Session | null, setter: (value: Identity | null) => void) {
  setter(session ? { token: session.access_token, provider: 'supabase', email: session.user.email } : null);
}

export default function App() {
  const auth = useIdentity();
  const [projects, setProjects] = useState<Project[]>([]);
  const [selectedProject, setSelectedProject] = useState<Project | null>(null);
  const [activeJob, setActiveJob] = useState<ResearchJob | null>(null);
  const [toast, setToast] = useState<Toast | null>(null);
  const [loadingProjects, setLoadingProjects] = useState(false);
  const [projectLoadError, setProjectLoadError] = useState('');
  const [mobileNav, setMobileNav] = useState(false);
  const [showPreferences, setShowPreferences] = useState(false);
  const [showReports, setShowReports] = useState(false);

  const notifyError = useCallback((error: unknown) => {
    setToast({ kind: 'error', text: error instanceof Error ? error.message : 'Something went wrong.' });
  }, []);

  const refreshProjects = useCallback(async () => {
    if (!auth.identity) return;
    setLoadingProjects(true);
    setProjectLoadError('');
    try {
      const items = await apiClient.listProjects();
      setProjects(items);
      setSelectedProject((selected) => selected ? items.find((item) => item.id === selected.id) || null : null);
    } catch (error) {
      setProjectLoadError(error instanceof Error ? error.message : 'Could not load your projects.');
      notifyError(error);
    }
    finally { setLoadingProjects(false); }
  }, [auth.identity, notifyError]);

  useEffect(() => { if (auth.identity) void refreshProjects(); }, [auth.identity, refreshProjects]);

  const createNewProject = async (data: { title: string; description: string; domain: string }) => {
    const project = await apiClient.createProject(data);
    setProjects((current) => [project, ...current]);
    setSelectedProject(project);
    setActiveJob(null);
    setShowReports(false);
  };

  const archive = async (project: Project) => {
    await apiClient.archiveProject(project.id);
    setProjects((current) => current.filter((item) => item.id !== project.id));
    setSelectedProject(null);
    setActiveJob(null);
    setShowReports(false);
    setToast({ kind: 'success', text: 'Project archived.' });
  };

  const updateProject = async (project: Project, data: { title: string; description: string; domain: string }) => {
    const updated = await apiClient.updateProject(project.id, data);
    setProjects((current) => current.map((item) => item.id === updated.id ? updated : item));
    setSelectedProject(updated);
  };

  if (!auth.authReady) return <div className="boot"><LoaderCircle className="spin" /><span>Securing your session…</span></div>;
  if (auth.configurationError) return <AuthConfigurationError message={auth.configurationError} />;
  if (!auth.identity) return <SignIn managed={auth.managed} error={auth.authError} onSignIn={auth.signIn} />;

  const handleSelectProject = (project: Project) => {
    setSelectedProject(project);
    setActiveJob(null);
    setShowReports(false);
    setMobileNav(false);
  };

  return (
    <div className="app-shell">
      <div className={`sidebar-backdrop ${mobileNav ? 'visible' : ''}`} onClick={() => setMobileNav(false)} />
      <aside className={`sidebar ${mobileNav ? 'open' : ''}`}>
        <div className="brand"><div className="brand-mark"><span>V</span></div><div><b>veda</b><small>RESEARCH STUDIO</small></div></div>
        <div className="sidebar-label">WORKSPACE</div>
        <button className={`nav-item ${!selectedProject && !showReports ? 'selected' : ''}`} onClick={() => { setSelectedProject(null); setActiveJob(null); setShowReports(false); setMobileNav(false); }}>
          <Layers3 size={17} /><span>Overview</span><span className="nav-count">{projects.length}</span>
        </button>
        <button className={`nav-item ${showReports ? 'selected' : ''}`} onClick={() => { setSelectedProject(null); setActiveJob(null); setShowReports(true); setMobileNav(false); }}>
          <FileText size={17} /><span>Reports</span>
        </button>
        <div className="sidebar-label section-label"><span>YOUR PROJECTS</span><button title="New project" onClick={() => window.dispatchEvent(new Event('veda:new-project'))}><Plus size={15} /></button></div>
        <div className="project-nav-list">
          {projects.map((project) => (
            <button key={project.id} className={`nav-item project-nav ${selectedProject?.id === project.id ? 'selected' : ''}`} onClick={() => handleSelectProject(project)}>
              <span className="project-dot" /><span className="truncate">{project.title}</span>
            </button>
          ))}
          {!projects.length && <p className="sidebar-empty">Your research projects will appear here.</p>}
        </div>
        <div className="sidebar-bottom">
          <div className="security-note"><ShieldCheck size={16} /><span><b>Private by design</b><small>Research stays in your workspace.</small></span></div>
          <button className="profile-row" onClick={auth.signOut} title="Sign out">
            <div className="avatar">{auth.identity.email?.[0]?.toUpperCase() || 'V'}</div>
            <span className="profile-name">{auth.identity.email || 'Local researcher'}<small>{auth.identity.provider === 'local-development' ? 'LOCAL DEVELOPMENT' : 'SIGNED IN'}</small></span>
            <LogOut size={15} />
          </button>
        </div>
      </aside>

      <main className="main-shell">
        <header className="topbar">
          <button className="icon-button menu-button" aria-label="Open navigation" onClick={() => setMobileNav(true)}><Menu size={20} /></button>
          <div className="breadcrumb"><span>Workspace</span><span className="crumb-slash">/</span><b>{activeJob ? 'Research run' : showReports ? 'Reports' : selectedProject?.title || 'Overview'}</b></div>
          <div className="topbar-right"><span className="online-dot" /> <span>Evidence-first mode</span><button className="icon-button" aria-label="Preferences and data" title="Preferences and data lifecycle" onClick={() => setShowPreferences(true)}><Settings2 size={17} /></button><button className="icon-button help-button" aria-label="About Veda" title="Veda reports evidence status and limitations explicitly."><CircleHelp size={18} /></button></div>
        </header>

        <div className="page-content">
          {showReports ? (
            <ReportHistoryPage projects={projects} onError={notifyError} />
          ) : activeJob && selectedProject ? (
            <JobWorkspace project={selectedProject} jobId={activeJob.id} onBack={() => setActiveJob(null)} onStartJob={setActiveJob} onError={notifyError} />
          ) : selectedProject ? (
            <ProjectWorkspace project={selectedProject} onBack={() => setSelectedProject(null)} onUpdate={(data) => updateProject(selectedProject, data)} onStartJob={setActiveJob} onArchive={() => void archive(selectedProject)} onError={notifyError} />
          ) : (
            <Dashboard projects={projects} loading={loadingProjects} loadError={projectLoadError} onCreate={createNewProject} onSelect={handleSelectProject} onRefresh={() => void refreshProjects()} onError={notifyError} />
          )}
        </div>
      </main>
      {showPreferences && <PreferencesModal onClose={() => setShowPreferences(false)} onProjectsChanged={() => refreshProjects()} onVedaDataDeleted={async () => { setActiveJob(null); setShowReports(false); await refreshProjects(); }} />}
      {toast && <div className={`toast ${toast.kind}`} role="status"><span>{toast.text}</span><button onClick={() => setToast(null)} aria-label="Dismiss"><X size={15} /></button></div>}
    </div>
  );
}

function ReportHistoryPage({ projects, onError }: { projects: Project[]; onError: (error: unknown) => void }) {
  const [archivedProjects, setArchivedProjects] = useState<Project[]>([]);
  const [items, setItems] = useState<ReportHistoryItem[]>([]);
  const [total, setTotal] = useState(0);
  const [hasMore, setHasMore] = useState(false);
  const [offset, setOffset] = useState(0);
  const [projectId, setProjectId] = useState('');
  const [includeArchived, setIncludeArchived] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [selected, setSelected] = useState<ReportHistoryItem | null>(null);
  const [reloadKey, setReloadKey] = useState(0);
  const limit = 10;

  useEffect(() => {
    let active = true;
    apiClient.listArchivedProjects().then((archived) => { if (active) setArchivedProjects(archived); })
      .catch((cause: unknown) => { if (active) onError(cause); });
    return () => { active = false; };
  }, [onError]);

  useEffect(() => {
    let active = true;
    setLoading(true); setError('');
    apiClient.listReports({ projectId: projectId || undefined, includeArchived, limit, offset })
      .then((page) => {
        if (!active) return;
        setItems(page.items); setTotal(page.total); setHasMore(page.has_more);
      })
      .catch((cause: unknown) => {
        if (!active) return;
        const message = cause instanceof Error ? cause.message : 'Could not load report history.';
        setError(message); onError(cause);
      })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [projectId, includeArchived, limit, offset, reloadKey, onError]);

  if (selected) return <HistoricalReportReader item={selected} onBack={() => setSelected(null)} onError={onError} />;

  const projectOptions = [...projects, ...archivedProjects];
  return <div className="report-history-page">
    <div className="welcome-row"><div><p className="eyebrow">SAVED EVIDENCE MAPS</p><h1>Report history</h1><p className="welcome-copy">Open the report saved for each completed run, inspect its cited passages, or export that exact report.</p></div><div className="welcome-seal"><FileText size={22} /><small>IMMUTABLE RUNS</small></div></div>
    <section className="content-card report-history-card">
      <div className="report-history-toolbar">
        <label className="history-project-filter">Project<select aria-label="Filter reports by project" value={projectId} onChange={(event) => { const nextId = event.target.value; setProjectId(nextId); setOffset(0); if (projectOptions.find((project) => project.id === nextId)?.archived_at) setIncludeArchived(true); }}><option value="">All projects</option>{projectOptions.filter((project, index, all) => all.findIndex((item) => item.id === project.id) === index).map((project) => <option value={project.id} key={project.id}>{project.title}{project.archived_at ? ' · archived' : ''}</option>)}</select></label>
        <label className="history-archived-filter"><input type="checkbox" checked={includeArchived} onChange={(event) => { setIncludeArchived(event.target.checked); setOffset(0); }} />Include archived projects</label>
        <span className="history-total">{total} {total === 1 ? 'report' : 'reports'}</span>
      </div>
      <p className="drawer-footnote report-version-note">Each immutable research run has one saved report. The displayed schema version describes the report format, not a later revision of the research.</p>
      {loading ? <div className="loading-panel"><LoaderCircle className="spin" /><span>Loading saved reports…</span></div> : error ? <div className="error-panel report-history-error"><p>{error}</p><button className="quiet-button" onClick={() => setReloadKey((value) => value + 1)}>Retry</button></div> : items.length ? <div className="report-history-list">{items.map((item) => <article className="report-history-row" key={item.id}><div className="report-history-copy"><span className="eyebrow">{item.project_title}{item.project_archived_at ? ' · ARCHIVED' : ''}</span><h2>{item.question}</h2><div className="report-history-meta"><span>{prettyStatus(item.status)}</span><span>Schema v{item.version}</span><time dateTime={item.created_at}>{new Date(item.created_at).toLocaleString()}</time><span>{Object.keys(item.citation_map).length} citations</span></div></div><button className="primary-button" onClick={() => setSelected(item)}><BookOpen size={14} /> Open report</button></article>)}</div> : <div className="not-ready report-history-empty">{includeArchived ? 'No saved reports match these filters.' : 'No saved reports yet. Completed research runs will appear here.'}</div>}
      <div className="report-history-pagination"><span>Showing {total === 0 ? 0 : offset + 1}–{Math.min(offset + limit, total)} of {total}</span><div><button className="quiet-button" disabled={offset === 0 || loading} onClick={() => setOffset((value) => Math.max(0, value - limit))}><ArrowLeft size={14} /> Previous</button><button className="quiet-button" disabled={!hasMore || loading} onClick={() => setOffset((value) => value + limit)}>Next <ArrowRight size={14} /></button></div></div>
    </section>
  </div>;
}

function HistoricalReportReader({ item, onBack, onError }: { item: ReportHistoryItem; onBack: () => void; onError: (error: unknown) => void }) {
  const [inspection, setInspection] = useState<ReportInspection | null>(null);
  const [error, setError] = useState('');
  const [selectedSource, setSelectedSource] = useState<Source | null>(null);
  const [selectedClaim, setSelectedClaim] = useState<Claim | null>(null);
  const [claimEvidence, setClaimEvidence] = useState<ClaimEvidence | null>(null);

  useEffect(() => {
    let active = true;
    setInspection(null); setError(''); setSelectedSource(null); setSelectedClaim(null); setClaimEvidence(null);
    apiClient.inspectReport(item.id).then((data) => { if (active) setInspection(data); })
      .catch((cause: unknown) => {
        if (!active) return;
        setError(cause instanceof Error ? cause.message : 'Could not open this saved report.');
        onError(cause);
      });
    return () => { active = false; };
  }, [item.id, onError]);

  const selectClaim = (claim: Claim) => {
    const source = inspection?.sources.find((candidate) => candidate.id === claim.source_id);
    const passage = source?.passages?.find((candidate) => candidate.id === claim.passage_id);
    if (!source || !passage || !inspection) {
      onError(new Error('The saved report does not contain the exact passage needed to inspect this claim.'));
      return;
    }
    const linkedIds = claim.appraisal?.methodology_appraisal?.passage_ids || [];
    const methodology_passages = (source.passages || []).filter((item) => linkedIds.includes(item.id));
    setClaimEvidence({ claim, source, passage, methodology_passages });
    setSelectedClaim(claim);
  };

  return <div className="historical-report-page"><button className="back-link" onClick={onBack}><ArrowLeft size={15} /> Report history</button>
    <div className="historical-report-heading"><div><p className="eyebrow">{item.project_title}{item.project_archived_at ? ' · ARCHIVED PROJECT' : ''} · {prettyStatus(item.status)}</p><h1>{item.question}</h1><p>Saved {new Date(item.created_at).toLocaleString()} · Report schema v{item.version} · One immutable report per research run.</p></div><span className="status-pill completed">{Object.keys(item.citation_map).length} citations</span></div>
    {error ? <section className="content-card error-panel"><p>{error}</p><button className="quiet-button" onClick={() => setError('')}>Close error</button></section> : !inspection ? <div className="loading-panel"><LoaderCircle className="spin" /><span>Loading report and saved citation evidence…</span></div> : <ReportPanel report={inspection.report} job={inspection.job} sources={inspection.sources} claims={inspection.claims} onSelectClaim={selectClaim} onSelectSource={setSelectedSource} onError={onError} />}
    {selectedSource && <SourceDrawer source={selectedSource} onClose={() => setSelectedSource(null)} />}
    {selectedClaim && claimEvidence && <EvidenceDrawer claim={selectedClaim} preloadedEvidence={claimEvidence} onClose={() => { setSelectedClaim(null); setClaimEvidence(null); }} />}
  </div>;
}

function PreferencesModal({ onClose, onProjectsChanged, onVedaDataDeleted }: { onClose: () => void; onProjectsChanged: () => Promise<void>; onVedaDataDeleted: () => Promise<void> }) {
  const [preferences, setPreferences] = useState<UserPreferences | null>(null);
  const [lifecycle, setLifecycle] = useState<DataLifecycle | null>(null);
  const [archivedProjects, setArchivedProjects] = useState<Project[]>([]);
  const [depth, setDepth] = useState<UserPreferences['default_depth']>('standard');
  const [budget, setBudget] = useState('0');
  const [retentionDays, setRetentionDays] = useState<UserPreferences['retention_days']>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [deleteProjectId, setDeleteProjectId] = useState<string | null>(null);
  const [deleteTitle, setDeleteTitle] = useState('');
  const [deleteVedaDataExpanded, setDeleteVedaDataExpanded] = useState(false);
  const [deleteVedaDataConfirmation, setDeleteVedaDataConfirmation] = useState('');
  const [dataDeletionResult, setDataDeletionResult] = useState('');

  useEffect(() => {
    let active = true;
    Promise.all([apiClient.getUserPreferences(), apiClient.getDataLifecycle(), apiClient.listArchivedProjects()])
      .then(([savedPreferences, dataLifecycle, archived]) => {
        if (!active) return;
        setPreferences(savedPreferences); setDepth(savedPreferences.default_depth);
        setBudget(String(savedPreferences.default_budget_ceiling_usd));
        setRetentionDays(savedPreferences.retention_days ?? null);
        setLifecycle(dataLifecycle); setArchivedProjects(archived);
      })
      .catch((cause: unknown) => { if (active) setError(cause instanceof Error ? cause.message : 'Could not load preferences.'); });
    return () => { active = false; };
  }, []);

  const save = async () => {
    setBusy(true); setError('');
    try {
      setPreferences(await apiClient.updateUserPreferences({ default_depth: depth, default_budget_ceiling_usd: Number(budget), retention_days: retentionDays }));
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'Could not save preferences.'); }
    finally { setBusy(false); }
  };
  const reset = async () => {
    setBusy(true); setError('');
    try {
      const defaults = await apiClient.resetUserPreferences();
      setPreferences(defaults); setDepth(defaults.default_depth); setBudget(String(defaults.default_budget_ceiling_usd));
      setRetentionDays(defaults.retention_days);
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'Could not reset preferences.'); }
    finally { setBusy(false); }
  };
  const restore = async (project: Project) => {
    setBusy(true); setError('');
    try {
      await apiClient.restoreProject(project.id);
      setArchivedProjects((items) => items.filter((item) => item.id !== project.id));
      await onProjectsChanged();
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'Could not restore project.'); }
    finally { setBusy(false); }
  };
  const exportAccount = async () => {
    setBusy(true); setError('');
    try { await apiClient.downloadAccountExport(); }
    catch (cause) { setError(cause instanceof Error ? cause.message : 'Could not download your account export.'); }
    finally { setBusy(false); }
  };
  const permanentlyDelete = async (project: Project) => {
    if (deleteTitle.trim() !== project.title) return;
    setBusy(true); setError('');
    try {
      await apiClient.permanentlyDeleteProject(project.id, deleteTitle.trim());
      setArchivedProjects((items) => items.filter((item) => item.id !== project.id));
      setDeleteProjectId(null); setDeleteTitle('');
      await onProjectsChanged();
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'Could not permanently delete this project.'); }
    finally { setBusy(false); }
  };
  const permanentlyDeleteVedaData = async () => {
    if (deleteVedaDataConfirmation !== 'DELETE VEDA DATA') return;
    setBusy(true); setError(''); setDataDeletionResult('');
    try {
      const result = await apiClient.deleteVedaData('DELETE VEDA DATA');
      setArchivedProjects([]);
      setDeleteProjectId(null); setDeleteTitle('');
      setPreferences({
        default_depth: 'standard', default_budget_ceiling_usd: 0, retention_days: null,
        is_customized: false, updated_at: null,
      });
      setDepth('standard'); setBudget('0'); setRetentionDays(null);
      setDeleteVedaDataExpanded(false); setDeleteVedaDataConfirmation('');
      setDataDeletionResult(
        `Deleted ${result.deleted_projects} Veda project(s). Current-day quota safety counters remain through ${result.daily_quota_counters_preserved_until_utc_date} UTC; your sign-in account remains active.`,
      );
      try { await onVedaDataDeleted(); }
      catch { setError('Veda data was deleted, but the workspace could not refresh. Reload the page.'); }
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'Could not delete Veda data.'); }
    finally { setBusy(false); }
  };

  return <Modal title="Preferences and data" onClose={onClose}><div className="modal-form preferences-form">
    <p className="modal-intro">Choose defaults for new research runs. The server keeps these settings with your authenticated account.</p>
    {error && <p className="form-error" role="alert">{error}</p>}
    {!preferences ? <div className="loading-panel"><LoaderCircle className="spin" /><span>Loading account settings…</span></div> : <>
      <div className="form-grid composer-bottom"><label>Default research depth<select value={depth} onChange={(event) => setDepth(event.target.value as typeof depth)}><option value="quick">Quick</option><option value="standard">Standard</option><option value="deep">Deep</option></select></label><label>Default model budget <span className="optional">USD · 0 disables model spend</span><input type="number" min="0" max="2" step="0.05" value={budget} onChange={(event) => setBudget(event.target.value)} /></label><label>Delete archived projects after<select aria-label="Delete archived projects after" value={retentionDays ?? ''} onChange={(event) => setRetentionDays(event.target.value ? Number(event.target.value) as 30 | 90 | 365 : null)}><option value="">Keep until I delete them</option><option value="30">30 days</option><option value="90">90 days</option><option value="365">365 days</option></select><span className="optional">Applies when you next archive a project</span></label></div>
      <p className="preferences-state">{preferences.is_customized ? 'Your defaults are saved to your account.' : 'Using standard depth and a $0 model budget until you save custom defaults.'}</p>
      <div className="modal-actions preferences-actions"><button type="button" className="quiet-button" onClick={() => void reset()} disabled={busy}>Reset</button><span /><button type="button" className="primary-button" onClick={() => void save()} disabled={busy}>{busy ? 'Saving…' : 'Save defaults'}</button></div>
    </>}
    <section className="lifecycle-panel"><p className="eyebrow">YOUR DATA</p>{lifecycle ? <>
      <p><b>Reports:</b> export an individual report as {lifecycle.report_exports.formats.join(' or ').toUpperCase()}. Archived reports remain exportable.</p>
      <p><b>Projects:</b> archive hides and retains records. Archived projects can be restored or permanently deleted below.</p>
      <p><b>Account deletion:</b> {lifecycle.account_deletion.detail}</p>
      <p><b>Veda data deletion:</b> {lifecycle.veda_data_deletion.detail}</p>
      <p><b>Retention:</b> {lifecycle.retention.detail}</p>
      <p>{lifecycle.full_account_export.alternative}</p>
      <p>Identity-provider records and original HTML/PDF bytes are not stored or included.</p>
      <button type="button" className="quiet-button" onClick={() => void exportAccount()} disabled={busy || lifecycle.full_account_export.status !== 'available'}>{busy ? 'Preparing export…' : 'Download full account export'}</button>
      <button type="button" className="quiet-button danger-action" onClick={() => { setDeleteVedaDataExpanded(true); setDeleteVedaDataConfirmation(''); setDataDeletionResult(''); }} disabled={busy || lifecycle.veda_data_deletion.status !== 'available'}>Delete all Veda data</button>
      {deleteVedaDataExpanded && <div className="project-delete-confirm" role="group" aria-label="Veda data deletion confirmation"><p>Export a copy first if you need one. This cannot be undone. Your identity-provider sign-in account, operator-held backups, and today's quota safety counter will remain.</p><label>Confirmation phrase<input autoComplete="off" value={deleteVedaDataConfirmation} onChange={(event) => setDeleteVedaDataConfirmation(event.target.value)} aria-label="Type DELETE VEDA DATA to confirm" /></label><div className="archived-project-actions"><button type="button" className="quiet-button" onClick={() => { setDeleteVedaDataExpanded(false); setDeleteVedaDataConfirmation(''); }} disabled={busy}>Cancel</button><button type="button" className="quiet-button danger-action" onClick={() => void permanentlyDeleteVedaData()} disabled={busy || deleteVedaDataConfirmation !== lifecycle.veda_data_deletion.confirmation_phrase}>Permanently delete Veda data</button></div></div>}
      {dataDeletionResult && <p role="status">{dataDeletionResult}</p>}
    </> : <p>Loading data lifecycle details…</p>}</section>
    <section className="archived-projects"><p className="eyebrow">ARCHIVED PROJECTS</p>{archivedProjects.length ? archivedProjects.map((project) => <div className="archived-project-item" key={project.id}><div className="archived-project-row"><span>{project.title}{project.purge_at && <small className="project-purge-date">Scheduled for deletion {new Date(project.purge_at).toLocaleDateString()}</small>}</span><div className="archived-project-actions"><button className="quiet-button" onClick={() => void restore(project)} disabled={busy}>Restore</button><button className="quiet-button danger-action" onClick={() => { setDeleteProjectId(project.id); setDeleteTitle(''); }} aria-expanded={deleteProjectId === project.id} disabled={busy}>Delete permanently</button></div></div>{deleteProjectId === project.id && <div className="project-delete-confirm" role="group" aria-label={`Permanent deletion confirmation for ${project.title}`}><p>This permanently deletes the project's Veda records and cannot be undone. Type the exact project title to continue. Deletion is unavailable while a research step is still running.</p><label>Project title<input autoComplete="off" value={deleteTitle} onChange={(event) => setDeleteTitle(event.target.value)} aria-label={`Type ${project.title} to confirm deletion`} /></label><div className="archived-project-actions"><button type="button" className="quiet-button" onClick={() => { setDeleteProjectId(null); setDeleteTitle(''); }} disabled={busy}>Cancel</button><button type="button" className="quiet-button danger-action" onClick={() => void permanentlyDelete(project)} disabled={busy || deleteTitle.trim() !== project.title}>Permanently delete</button></div></div>}</div>) : <p>{lifecycle ? 'No archived projects.' : 'Loading…'}</p>}</section>
  </div></Modal>;
}

function AuthConfigurationError({ message }: { message: string }) {
  return (
    <div className="signin-page">
      <div className="signin-card">
        <div className="brand signin-brand"><div className="brand-mark"><span>V</span></div><div><b>veda</b><small>RESEARCH STUDIO</small></div></div>
        <p className="eyebrow">AUTHENTICATION UNAVAILABLE</p>
        <h1>Configuration required.</h1>
        <p role="alert" className="signin-error">{message}</p>
      </div>
    </div>
  );
}

function SignIn({ managed, error, onSignIn }: { managed: boolean; error: string; onSignIn: (email?: string) => Promise<void> }) {
  const [email, setEmail] = useState('');
  const [busy, setBusy] = useState(false);
  const [sent, setSent] = useState(false);
  const startSignIn = async () => {
    setBusy(true);
    try {
      await onSignIn(managed ? email : undefined);
      setSent(managed);
    } finally {
      setBusy(false);
    }
  };
  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    await startSignIn();
  };
  return (
    <div className="signin-page">
      <div className="signin-ambient ambient-one" /><div className="signin-ambient ambient-two" />
      <div className="signin-card">
        <div className="brand signin-brand"><div className="brand-mark"><span>V</span></div><div><b>veda</b><small>RESEARCH STUDIO</small></div></div>
        <p className="eyebrow">THINK CLEARLY. DECIDE WITH EVIDENCE.</p>
        <h1>Research that<br /><em>shows its work.</em></h1>
        <p className="signin-copy">A calmer way to investigate complex questions. Follow every finding back to the source and see what the evidence can — and can’t — say.</p>
        {managed ? (
          <form className="signin-form" onSubmit={submit}>
            <label htmlFor="email">Work email</label>
            <div className="email-control"><LockKeyhole size={17} /><input id="email" type="email" autoComplete="email" required value={email} onChange={(e) => setEmail(e.target.value)} placeholder="you@company.com" /><button type="submit" disabled={busy || sent}>{busy ? <LoaderCircle className="spin" size={17} /> : sent ? <Check size={17} /> : <ArrowRight size={17} />}</button></div>
            <p className="form-hint">{sent ? 'A secure sign-in link is on its way.' : 'We’ll email you a secure, one-time sign-in link.'}</p>
          </form>
        ) : (
          <div className="signin-form"><label>Local development</label><button className="primary-button signin-button" onClick={() => void startSignIn()} disabled={busy}>{busy ? <LoaderCircle className="spin" size={17} /> : <KeyRound size={17} />}<span>Continue to local workspace</span><ArrowRight size={16} /></button><p className="form-hint">Only available when the backend explicitly enables local development auth.</p></div>
        )}
        {error && <div className={error.startsWith('Check your inbox') ? 'signin-notice' : 'signin-error'}>{error}</div>}
        <div className="signin-footer"><span>Veda keeps citations close</span><span>·</span><span>Built for thoughtful decisions</span></div>
      </div>
      <div className="signin-art"><div className="art-orbit orbit-a" /><div className="art-orbit orbit-b" /><div className="art-orbit orbit-c" /><div className="art-core"><BookOpen size={28} strokeWidth={1.2} /></div><div className="art-node node-a"><Sparkles size={16} /></div><div className="art-node node-b"><FileText size={17} /></div><div className="art-node node-c"><ShieldCheck size={17} /></div><div className="art-label label-a">RESEARCH</div><div className="art-label label-b">EVIDENCE</div></div>
    </div>
  );
}

function Dashboard({ projects, loading, loadError, onCreate, onSelect, onRefresh, onError }: {
  projects: Project[]; loading: boolean; loadError: string; onCreate: (data: { title: string; description: string; domain: string }) => Promise<void>;
  onSelect: (project: Project) => void; onRefresh: () => void; onError: (error: unknown) => void;
}) {
  const [showCreate, setShowCreate] = useState(false);
  const [search, setSearch] = useState('');
  const filtered = useMemo(() => projects.filter((project) => `${project.title} ${project.description} ${project.domain}`.toLowerCase().includes(search.toLowerCase())), [projects, search]);
  useEffect(() => {
    const show = () => setShowCreate(true);
    window.addEventListener('veda:new-project', show);
    return () => window.removeEventListener('veda:new-project', show);
  }, []);
  const submit = async (data: { title: string; description: string; domain: string }) => {
    try { await onCreate(data); setShowCreate(false); } catch (error) { onError(error); }
  };
  return (
    <div className="dashboard-view">
      <div className="welcome-row"><div><p className="eyebrow">YOUR RESEARCH DESK</p><h1>Make room for <em>good questions.</em></h1><p className="welcome-copy">Build an evidence trail you can return to, challenge, and share with confidence.</p></div><div className="welcome-seal"><span>V</span><small>OPEN<br />QUESTIONS<br />WELCOME</small></div></div>
      <div className="stat-strip"><div><span className="stat-icon sage"><FolderKanban size={17} /></span><span><b>{projects.length}</b><small>RESEARCH PROJECTS</small></span></div><div><span className="stat-icon gold"><FlaskConical size={17} /></span><span><b>Evidence-led</b><small>RESEARCH APPROACH</small></span></div><div><span className="stat-icon blue"><ShieldCheck size={17} /></span><span><b>Source-linked</b><small>EVERY FINDING</small></span></div></div>
      <div className="section-heading"><div><p className="eyebrow">YOUR LIBRARY</p><h2>Research projects</h2></div><div className="section-actions"><div className="search-box"><Search size={16} /><input aria-label="Search projects" value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search projects" /></div><button className="icon-button" onClick={onRefresh} title="Refresh projects" aria-label="Refresh projects"><RefreshCw size={16} /></button><button className="primary-button" onClick={() => setShowCreate(true)}><Plus size={16} /> New project</button></div></div>
      {loadError && <div className="project-load-error" role="alert"><p>Could not refresh your project list: {loadError}</p><button className="quiet-button" onClick={onRefresh}>Retry project loading</button></div>}
      {loading ? <div className="loading-panel"><LoaderCircle className="spin" /><span>Opening your workspace…</span></div> : filtered.length ? <div className="project-grid">{filtered.map((project, index) => <ProjectCard key={project.id} project={project} index={index} onClick={() => onSelect(project)} />)}</div> : loadError ? <div className="not-ready">Project availability is unknown until the list can be refreshed.</div> : <EmptyProjects onCreate={() => setShowCreate(true)} searching={!!search} />}
      <div className="dashboard-footnote"><span><span className="tiny-spark">✳</span> Veda separates what a source reports from what we can conclude.</span><a href="https://crossref.org" target="_blank" rel="noreferrer">About scholarly discovery <ExternalLink size={13} /></a></div>
      {showCreate && <CreateProjectModal onClose={() => setShowCreate(false)} onSubmit={(data) => void submit(data)} />}
    </div>
  );
}

function ProjectCard({ project, index, onClick }: { project: Project; index: number; onClick: () => void }) {
  const colors = ['mint', 'sand', 'lavender', 'blue'];
  return <button className="project-card" onClick={onClick}><div className="card-topline"><span className={`project-type-icon ${colors[index % colors.length]}`}><BookOpen size={18} /></span><span className="card-open"><ArrowRight size={16} /></span></div><span className="card-domain">{project.domain}</span><h3>{project.title}</h3><p>{project.description || 'A space for focused research and evidence you can inspect.'}</p><div className="card-bottom"><span><Activity size={14} /> Ready to research</span><span>{new Date(project.updated_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })}</span></div></button>;
}

function EmptyProjects({ onCreate, searching }: { onCreate: () => void; searching: boolean }) {
  return <div className="empty-state" role={searching ? 'status' : undefined} aria-live={searching ? 'polite' : undefined}><div className="empty-illustration"><span className="empty-page"><FileText size={27} /></span><span className="empty-plus"><Plus size={18} /></span></div><h3>{searching ? 'No matching projects' : 'Start with the question that matters.'}</h3><p>{searching ? 'Try a different title, topic, or domain.' : 'Create a project to gather sources, track evidence, and build a research trail over time.'}</p>{!searching && <button className="primary-button" onClick={onCreate}><Plus size={16} /> Create your first project</button>}</div>;
}

function CreateProjectModal({ onClose, onSubmit }: { onClose: () => void; onSubmit: (data: { title: string; description: string; domain: string }) => void }) {
  const [title, setTitle] = useState(''); const [description, setDescription] = useState(''); const [domain, setDomain] = useState('AI adoption economics');
  return <Modal title="Create a research project" onClose={onClose}><form className="modal-form" onSubmit={(e) => { e.preventDefault(); onSubmit({ title: title.trim(), description: description.trim(), domain: domain.trim() }); }}><p className="modal-intro">Give your research a home. You can refine the scope as you learn.</p><label>Project name<input required maxLength={160} value={title} onChange={(e) => setTitle(e.target.value)} placeholder="e.g. AI adoption in Indian SMEs" /></label><label>Research domain<input maxLength={120} value={domain} onChange={(e) => setDomain(e.target.value)} /></label><label>Persistent project brief<textarea maxLength={4000} rows={3} value={description} onChange={(e) => setDescription(e.target.value)} placeholder="What decision, population, or assumptions should carry across research runs?" /></label><p className="drawer-footnote">Saved with this project and prefilled into each run's editable decision context. This is user-authored context, not source evidence.</p><div className="modal-actions"><button type="button" className="quiet-button" onClick={onClose}>Cancel</button><button className="primary-button" type="submit"><Plus size={16} /> Create project</button></div></form></Modal>;
}

function EditProjectModal({ project, onClose, onSubmit }: { project: Project; onClose: () => void; onSubmit: (data: { title: string; description: string; domain: string }) => void }) {
  const [title, setTitle] = useState(project.title);
  const [description, setDescription] = useState(project.description);
  const [domain, setDomain] = useState(project.domain);
  return <Modal title="Edit research project" onClose={onClose}><form className="modal-form" onSubmit={(event) => { event.preventDefault(); onSubmit({ title: title.trim(), description: description.trim(), domain: domain.trim() }); }}><label>Project name<input required maxLength={160} value={title} onChange={(event) => setTitle(event.target.value)} /></label><label>Research domain<input required maxLength={120} value={domain} onChange={(event) => setDomain(event.target.value)} /></label><label>Persistent project brief<textarea maxLength={4000} rows={4} value={description} onChange={(event) => setDescription(event.target.value)} /></label><p className="drawer-footnote">Changes apply to future research runs. Each run keeps its own saved decision-context snapshot.</p><div className="modal-actions"><button type="button" className="quiet-button" onClick={onClose}>Cancel</button><button className="primary-button" type="submit"><Check size={16} /> Save changes</button></div></form></Modal>;
}

function ProjectWorkspace({ project, onBack, onUpdate, onStartJob, onArchive, onError }: { project: Project; onBack: () => void; onUpdate: (data: { title: string; description: string; domain: string }) => Promise<void>; onStartJob: (job: ResearchJob) => void; onArchive: () => void; onError: (error: unknown) => void }) {
  const [jobs, setJobs] = useState<ResearchJob[]>([]);
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [loading, setLoading] = useState(true);
  const [historyRevision, setHistoryRevision] = useState(0);
  const [historyErrors, setHistoryErrors] = useState<{ jobs: string; conversations: string }>({ jobs: '', conversations: '' });
  const [showComposer, setShowComposer] = useState(false);
  const [showEdit, setShowEdit] = useState(false);
  useEffect(() => {
    let active = true;
    setHistoryErrors({ jobs: '', conversations: '' });
    Promise.allSettled([apiClient.listJobs(project.id), apiClient.listConversations(project.id)]).then(([jobsResult, conversationsResult]) => {
      if (!active) return;
      if (jobsResult.status === 'fulfilled') { setJobs(jobsResult.value); setHistoryErrors((current) => ({ ...current, jobs: '' })); }
      else setHistoryErrors((current) => ({ ...current, jobs: jobsResult.reason instanceof Error ? jobsResult.reason.message : 'Research run history is unavailable.' }));
      if (conversationsResult.status === 'fulfilled') { setConversations(conversationsResult.value); setHistoryErrors((current) => ({ ...current, conversations: '' })); }
      else setHistoryErrors((current) => ({ ...current, conversations: conversationsResult.reason instanceof Error ? conversationsResult.reason.message : 'Conversation history is unavailable.' }));
    }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [project.id, historyRevision]);
  const retryHistory = () => { setLoading(true); setHistoryRevision((revision) => revision + 1); };
  const submit = async (input: Record<string, unknown>) => {
    const job = await apiClient.createJob(project.id, input);
    setJobs((current) => [job, ...current.filter((item) => item.id !== job.id)]);
    setConversations(await apiClient.listConversations(project.id));
    onStartJob(job);
  };
  const openConversation = async (conversation: Conversation) => {
    try {
      const page = await apiClient.getMessages(conversation.id);
      const relatedJobId = [...page.items].reverse().find((message) => message.related_job_id)?.related_job_id;
      if (!relatedJobId) throw new Error('This conversation does not have a research run yet.');
      onStartJob(await apiClient.getJob(relatedJobId));
    } catch (error) { onError(error); }
  };
  return <div className="project-view"><button className="back-link" onClick={onBack}><ArrowLeft size={15} /> Workspace</button><div className="project-hero"><div className="project-hero-mark"><BookOpen size={24} /></div><div className="project-hero-main"><p className="eyebrow">{project.domain}</p><h1>{project.title}</h1><p>{project.description || 'A focused workspace for evidence, questions and decision context.'}</p></div><div className="project-hero-actions"><button className="icon-button" onClick={() => setShowEdit(true)} title="Edit project" aria-label="Edit project"><Pencil size={16} /></button><button className="icon-button" onClick={onArchive} title="Archive project" aria-label="Archive project"><Archive size={17} /></button></div></div>
    <div className="project-action-band"><div><span className="band-icon"><Sparkles size={16} /></span><span><b>What would you like to understand?</b><small>Start a research run with a clear scope and a visible evidence trail.</small></span></div><button className="primary-button" onClick={() => setShowComposer(true)}><Plus size={16} /> Start research</button></div>
    {(historyErrors.jobs || historyErrors.conversations) && <section className="history-recovery" role="alert"><div><b>Some project history could not be loaded.</b>{historyErrors.conversations && <p>Conversations: {historyErrors.conversations}</p>}{historyErrors.jobs && <p>Research runs: {historyErrors.jobs}</p>}</div><button className="quiet-button" onClick={retryHistory} disabled={loading}>{loading ? <><LoaderCircle size={14} className="spin" /> Retrying…</> : <><RefreshCw size={14} /> Retry project history</>}</button></section>}
    {loading ? <div className="loading-panel"><LoaderCircle className="spin" /><span>Loading project history…</span></div> : <>
      {conversations.length > 0 && <section className="project-conversations"><div className="section-heading compact"><div><p className="eyebrow">PERSISTENT CONTEXT</p><h2>Conversations</h2></div><span className="subtle-count">{conversations.length}</span></div><div className="conversation-list">{conversations.map((conversation) => <button className="conversation-row" key={conversation.id} onClick={() => void openConversation(conversation)}><MessageSquareText size={17} /><span><b>{conversation.title}</b><small>Conversation · {new Date(conversation.created_at).toLocaleDateString()}</small></span><ArrowRight size={16} /></button>)}</div></section>}
      <div className="section-heading compact"><div><p className="eyebrow">PROJECT HISTORY</p><h2>Research runs</h2></div><span className="subtle-count">{jobs.length} {jobs.length === 1 ? 'run' : 'runs'}</span></div>
      {jobs.length ? <div className="job-list">{jobs.map((job) => <button className="job-row" key={job.id} onClick={() => onStartJob(job)}><div className={`job-status-icon ${job.status}`}><Activity size={17} /></div><div className="job-row-copy"><span className="job-question">{job.question}</span><span className="job-meta">{prettyStatus(job.status)} · {new Date(job.created_at).toLocaleString(undefined, { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' })}</span></div><span className={`status-pill ${job.status}`}>{prettyStatus(job.status)}</span><ArrowRight size={16} className="job-chevron" /></button>)}</div> : historyErrors.jobs ? null : <div className="history-empty"><div className="history-line" /><span>Research runs you start here will stay attached to this project.</span></div>}
    </>}
    {showComposer && <ResearchComposer initialContext={project.description} onClose={() => setShowComposer(false)} onSubmit={(data) => void submit(data).catch(onError)} />}{showEdit && <EditProjectModal project={project} onClose={() => setShowEdit(false)} onSubmit={(data) => void onUpdate(data).then(() => setShowEdit(false)).catch(onError)} />}</div>;
}

function ResearchComposer({ onClose, onSubmit, parentJobId, conversationId, initialQuestion, initialContext }: { onClose: () => void; onSubmit: (data: Record<string, unknown>) => void; parentJobId?: string; conversationId?: string | null; initialQuestion?: string; initialContext?: string }) {
  const [question, setQuestion] = useState(initialQuestion || ''); const [context, setContext] = useState(initialContext || ''); const [geography, setGeography] = useState(''); const [population, setPopulation] = useState(''); const [timeHorizon, setTimeHorizon] = useState(''); const [objective, setObjective] = useState(''); const [comparator, setComparator] = useState(''); const [targetOutcome, setTargetOutcome] = useState(''); const [denominator, setDenominator] = useState(''); const [assumptions, setAssumptions] = useState(''); const [depth, setDepth] = useState<'quick' | 'standard' | 'deep'>('standard'); const [budget, setBudget] = useState('0'); const [busy, setBusy] = useState(false);
  const [providerStatus, setProviderStatus] = useState<{ active_provider: string; provider_ready: boolean; model: string | null; paid_calls_allowed: boolean } | null>(null);
  const [depthProfiles, setDepthProfiles] = useState<Record<DepthProfile['name'], DepthProfile> | null>(null);
  const [preferencesReady, setPreferencesReady] = useState(false);
  useEffect(() => { api<{ active_provider: string; provider_ready: boolean; model: string | null; paid_calls_allowed: boolean }>('/settings/providers').then(setProviderStatus).catch(() => setProviderStatus(null)); }, []);
  useEffect(() => { apiClient.getDepthProfiles().then(setDepthProfiles).catch(() => setDepthProfiles(null)); }, []);
  useEffect(() => { apiClient.getUserPreferences().then((preferences) => { setDepth(preferences.default_depth); setBudget(String(preferences.default_budget_ceiling_usd)); }).catch(() => undefined).finally(() => setPreferencesReady(true)); }, []);
  const depthOption = (key: DepthProfile['name'], fallback: string) => {
    const profile = depthProfiles?.[key];
    return profile
      ? `${key[0].toUpperCase()}${key.slice(1)} · ${profile.max_queries} queries, ${profile.max_sources} sources, ${profile.max_passages} passages, ${profile.max_pdf_documents} PDFs, ${profile.max_model_calls} model calls, ${profile.max_prompt_tokens_per_call.toLocaleString()} estimated input / ${profile.max_output_tokens_per_call.toLocaleString()} output tokens per call, ${profile.max_step_seconds}s per step`
      : `${key[0].toUpperCase()}${key.slice(1)} · ${fallback}`;
  };
  const modelDisclosure = !providerStatus
    ? 'Provider status could not be loaded. Veda cannot confirm whether model processing is disabled; check provider settings before submitting sensitive material.'
    : providerStatus.active_provider === 'disabled'
      ? 'No model provider is enabled. Veda will save a source evidence map without model appraisal or synthesis.'
      : !providerStatus.provider_ready
        ? 'The selected provider is not ready. Missing credentials or settings mean this server will not send a model request.'
        : providerStatus.active_provider === 'openrouter'
          ? `The server may send your question, supplied scope, and retrieved excerpts to ${providerStatus.model || 'OpenRouter free'} for model-assisted planning or analysis. Only free model routes are accepted; free-provider data handling may vary.`
        : providerStatus.active_provider === 'sarvam' && providerStatus.paid_calls_allowed
          ? `The server may send your question, supplied scope, and retrieved excerpts to ${providerStatus.model || 'Sarvam AI'} for model-assisted research. INR budget reservations apply; billing is shared at the Sarvam organization level.`
          : providerStatus.paid_calls_allowed
            ? `The server may send your question, supplied scope, and retrieved excerpts to ${providerStatus.model || 'OpenAI'} for model-assisted planning or analysis; the job budget and configured price estimate apply.`
            : 'OpenAI is configured but paid calls are disabled. No request will be sent until the server is explicitly enabled.';
  const submit = async (event: React.FormEvent) => { event.preventDefault(); setBusy(true); onSubmit({ question: question.trim(), context, geography: geography || null, population: population || null, time_horizon: timeHorizon || null, decision_objective: objective || null, comparator: comparator || null, target_outcome: targetOutcome || null, denominator: denominator || null, assumptions_to_test: assumptions || null, depth, budget_ceiling_usd: Number(budget), idempotency_key: crypto.randomUUID(), ...(parentJobId ? { parent_job_id: parentJobId } : {}), ...(conversationId ? { conversation_id: conversationId } : {}) }); };
  return <Modal title={parentJobId ? 'Continue this research' : 'Shape your research question'} wide onClose={onClose}><form className="modal-form composer-form" onSubmit={submit}><p className="modal-intro">{parentJobId ? 'This run will stay linked to its parent and conversation. Prior claims help frame the search; the new report must cite evidence retrieved for this run.' : 'A little context helps Veda search the right evidence. You can leave fields open when the question is exploratory.'}</p>{initialContext?.trim() && <p className="drawer-footnote">The saved project brief is prefilled below. You can edit it for this run; these edits do not change the persistent project brief.</p>}<label>Research question<textarea required minLength={10} maxLength={2000} rows={3} value={question} onChange={(e) => setQuestion(e.target.value)} placeholder="e.g. What evidence shows that AI tools improve end-to-end productivity for experienced software developers?" /></label><label>Decision context <span className="optional">{initialContext?.trim() ? 'SAVED PROJECT BRIEF · EDIT FOR THIS RUN' : 'OPTIONAL'}</span><textarea maxLength={4000} rows={2} value={context} onChange={(e) => setContext(e.target.value)} placeholder="What decision will this research inform? What context should be considered?" /></label><div className="form-grid"><label>Geography<input maxLength={160} value={geography} onChange={(e) => setGeography(e.target.value)} placeholder="e.g. India" /></label><label>Population or industry<input maxLength={300} value={population} onChange={(e) => setPopulation(e.target.value)} placeholder="e.g. small businesses" /></label><label>Time horizon<input maxLength={160} value={timeHorizon} onChange={(e) => setTimeHorizon(e.target.value)} placeholder="e.g. 2022–2026" /></label><label>Decision objective<input maxLength={500} value={objective} onChange={(e) => setObjective(e.target.value)} placeholder="e.g. adoption investment" /></label></div><div className="form-grid planning-input-grid"><label>Comparator or counterfactual <span className="optional">OPTIONAL</span><input maxLength={300} value={comparator} onChange={(e) => setComparator(e.target.value)} placeholder="e.g. teams not using the tool" /></label><label>Target outcome <span className="optional">OPTIONAL</span><input maxLength={300} value={targetOutcome} onChange={(e) => setTargetOutcome(e.target.value)} placeholder="e.g. completed tasks per worker-hour" /></label><label>Outcome denominator <span className="optional">OPTIONAL</span><input maxLength={200} value={denominator} onChange={(e) => setDenominator(e.target.value)} placeholder="e.g. per worker-hour observed over 12 weeks" /></label><label>Assumptions to test <span className="optional">OPTIONAL</span><textarea maxLength={1000} rows={2} value={assumptions} onChange={(e) => setAssumptions(e.target.value)} placeholder="Only the assumptions you want Veda to examine; Veda will not infer these for you." /></label></div><div className="form-grid composer-bottom"><label>Research depth<select value={depth} onChange={(e) => setDepth(e.target.value as typeof depth)}><option value="quick">{depthOption('quick', 'bounded research')}</option><option value="standard">{depthOption('standard', 'balanced research')}</option><option value="deep">{depthOption('deep', 'expanded research')}</option></select></label><label>Maximum model spend <span className="optional">USD · 0 = no model spend</span><input type="number" min="0" max="2" step="0.05" value={budget} onChange={(e) => setBudget(e.target.value)} /></label></div><div className="budget-note"><ShieldCheck size={15} /><div className="budget-note-copy"><p><strong>External search.</strong> Your research question and planned queries (which may include saved decision context and other supplied scope fields) are sent to Crossref and OpenAlex. One bounded publication-metadata query is also sent to OpenAIRE Graph. When multilateral sources are planned, Veda makes one bounded metadata-only search of the official World Bank Documents &amp; Reports API only when the server explicitly confirms non-commercial API use; otherwise the source class is reported as not searched. This does not fetch document files or establish reuse rights. If you explicitly scope a government question to the United Kingdom, Veda may make one metadata-only policy-paper query to the unsupported best-effort GOV.UK Search API; linked publication contents are not fetched. For questions that clearly request World Bank indicator data and when you supply a supported geography, Veda may also send your research question and geography to World Bank Data360. Employment questions with an explicitly supplied World geography may also be sent to ILOSTAT. Retrieved provider records and permitted excerpts are stored in this project. Full-text fetching follows the displayed host and rights checks.</p><p><strong>Model processing.</strong> {modelDisclosure}</p><p>Depth-profile limits are fixed by the server and included in the resulting report.</p></div></div><div className="modal-actions"><button type="button" className="quiet-button" onClick={onClose}>Cancel</button><button className="primary-button" type="submit" disabled={!preferencesReady || busy || question.trim().length < 10}>{busy ? <LoaderCircle className="spin" size={16} /> : <Sparkles size={16} />} {preferencesReady ? (parentJobId ? 'Start follow-up' : 'Start research') : 'Loading defaults…'}</button></div></form></Modal>;
}

function JobWorkspace({ project, jobId, onBack, onStartJob, onError }: { project: Project; jobId: string; onBack: () => void; onStartJob: (job: ResearchJob) => void; onError: (error: unknown) => void }) {
  const [job, setJob] = useState<ResearchJob | null>(null); const [events, setEvents] = useState<JobEvent[]>([]); const [sources, setSources] = useState<Source[]>([]); const [candidates, setCandidates] = useState<DiscoveryCandidate[]>([]); const [claims, setClaims] = useState<Claim[]>([]); const [relationships, setRelationships] = useState<EvidenceRelationship[]>([]); const [hypotheses, setHypotheses] = useState<CompetingHypothesis[]>([]); const [relationshipStatus, setRelationshipStatus] = useState('not_assessed'); const [hypothesisStatus, setHypothesisStatus] = useState('not_assessed'); const [report, setReport] = useState<ResearchReport | null>(null); const [plan, setPlan] = useState<ResearchPlan | null>(null);
  const [messages, setMessages] = useState<ConversationMessage[]>([]); const [messageOffset, setMessageOffset] = useState(0); const [messagesHaveMore, setMessagesHaveMore] = useState(false); const [loadingOlderMessages, setLoadingOlderMessages] = useState(false); const [followUpContext, setFollowUpContext] = useState<FollowUpContext | null>(null); const [historyError, setHistoryError] = useState(''); const [showFollowUp, setShowFollowUp] = useState(false);
  const [loading, setLoading] = useState(true); const [busy, setBusy] = useState(false); const [running, setRunning] = useState(false); const [tab, setTab] = useState<'overview' | 'conversation' | 'sources' | 'evidence' | 'comparisons' | 'report'>('overview'); const [selectedSource, setSelectedSource] = useState<Source | null>(null); const [selectedClaim, setSelectedClaim] = useState<Claim | null>(null); const [error, setError] = useState('');
  const [retryNow, setRetryNow] = useState(Date.now());
  const shouldContinueRef = useRef(false);

  const refresh = useCallback(async () => {
    const nextJob = await apiClient.getJob(jobId);
    setJob(nextJob);
    const [nextEvents, nextSources, nextCandidates, nextClaims, nextRelationships, nextHypotheses] = await Promise.all([
      apiClient.getEvents(jobId), apiClient.getSources(jobId), apiClient.getCandidates(jobId), apiClient.getClaims(jobId),
      apiClient.getRelationships(jobId), apiClient.getHypotheses(jobId),
    ]);
    setEvents(nextEvents); setSources(nextSources); setCandidates(nextCandidates); setClaims(nextClaims);
    setRelationships(nextRelationships.items); setHypotheses(nextHypotheses.items);
    setRelationshipStatus(nextRelationships.status); setHypothesisStatus(nextHypotheses.status);
    if (nextJob.conversation_id) {
      try { const page = await apiClient.getMessages(nextJob.conversation_id); setMessages(page.items); setMessageOffset(page.items.length); setMessagesHaveMore(page.has_more); setHistoryError(''); }
      catch (historyLoadError) { setHistoryError(historyLoadError instanceof Error ? historyLoadError.message : 'Could not load conversation history.'); }
    } else { setMessages([]); setMessageOffset(0); setMessagesHaveMore(false); }
    if (nextJob.parent_job_id) {
      try { setFollowUpContext(await apiClient.getFollowUpContext(jobId)); }
      catch { setFollowUpContext(null); }
    } else { setFollowUpContext(null); }
    try { setPlan(await apiClient.getPlan(jobId)); } catch { setPlan(null); }
    if (['completed', 'completed_with_limitations'].includes(nextJob.status)) {
      try { setReport(await apiClient.getReport(jobId)); } catch { setReport(null); }
    }
    setLoading(false);
    return nextJob;
  }, [jobId]);

  useEffect(() => { let active = true; void refresh().catch((err) => { if (active) { setError(err instanceof Error ? err.message : 'Could not load this research run.'); setLoading(false); } }); return () => { active = false; }; }, [refresh]);
  useEffect(() => { if (!running) return; const timer = window.setInterval(() => { void refresh().catch(onError); }, 2500); return () => window.clearInterval(timer); }, [running, refresh, onError]);
  useEffect(() => {
    const hasPendingRetry = sources.some((source) => Object.values(source.retrieval?.deferred_retries || {}).some((retry) => retry?.status === 'pending'));
    if (!hasPendingRetry) return;
    const timer = window.setInterval(() => setRetryNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [sources]);

  const selectSource = async (source: Source) => {
    try { setSelectedSource(await apiClient.getSource(source.id)); }
    catch (error) { setSelectedSource(source); onError(error); }
  };

  const startFollowUp = async (data: Record<string, unknown>) => {
    const child = await apiClient.createJob(project.id, data);
    setShowFollowUp(false);
    onStartJob(child);
  };
  const continueDeferredRetrieval = async () => {
    setBusy(true); setError('');
    try {
      const continuation = await apiClient.retryDeferredRetrieval(jobId);
      onStartJob(continuation.job);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not queue the deferred retrieval continuation.');
      onError(err);
    } finally { setBusy(false); }
  };
  const openRelatedJob = async (relatedJobId: string) => {
    try { onStartJob(await apiClient.getJob(relatedJobId)); }
    catch (error) { onError(error); }
  };
  const loadOlderMessages = async () => {
    if (!job?.conversation_id || loadingOlderMessages) return;
    setLoadingOlderMessages(true);
    try {
      const page = await apiClient.getMessages(job.conversation_id, messageOffset);
      setMessages((current) => [...page.items, ...current]);
      setMessageOffset((current) => current + page.items.length);
      setMessagesHaveMore(page.has_more);
    } catch (historyLoadError) { setHistoryError(historyLoadError instanceof Error ? historyLoadError.message : 'Could not load older messages.'); }
    finally { setLoadingOlderMessages(false); }
  };

  const step = async () => {
    setBusy(true); setError('');
    try {
      let current = job;
      if (current?.status === 'retryable_failure' || current?.status === 'paused') current = await apiClient.resumeJob(jobId);
      if (!current || terminal(current)) { current = await refresh(); }
      if (!terminal(current)) {
        const next = await apiClient.advanceJob(jobId, crypto.randomUUID());
        setJob(next);
        await refresh();
        if (next.status === 'retryable_failure' || next.status === 'terminal_failure') setRunning(false);
        if (terminal(next)) setRunning(false);
      }
    } catch (err) { setError(err instanceof Error ? err.message : 'Could not advance the research job.'); setRunning(false); onError(err); }
    finally { setBusy(false); }
  };

  const runAll = async () => {
    shouldContinueRef.current = true;
    setRunning(true);
    let count = 0;
    while (count < 12 && shouldContinueRef.current) {
      count += 1;
      setBusy(true); setError('');
      try {
        let current = await apiClient.getJob(jobId);
        if (current.status === 'retryable_failure' || current.status === 'paused') current = await apiClient.resumeJob(jobId);
        if (terminal(current)) { setJob(current); setRunning(false); await refresh(); return; }
        const next = await apiClient.advanceJob(jobId, crypto.randomUUID());
        setJob(next);
        await refresh();
        if (terminal(next) || next.status === 'terminal_failure') { setRunning(false); return; }
        if (!shouldContinueRef.current) {
          const paused = await apiClient.pauseJob(jobId);
          setJob(paused);
          await refresh();
          setRunning(false);
          return;
        }
      } catch (err) { setError(err instanceof Error ? err.message : 'Research paused after an error.'); setRunning(false); onError(err); return; }
      finally { setBusy(false); }
      await new Promise((resolve) => window.setTimeout(resolve, 650));
    }
    setRunning(false);
  };

  const pauseRun = async () => {
    shouldContinueRef.current = false;
    setRunning(false);
    if (!busy) {
      try { setJob(await apiClient.pauseJob(jobId)); await refresh(); }
      catch (err) { onError(err); }
    }
  };
  const continueDisabled = busy || !job || terminal(job);
  const pendingDeferredCount = sources.reduce((count, source) => count + Object.values(source.retrieval?.deferred_retries || {}).filter((retry) => retry?.status === 'pending').length, 0);
  const dueDeferredCount = sources.reduce((count, source) => count + Object.values(source.retrieval?.deferred_retries || {}).filter((retry) => retry?.status === 'pending' && !!retry.due_at && Date.parse(retry.due_at) <= retryNow).length, 0);
  if (loading) return <div className="loading-panel full-page"><LoaderCircle className="spin" /><span>Restoring your research checkpoint…</span></div>;
  if (error && !job) return <div className="error-panel"><p>{error}</p><button className="quiet-button" onClick={onBack}>Return to project</button></div>;
  if (!job) return null;

  return <div className="job-view"><button className="back-link" onClick={onBack}><ArrowLeft size={15} /> {project.title}</button><div className="job-hero"><div className="eyebrow-row"><p className="eyebrow">RESEARCH RUN · {project.domain}</p><span className={`status-pill ${job.status}`}>{prettyStatus(job.status)}</span></div><h1>{job.question}</h1><div className="job-scope-chips">{job.scope.geography && <span>{job.scope.geography}</span>}{job.scope.population && <span>{job.scope.population}</span>}<span>{job.depth} depth</span>{job.budget_ceiling_usd > 0 && <span>Model budget ${job.budget_ceiling_usd.toFixed(2)}</span>}{job.cost_spent_estimate_usd > 0 && <span>Estimated model cost ${job.cost_spent_estimate_usd.toFixed(4)}</span>}{job.cost_reserved_usd > 0 && <span>Reserved ${job.cost_reserved_usd.toFixed(4)}</span>}{job.budget_ceiling_inr > 0 && <span>Model budget ₹{job.budget_ceiling_inr.toFixed(2)}</span>}{job.cost_spent_estimate_inr > 0 && <span>Estimated model cost ₹{job.cost_spent_estimate_inr.toFixed(4)}</span>}{job.cost_reserved_inr > 0 && <span>Reserved ₹{job.cost_reserved_inr.toFixed(4)}</span>}{job.cost_estimate_complete === false && <span>{job.unknown_cost_calls ?? 'Some'} calls without reported cost</span>}</div><p className="depth-profile-summary">Limits: {job.resource_limits.max_queries} searches · {job.resource_limits.max_sources} sources · {job.resource_limits.max_passages} passages · {job.resource_limits.max_pdf_documents} PDF documents · {job.model_calls_reserved}/{job.resource_limits.max_model_calls} model calls · {job.resource_limits.max_retries} retries · {job.resource_limits.max_step_seconds}s per step. Input cap is {job.resource_limits.max_prompt_tokens_per_call.toLocaleString()} estimated tokens/call ({job.resource_limits.max_prompt_characters_per_call.toLocaleString()} characters max); output cap is {job.resource_limits.max_output_tokens_per_call.toLocaleString()} tokens/call. Reserved input envelope {job.prompt_token_budget_reserved.toLocaleString()} tokens.</p></div>
    <div className="run-toolbar"><div className="run-stage"><div className={`stage-pulse ${job.status}`}><span /></div><div><b>{stageLabel(job.current_stage)}</b><small>{job.status === 'active' ? 'The latest update reflects a completed server step.' : job.status === 'completed_with_limitations' ? 'A report is saved with its verification limits.' : job.error_message || (terminal(job) ? 'This run is no longer advancing.' : 'Each action saves a durable checkpoint.')}</small></div></div><div className="run-actions">{pendingDeferredCount > 0 && <button className="quiet-button" disabled={busy || running || dueDeferredCount === 0} onClick={() => void continueDeferredRetrieval()}>{dueDeferredCount > 0 ? `Continue deferred retrieval (${dueDeferredCount})` : 'Waiting for host interval'}</button>}<button className="quiet-button" disabled={!job.conversation_id} onClick={() => setShowFollowUp(true)}><MessageSquareText size={15} /> Follow up</button>{(job.status === 'retryable_failure' || job.status === 'paused') && <button className="quiet-button" onClick={() => void apiClient.resumeJob(jobId).then(refresh).catch(onError)}>Resume</button>}{running ? <button className="quiet-button stop-button" onClick={() => void pauseRun()}><Pause size={15} /> Pause</button> : <button className="quiet-button" disabled={continueDisabled} onClick={() => void step()}>{busy ? <LoaderCircle className="spin" size={15} /> : <ArrowRight size={15} />} Next step</button>}<button className="primary-button" disabled={continueDisabled || running} onClick={() => void runAll()}>{busy || running ? <LoaderCircle className="spin" size={15} /> : <Sparkles size={15} />} Run while open</button></div></div>
    {error && <div className="inline-error">{error}<button onClick={() => setError('')} aria-label="Dismiss"><X size={14} /></button></div>}
    <StageTimeline job={job} events={events} />
    <div className="workspace-tabs" role="tablist">{(['overview', 'conversation', 'sources', 'evidence', 'comparisons', 'report'] as const).map((name) => <button key={name} role="tab" aria-selected={tab === name} className={tab === name ? 'active' : ''} onClick={() => setTab(name)}>{name === 'overview' ? <Activity size={15} /> : name === 'conversation' ? <MessageSquareText size={15} /> : name === 'sources' ? <BookOpen size={15} /> : name === 'evidence' ? <Clipboard size={15} /> : name === 'comparisons' ? <Layers3 size={15} /> : <FileText size={15} />}<span>{name === 'comparisons' ? 'compare' : name}</span><small>{name === 'sources' ? sources.length : name === 'evidence' ? claims.length : name === 'comparisons' ? relationships.length + hypotheses.length : name === 'conversation' ? messages.length : ''}</small></button>)}</div>
    {tab === 'overview' && <OverviewPanel plan={plan} events={events} sources={sources} onViewSources={() => setTab('sources')} />}
    {tab === 'conversation' && <ConversationPanel job={job} messages={messages} followUpContext={followUpContext} historyError={historyError} hasOlderMessages={messagesHaveMore} loadingOlderMessages={loadingOlderMessages} onLoadOlder={() => void loadOlderMessages()} onOpenJob={openRelatedJob} onSelectClaim={setSelectedClaim} />}
    {tab === 'sources' && <SourcesPanel sources={sources} candidates={candidates} onSelect={selectSource} />}
    {tab === 'evidence' && <EvidencePanel claims={claims} sources={sources} onSelect={setSelectedClaim} />}
    {tab === 'comparisons' && <ComparisonPanel relationships={relationships} hypotheses={hypotheses} relationshipStatus={relationshipStatus} hypothesisStatus={hypothesisStatus} claims={claims} sources={sources} onSelectClaim={setSelectedClaim} />}
    {tab === 'report' && <ReportPanel report={report} job={job} sources={sources} claims={claims} onSelectClaim={setSelectedClaim} onSelectSource={selectSource} onError={onError} />}
    {selectedSource && <SourceDrawer source={selectedSource} onClose={() => setSelectedSource(null)} />}
    {selectedClaim && <EvidenceDrawer claim={selectedClaim} onClose={() => setSelectedClaim(null)} />}
    {showFollowUp && <ResearchComposer parentJobId={job.id} conversationId={job.conversation_id} initialQuestion={`What new evidence changes or qualifies this research? ${job.question}`} initialContext={project.description} onClose={() => setShowFollowUp(false)} onSubmit={(data) => void startFollowUp(data).catch(onError)} />}
  </div>;
}

function ConversationPanel({ job, messages, followUpContext, historyError, hasOlderMessages, loadingOlderMessages, onLoadOlder, onOpenJob, onSelectClaim }: { job: ResearchJob; messages: ConversationMessage[]; followUpContext: FollowUpContext | null; historyError: string; hasOlderMessages: boolean; loadingOlderMessages: boolean; onLoadOlder: () => void; onOpenJob: (jobId: string) => void; onSelectClaim: (claim: Claim) => void }) {
  return <div className="conversation-panel">
    <section className="content-card conversation-history"><div className="panel-heading"><div><p className="eyebrow">PROJECT CONVERSATION</p><h2>Research history</h2><p>Questions and saved report updates stay attached to this project conversation.</p></div><span className="evidence-count"><MessageSquareText size={15} /> {messages.length} messages</span></div>
      {historyError && <div className="inline-error">{historyError}</div>}{messages.length ? <div className="message-list">{hasOlderMessages && <button className="quiet-button older-messages" disabled={loadingOlderMessages} onClick={onLoadOlder}>{loadingOlderMessages ? <LoaderCircle size={14} className="spin" /> : <ArrowLeft size={14} />} Load older messages</button>}{messages.map((message) => <article className={`conversation-message ${message.role}`} key={message.id}><div className="message-meta"><b>{message.role === 'user' ? 'Research question' : 'Veda update'}</b><time dateTime={message.created_at}>{new Date(message.created_at).toLocaleString(undefined, { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' })}</time></div><p>{message.content}</p>{message.related_job_id && message.related_job_id !== job.id && <button className="text-button" onClick={() => onOpenJob(message.related_job_id!)}>Open linked run <ArrowRight size={14} /></button>}</article>)}</div> : !historyError && <div className="not-ready">No messages are stored for this conversation yet.</div>}
    </section>
    {job.parent_job_id && <section className="content-card follow-up-context-card"><div className="panel-heading"><div><p className="eyebrow">{followUpContext?.status === 'retrieval_continuation' ? 'RETRIEVAL CONTINUATION' : 'FOLLOW-UP PROVENANCE'}</p><h2>{followUpContext?.status === 'retrieval_continuation' ? 'Evidence carried into this continuation' : 'What informed this follow-up'}</h2><p>{followUpContext?.status === 'retrieval_continuation' ? 'Previously saved source metadata and evidence snapshots were copied with lineage identifiers. Only the listed due, deferred URLs are retried; the earlier report remains available as its own run.' : 'Parent material is shown with its original source and passage locator. It frames the new search and is not automatically carried into this run’s citations.'}</p></div><span className="access-badge neutral">{prettyStatus(followUpContext?.status || 'loading')}</span></div>
      {followUpContext?.parent && <div className="parent-question"><small>PARENT QUESTION</small><b>{followUpContext.parent.question}</b><button className="text-button" onClick={() => onOpenJob(followUpContext.parent!.job_id)}>Open parent run <ArrowRight size={14} /></button></div>}
      {followUpContext?.claims.length ? <div className="follow-up-claims">{followUpContext.claims.map((item) => <article className="follow-up-claim" key={item.claim.id}><b>{item.claim.text}</b><span>{item.source.title} · {item.passage.locator} · {sourceAccessLabel(item.source.retrieval_status)}</span><button className="text-button" onClick={() => onSelectClaim(item.claim)}>Inspect parent passage <ArrowRight size={14} /></button></article>)}</div> : <div className="not-ready">{followUpContext?.status === 'retrieval_continuation' ? 'The continuation contains copied source evidence and will add any newly retrieved excerpts to its own report.' : followUpContext ? 'No parent claims matched this follow-up question. The new run will search its own evidence.' : 'Follow-up context is not available yet.'}</div>}
      {followUpContext?.reuse_boundary && <p className="follow-up-boundary">{followUpContext.reuse_boundary}</p>}
    </section>}
  </div>;
}

function StageTimeline({ job, events }: { job: ResearchJob; events: JobEvent[] }) {
  const completedStages = new Set(events.filter((event) => event.event_type === 'step_completed').map((event) => event.stage));
  const labels = ['Plan', 'Discover', 'Extract', 'Appraise', 'Compare', 'Verify', 'Synthesize', 'Save report'];
  const finalized = ['completed', 'completed_with_limitations'].includes(job.status);
  return <div className="stage-card"><div className="stage-track">{labels.map((label, index) => { const key = stages[index]; const done = completedStages.has(key) || (key === 'complete' && finalized); const active = key === job.current_stage && !terminal(job); return <div className={`stage-step ${done ? 'done' : ''} ${active ? 'active' : ''}`} key={key}><span className="stage-dot">{done ? <Check size={12} /> : index + 1}</span><span className="stage-name">{label}</span>{index < labels.length - 1 && <span className={`stage-connector ${done ? 'done' : ''}`} />}</div>; })}</div><div className="stage-caption"><span><span className="legend-dot current" /> Current step: <b>{terminal(job) ? prettyStatus(job.status) : stageLabel(job.current_stage)}</b></span><span>{events.length} saved updates</span></div></div>;
}

function sourceAccessLabel(status: string) {
  const labels: Record<string, string> = {
    full_text_html: 'LICENSED HTML EXCERPTS',
    full_text_pdf: 'LICENSED PDF TEXT',
    full_text_jats: 'LICENSED JATS FULL TEXT',
    abstract_only: 'ABSTRACT-ONLY',
    metadata_only: 'METADATA-ONLY',
    official_statistics: 'OFFICIAL STATISTIC',
    official_publication_page_body: 'OFFICIAL PUBLICATION PAGE BODY',
  };
  return labels[status] || status.replace(/_/g, '-').toUpperCase();
}

function abstractTextRetentionLabel(status: string) {
  if (status === 'not_retained_item_text_rights_unverified') {
    return 'Abstract omitted: item/version reuse rights are unverified.';
  }
  if (status === 'legacy_not_recorded') {
    return 'Legacy abstract text is stored; item/version reuse rights were not recorded.';
  }
  if (status === 'not_available') return 'No provider abstract was available.';
  return status.replace(/_/g, ' ');
}

function retrievalOutcomeLabel(outcome: string) {
  const labels: Record<string, string> = {
    not_attempted: 'NOT ATTEMPTED',
    retrieved: 'RETRIEVED',
    partial: 'PARTIAL',
    unavailable: 'UNAVAILABLE',
    error: 'ERROR',
    deferred: 'DEFERRED',
  };
  return labels[outcome] || outcome.replace(/_/g, ' ').toUpperCase();
}

function RetrievalOutcomeBadges({ retrieval }: { retrieval: Source['retrieval'] }) {
  const entries = Object.entries(retrieval?.outcomes?.by_format || {}).filter((entry) => entry[1]);
  if (!entries.length) return null;
  return <>{entries.map(([format, row]) => {
    if (!row) return null;
    const cautious = ['partial', 'unavailable', 'error', 'deferred'].includes(row.outcome);
    return <span className={`access-badge ${cautious ? 'caution' : 'neutral'}`} key={format}>{format.toUpperCase()} · {retrievalOutcomeLabel(row.outcome)}</span>;
  })}</>;
}

function OverviewPanel({ plan, events, sources, onViewSources }: { plan: ResearchPlan | null; events: JobEvent[]; sources: Source[]; onViewSources: () => void }) {
  const modelExecutionPlan = latestModelExecutionPlan(events);
  const htmlCount = sources.filter((source) => source.retrieval_status === 'full_text_html').length;
  const pdfCount = sources.filter((source) => source.retrieval_status === 'full_text_pdf').length;
  const jatsCount = sources.filter((source) => source.retrieval_status === 'full_text_jats').length;
  const abstractCount = sources.filter((source) => source.retrieval_status === 'abstract_only').length;
  const metadataCount = sources.filter((source) => source.retrieval_status === 'metadata_only').length;
  const statisticsCount = sources.filter((source) => source.source_type === 'official_statistics').length;
  const attemptCounts = sources.flatMap((source) => Object.values(source.retrieval?.outcomes?.by_format || {})).reduce((counts, outcome) => {
    if (outcome) counts[outcome.outcome] = (counts[outcome.outcome] || 0) + 1;
    return counts;
  }, {} as Record<string, number>);
  const contextLabels: [keyof NonNullable<ResearchPlan['decision_context']>, string][] = [
    ['decision_objective', 'Decision objective'],
    ['context', 'Decision context'],
    ['population', 'Population'],
    ['geography', 'Geography'],
    ['time_horizon', 'Time horizon'],
  ];
  const rationaleByQuery = new Map((plan?.query_rationales || []).map((item) => [item.query, item]));
  const planMethod = plan?.planning_mode === 'model_assisted_selection'
    ? `Model-assisted selection · ${plan.planning_provenance?.provider || 'provider unavailable'} · ${plan.planning_provenance?.model || 'model unavailable'}`
    : plan?.planning_mode === 'deterministic_fallback'
      ? `Deterministic fallback · ${(plan.planning_provenance?.fallback_reason || 'provider blocked').replace(/_/g, ' ')}`
      : 'Deterministic plan · no model call';
  return <div className="overview-grid">
    {modelExecutionPlan && <ModelWorkloadPlanCard plan={modelExecutionPlan} />}
    <section className="content-card plan-card">
      <div className="card-title-row"><div><p className="eyebrow">RESEARCH PLAN</p><h2>Questions to investigate</h2></div><span className="plan-version">{plan ? `v${plan.version}` : 'PENDING'}</span></div>
      {plan ? <>
        {plan.decision_context && <div className="decision-context" aria-label="Saved decision context">
          {contextLabels.map(([field, label]) => <div key={field}><span>{label}</span><b>{plan.decision_context?.[field] || 'Not specified'}</b></div>)}
        </div>}
        {plan.scope_notice && <p className={`scope-notice ${plan.scope_status === 'underspecified' ? 'warning' : ''}`} role={plan.scope_status === 'underspecified' ? 'status' : undefined}>{plan.scope_notice}</p>}
        {plan.planning_lenses && <details className="plan-lenses" open>
          <summary>Comparator, outcomes and bias checks</summary>
          <dl>
            <div><dt>Comparator or counterfactual</dt><dd><b>{plan.planning_lenses.comparator_or_counterfactual.user_statement || 'Not specified'}</b><span>{plan.planning_lenses.comparator_or_counterfactual.prompt}</span></dd></div>
            <div><dt>Outcome and denominator</dt><dd><b>{plan.planning_lenses.outcomes.target_outcome || 'Outcome not specified'} · {plan.planning_lenses.outcomes.denominator || 'Denominator not specified'}</b><span>{plan.planning_lenses.outcomes.possible_outcomes_prompt} {plan.planning_lenses.outcomes.denominator_prompt}</span></dd></div>
            <div><dt>Assumptions</dt><dd><b>{plan.planning_lenses.assumptions.status === 'user_supplied' ? plan.planning_lenses.assumptions.user_supplied_text : 'No assumptions supplied; none inferred'}</b></dd></div>
            <div><dt>Confounding and measurement</dt><dd><span>{plan.planning_lenses.confounding.prompt}</span></dd></div>
            <div><dt>Evidence designs to consider</dt><dd><b>{plan.planning_lenses.evidence_types.types_to_consider.map((item) => item.replace(/_/g, ' ')).join(' · ')}</b><span>Planning lenses only; these are not provider search filters.</span></dd></div>
          </dl>
        </details>}
        <div className="plan-method">{planMethod}</div>
        <div className="subquestion-list">{plan.subquestions.map((question, index) => <div className="subquestion" key={index}><span className="sub-number">{String(index + 1).padStart(2, '0')}</span><span><b>{question.text}</b><small>{question.purpose}</small></span></div>)}</div>
        <div className="query-list"><span>SEARCH QUERIES AND PURPOSE</span>{plan.queries.map((query, index) => <div className="planned-query" key={`${index}-${query}`}><Search size={13} /><span><b>{query}</b>{rationaleByQuery.has(query) && <small>{rationaleByQuery.get(query)?.purpose}</small>}</span></div>)}</div>
        {plan.stopping_criteria && <details className="plan-stopping"><summary>When Veda will qualify or abstain</summary><dl>
          <div><dt>Search bound</dt><dd>{plan.stopping_criteria.execution}</dd></div>
          <div><dt>Insufficient evidence</dt><dd>{plan.stopping_criteria.insufficient_evidence}</dd></div>
          <div><dt>Comparability</dt><dd>{plan.stopping_criteria.incomparability}</dd></div>
          <div><dt>Counterevidence</dt><dd>{plan.stopping_criteria.counterevidence}</dd></div>
        </dl></details>}
      </> : <div className="not-ready"><CircleHelp size={18} /><span>The plan will appear after the first research step is saved.</span></div>}
    </section>
    <section className="content-card coverage-card"><div className="card-title-row"><div><p className="eyebrow">COVERAGE SNAPSHOT</p><h2>What we have</h2></div><BookOpen size={17} className="muted-icon" /></div><div className="coverage-number">{sources.length}<small> sources discovered</small></div><div className="coverage-rows"><span>Europe PMC JATS full text <b>{jatsCount}</b></span><span>Licensed HTML excerpts <b>{htmlCount}</b></span><span>Licensed PDF text <b>{pdfCount}</b></span><span>Abstract-only <b>{abstractCount}</b></span><span>Metadata only <b>{metadataCount}</b></span><span>Official statistics <b>{statisticsCount}</b></span><span>Retrieval partial / errors / deferred <b>{attemptCounts.partial || 0} / {attemptCounts.error || 0} / {attemptCounts.deferred || 0}</b></span><span>Passage-linked claims <b>{events.reduce((count, event) => count + Number(event.data.claim_count || 0), 0)}</b></span></div><button className="text-button" onClick={onViewSources}>Explore source library <ArrowRight size={14} /></button></section>
    <section className="content-card updates-card"><div className="card-title-row"><div><p className="eyebrow">CHECKPOINTS</p><h2>Recent updates</h2></div><span className="plan-version">{events.length} TOTAL</span></div>{events.length ? <div className="update-list">{[...events].reverse().slice(0, 5).map((event) => <div className="update-item" key={event.id}><span className={`update-dot ${event.event_type}`} /><span><b>{event.message}</b><small>{event.stage ? stageLabel(event.stage) : 'Job'} · {new Date(event.created_at).toLocaleTimeString(undefined, { hour: 'numeric', minute: '2-digit' })}</small></span></div>)}</div> : <div className="not-ready">The first checkpoint will appear here.</div>}</section>
    <section className="content-card honest-card"><div className="honest-icon"><ShieldCheck size={18} /></div><div><b>Evidence status stays visible</b><p>Stored statements remain source-reported and unverified. Official time-series observations are descriptive rather than causal. Licensed HTML and PDF excerpts are bounded; PDF text extraction does not use OCR.</p></div></section>
  </div>;
}

function ModelWorkloadPlanCard({ plan }: { plan: ModelExecutionPlan }) {
  const quota = plan.daily_quota_snapshot;
  const currency = plan.authorized_spend_currency === 'INR' ? 'INR' : 'USD';
  const formatSpend = (value: number) => new Intl.NumberFormat(
    currency === 'INR' ? 'en-IN' : 'en-US',
    { style: 'currency', currency, maximumFractionDigits: 2 },
  ).format(value);
  const operationLabel = (item: ModelExecutionPlan['accepted'][number]) =>
    `${stageLabel(item.stage)}${item.batch > 1 ? ` · batch ${item.batch}` : ''} · ${item.completion_tokens.toLocaleString()} output tokens`;
  return <section className="content-card model-plan-card" aria-label="Pre-dispatch model workload plan">
    <div className="card-title-row"><div><p className="eyebrow">PRE-DISPATCH MODEL PLAN</p><h2>Requests and limits</h2></div><span className={`plan-version ${plan.complete ? 'plan-ready' : 'plan-limited'}`}>{plan.complete ? 'ALL PLANNED WORK FITS' : `${plan.deferred_calls} DEFERRED`}</span></div>
    <p className="model-plan-route">{plan.provider}{plan.model ? ` · ${plan.model}` : ''}</p>
    <div className="model-plan-metrics">
      <span>Remaining graph <b>{plan.planned_calls}/{plan.required_calls} requests</b></span>
      <span>Prior reservations <b>{plan.reserved_calls_before_plan} requests</b></span>
      <span>Output allocation <b>{plan.planned_output_tokens.toLocaleString()}/{plan.required_output_tokens.toLocaleString()} tokens</b></span>
      <span>Authorized ceiling <b>{formatSpend(plan.authorized_spend_ceiling)}</b></span>
      <span>Remaining ceiling <b>{formatSpend(plan.remaining_authorized_spend)}</b></span>
      <span>Latency estimate <b>{plan.latency_estimate_ms == null ? 'Unavailable' : `${plan.latency_estimate_ms.toLocaleString()} ms`}</b></span>
      {quota && <span>Daily call slots <b>Global {String(quota.global_remaining ?? '?')} · this user {String(quota.per_user_remaining ?? '?')}</b></span>}
    </div>
    <p className="model-plan-note">The plan is a pre-dispatch allocation, not a completion report. Exact prompt token envelopes and cost reservations are checked before each call. No validated provider-and-stage latency baseline is available.</p>
    {(plan.accepted.length > 0 || plan.deferred.length > 0) && <details className="model-plan-details">
      <summary>Inspect operation allocation ({plan.accepted.length} planned · {plan.deferred.length} deferred)</summary>
      <ul>{plan.accepted.map((item, index) => <li key={`accepted-${item.operation}-${item.stage}-${item.batch}-${index}`}>{operationLabel(item)}</li>)}{plan.deferred.map((item, index) => <li className="deferred-operation" key={`deferred-${item.operation}-${item.stage}-${item.batch}-${index}`}>{operationLabel(item)} · deferred: {(item.deferred_reason || 'unspecified').replace(/_/g, ' ')}</li>)}</ul>
    </details>}
  </section>;
}

function SourcesPanel({ sources, candidates, onSelect }: { sources: Source[]; candidates: DiscoveryCandidate[]; onSelect: (source: Source) => void }) {
  const [filter, setFilter] = useState('all');
  const [view, setView] = useState<'sources' | 'candidates'>('sources');
  const filtered = sources.filter((source) => filter === 'all' || source.retrieval_status === filter || source.source_type === filter || Object.values(source.retrieval?.outcomes?.by_format || {}).some((outcome) => outcome?.outcome === filter));
  return <section className="content-card library-panel"><div className="panel-heading"><div><p className="eyebrow">DISCOVERED RECORDS</p><h2>Source library and selection ledger</h2><p>Crossref, OpenAlex, and OpenAIRE scholarly metadata, World Bank Documents &amp; Reports institutional publications, World Bank Data360 observations, and a bounded global ILOSTAT employment series. Full-text retrieval requires an accepted OpenAlex license assertion, an exact reviewed host policy, and an allowing robots rule. Statistics remain separate from study records.</p></div>{view === 'sources' && <label className="filter-select"><span>Access or attempt status</span><select value={filter} onChange={(e) => setFilter(e.target.value)}><option value="all">All sources</option><option value="full_text_html">Licensed HTML excerpts</option><option value="full_text_pdf">Licensed PDF text</option><option value="abstract_only">Abstract-only</option><option value="metadata_only">Metadata only</option><option value="official_statistics">Official statistics</option><option value="institutional_report">Institutional reports</option><option value="partial">Partial retrieval</option><option value="unavailable">Format unavailable</option><option value="error">Retrieval error</option><option value="deferred">Retrieval deferred</option><option value="not_attempted">Not attempted</option></select><ChevronDown size={13} /></label>}</div>
    <div className="source-view-toggle" role="tablist" aria-label="Source records"><button type="button" role="tab" aria-selected={view === 'sources'} onClick={() => setView('sources')}>Selected sources <small>{sources.length}</small></button><button type="button" role="tab" aria-selected={view === 'candidates'} onClick={() => setView('candidates')}>All candidates <small>{candidates.length}</small></button></div>
    {view === 'candidates' && <p className="candidate-ranking-note">The source-cap order uses the higher of two auditable lexical-overlap scores: the original question and the exact provider query that found the candidate. The original-question score remains visible, and the topic eligibility gate still uses the original question. These scores indicate retrieval relevance only, not study quality or truth. Official statistics do not receive these scholarly scores.</p>}
    {view === 'sources' ? (filtered.length ? <div className="source-list">{filtered.map((source, index) => <button className="source-row" key={source.id} onClick={() => onSelect(source)}><span className="source-number">S{String(index + 1).padStart(2, '0')}</span><span className="source-info"><b>{source.title}</b><span>{source.source_type === 'official_statistics' ? 'Official statistical series' : source.source_type === 'institutional_report' ? 'Institutional research report' : source.authors.map(authorLabel).filter(Boolean).join(', ') || 'Authors not listed'}{source.published_year ? ` · ${source.published_year}` : ''}{source.publisher ? ` · ${source.publisher}` : ''}</span><span className="source-badges"><span className={`access-badge ${source.retrieval_status}`}>{sourceAccessLabel(source.retrieval_status)}</span><RetrievalOutcomeBadges retrieval={source.retrieval} /><span className="access-badge neutral">{source.source_type === 'official_statistics' ? 'NOT A STUDY' : source.appraisal?.status === 'model_assessed_not_independently_verified' ? 'MODEL-ASSESSED · NOT VERIFIED' : 'APPRAISAL NOT PERFORMED'}</span></span></span><ArrowRight size={16} className="source-chevron" /></button>)}</div> : <div className="not-ready">{sources.length ? 'No source records match this filter.' : 'No sources are stored yet. Advance discovery to search scholarly sources and supported official statistics.'}</div>) : (candidates.length ? <div className="source-list">{candidates.map((candidate) => <article className="source-row candidate-row" key={candidate.id}><span className="source-number">{candidate.disposition === 'selected' ? 'IN' : 'OUT'}</span><span className="source-info"><b>{candidate.title}</b><span>{candidate.provider}{candidate.publisher ? ` · Publisher: ${candidate.publisher}` : ''}{candidate.doi ? ` · DOI ${candidate.doi}` : ''}{candidate.published_year ? ` · ${candidate.published_year}` : ''}{candidate.provider === 'World Bank Documents & Reports' ? ` · Repository record ${candidate.provider_record_id.replace(/^worldbank:/, '')}` : ''}</span><span className="source-badges"><span className={`access-badge ${candidate.disposition === 'selected' ? 'full_text_html' : 'neutral'}`}>{candidate.disposition === 'selected' ? 'SELECTED' : 'EXCLUDED'}</span><span className="access-badge neutral">{candidate.reason_code.replace(/_/g, ' ')}</span>{candidate.relevance?.topic_eligibility_basis && <span className="access-badge neutral">TOPIC GATE · {candidate.relevance.topic_eligibility_basis.replace(/_/g, ' ')}</span>}{candidate.relevance_score != null && <span className="access-badge neutral">QUESTION SCORE {candidate.relevance_score.toFixed(2)}</span>}{candidate.planned_query_score != null && <span className="access-badge neutral">QUERY SCORE {candidate.planned_query_score.toFixed(2)}</span>}{candidate.selection_score != null && <span className="access-badge neutral">RANK SCORE {candidate.selection_score.toFixed(2)}</span>}</span><small>Query: {candidate.query} · discovered {new Date(candidate.discovered_at).toLocaleString()}</small>{candidate.publisher_organizations?.map((organization) => <small key={organization.organization_id}>Publisher identity: {organization.canonical_name} · {organization.identity_status.replace(/_/g, ' ')} · identity only; methodology not assessed. <a href={organization.official_url} target="_blank" rel="noreferrer">Official directory record</a></small>)}{candidate.abstract_excerpt && candidate.abstract_excerpt_retention_status === 'retained_item_license_verified_v1' && <small>Permitted candidate abstract excerpt: {candidate.abstract_excerpt}</small>}{candidate.abstract_excerpt_retention_status === 'not_retained_item_text_rights_unverified' && <small>Abstract text omitted: reuse rights are not verified for this source version.</small>}{candidate.relevance && <small>Question: {candidate.relevance.explanation}{candidate.relevance.planned_query_alignment && <> Planned query: {candidate.relevance.planned_query_alignment.explanation}</>} {candidate.relevance.interpretation_limit}</small>}{candidate.source_governance && <small>Source class: {candidate.source_governance.source_classes.join(', ') || 'unclassified'} · identity {candidate.source_governance.identity_status} · methodology not assessed by institutional identity.</small>}</span></article>)}</div> : <div className="not-ready">No discovery candidates are stored yet. Abstract text is omitted unless item and version specific reuse permission is recorded; full text has a separate access and rights decision.</div>)}
  </section>;
}

function EvidencePanel({ claims, sources, onSelect }: { claims: Claim[]; sources: Source[]; onSelect: (claim: Claim) => void }) {
  const sourceMap = new Map(sources.map((source) => [source.id, source]));
  return <section className="content-card library-panel"><div className="panel-heading"><div><p className="eyebrow">PASSAGE-LINKED STATEMENTS</p><h2>Evidence ledger</h2><p>Passage-linked source-reported statements and transcribed official observations. They have not been independently verified.</p></div><span className="evidence-count"><Clipboard size={15} /> {claims.length} statements</span></div>{claims.length ? <div className="claim-list">{claims.map((claim, index) => <button className="claim-card" key={claim.id} onClick={() => onSelect(claim)}><span className="claim-index">{String(index + 1).padStart(2, '0')}</span><span className="claim-body"><b>{claim.text}</b><span className="claim-source"><BookOpen size={13} />{sourceMap.get(claim.source_id)?.title || 'Source record'}</span><span className="claim-badges"><span className="access-badge neutral">SOURCE-REPORTED</span><span className="access-badge caution">NOT INDEPENDENTLY VERIFIED</span></span></span><ArrowRight size={16} className="source-chevron" /></button>)}</div> : <div className="not-ready">Abstract sentences that can be stored as exact short excerpts will appear here after extraction. No claim will be created without a real passage.</div>}</section>;
}

function ComparisonPanel({ relationships, hypotheses, relationshipStatus, hypothesisStatus, claims, sources, onSelectClaim }: { relationships: EvidenceRelationship[]; hypotheses: CompetingHypothesis[]; relationshipStatus: string; hypothesisStatus: string; claims: Claim[]; sources: Source[]; onSelectClaim: (claim: Claim) => void }) {
  const claimById = new Map(claims.map((claim) => [claim.id, claim]));
  const sourceById = new Map(sources.map((source) => [source.id, source]));
  const grouped = new Map<string, CompetingHypothesis[]>();
  for (const item of hypotheses) grouped.set(item.comparison_group_id, [...(grouped.get(item.comparison_group_id) || []), item]);
  const modelState = (status: string) => status === 'model_assessed_not_independently_verified'
    ? 'MODEL-ASSESSED · NOT VERIFIED' : prettyStatus(status).toUpperCase();
  const renderEvidence = (items: EvidenceLink[]) => items.map((link, index) => {
    const claim = claimById.get(link.claim_id);
    const source = claim ? sourceById.get(claim.source_id) : undefined;
    return claim
      ? <button className="comparison-evidence" key={`${link.claim_id}-${index}`} onClick={() => onSelectClaim(claim)}><b>{source?.title || 'Open source-reported claim'}</b><span>{claim.text}</span><small>{link.passage_ids.length} linked {link.passage_ids.length === 1 ? 'passage' : 'passages'} · open evidence inspector</small></button>
      : <span className="comparison-evidence missing" key={`${link.claim_id}-${index}`}>Linked claim is not present in the loaded evidence list.</span>;
  });
  return <div className="comparison-panel">
    <section className="content-card comparison-section">
      <div className="panel-heading"><div><p className="eyebrow">EVIDENCE RELATIONSHIPS</p><h2>How stored claims compare</h2><p>These are model-assisted comparisons of source-reported statements. A contradiction is distinguished from scope differences and unknown scope.</p></div><span className="access-badge caution">{modelState(relationshipStatus)}</span></div>
      {relationships.length ? <div className="comparison-list">{relationships.map((item) => <article className="relationship-card" key={item.id}>
        <div className="relationship-heading"><span className={`relation-badge ${item.relationship_type}`}>{prettyStatus(item.relationship_type)}</span><span className="comparison-scope">Scope: {prettyStatus(item.scope_alignment)}</span></div>
        <div className="relationship-claims">{renderEvidence(item.evidence)}</div>
        <p className="relationship-rationale">{item.rationale}</p>
        {item.scope_differences.length > 0 && <div className="scope-differences"><b>Scope differences</b>{item.scope_differences.map((difference) => <span key={difference}>{prettyStatus(difference)}</span>)}</div>}
        <small className="comparison-provenance">{item.status} · {item.provider || 'provider unavailable'} / {item.model || 'model not recorded'} · schema v{item.schema_version}</small>
      </article>)}</div> : <div className="not-ready">{relationshipStatus === 'not_assessed' ? 'Comparison has not been assessed yet.' : relationshipStatus === 'no_supported_relationships_or_hypotheses' ? 'The comparison model stored no evidence-linked relationships. This is not evidence that the studies agree.' : 'No evidence-linked claim relationships were stored for this run.'}</div>}
    </section>
    <section className="content-card comparison-section">
      <div className="panel-heading"><div><p className="eyebrow">COMPETING EXPLANATIONS</p><h2>Hypotheses held side by side</h2><p>Each explanation is shown with its own evidence and uncertainty. Open a linked statement to inspect its passage.</p></div><span className="access-badge caution">{modelState(hypothesisStatus)} · {grouped.size} PAIRS</span></div>
      {grouped.size ? <div className="hypothesis-list">{[...grouped.entries()].map(([groupId, pair]) => {
        const sideA = pair.find((item) => item.side === 'A');
        const sideB = pair.find((item) => item.side === 'B');
        return <article className="hypothesis-pair" key={groupId}>
          <p className="why-competing">{sideA?.why_competing || sideB?.why_competing || 'The model did not record why these explanations compete.'}</p>
          <div className="hypothesis-sides">{(['A', 'B'] as const).map((side) => {
            const item = side === 'A' ? sideA : sideB;
            return <div className={`hypothesis-card ${!item ? 'missing' : ''}`} key={side}>
              <span className="hypothesis-side">HYPOTHESIS {side}</span>
              {item ? <><p>{item.statement}</p><div className="hypothesis-uncertainty"><b>Uncertainty</b><span>{item.uncertainty}</span></div><div className="hypothesis-links">{renderEvidence(item.evidence)}</div><small className="comparison-provenance">{item.status} · {item.provider || 'provider unavailable'} / {item.model || 'model not recorded'}</small></> : <span>Hypothesis side {side} was not stored.</span>}
            </div>;
          })}</div>
        </article>;
      })}</div> : <div className="not-ready">{hypothesisStatus === 'not_assessed' ? 'Competing explanations have not been assessed yet.' : hypothesisStatus === 'no_supported_relationships_or_hypotheses' ? 'No evidence-linked competing pair passed the storage checks.' : 'No competing hypothesis pairs were stored. Veda does not invent a pair when the evidence is insufficient.'}</div>}
      <div className="audit-warning"><ShieldCheck size={15} /><span>Relationships and hypotheses are model-generated interpretations, not validated scientific conclusions. Check the linked source passages and study methods.</span></div>
    </section>
  </div>;
}

function ReportPanel({ report, job, sources, claims, onSelectClaim, onSelectSource, onError }: { report: ResearchReport | null; job: ResearchJob; sources: Source[]; claims: Claim[]; onSelectClaim: (claim: Claim) => void; onSelectSource: (source: Source) => void; onError: (error: unknown) => void }) {
  if (!report) return <section className="content-card report-pending"><div className="report-icon"><FileText size={21} /></div><h2>Your evidence map is taking shape.</h2><p>Veda saves a report after source links are checked. The report will state the limits of the evidence it actually accessed.</p><span>{job.current_stage === 'complete' ? 'Report could not be loaded. Refresh to try again.' : `Current step: ${stageLabel(job.current_stage)}`}</span></section>;
  const renderLink = ({ href, children }: { href?: string; children?: React.ReactNode }) => {
    const citation = href?.match(/^#veda-citation-(S\d+)$/)?.[1];
    if (citation) {
      const sourceId = report.citation_map[citation]?.source_id;
      const source = sources.find((item) => item.id === sourceId);
      return <button type="button" className="citation-link" onClick={() => source && onSelectSource(source)} aria-label={`Open source ${citation}`}>{children}</button>;
    }
    return <a href={href} target={href?.startsWith('http') ? '_blank' : undefined} rel={href?.startsWith('http') ? 'noreferrer' : undefined}>{children}</a>;
  };
  const appraisalStatus = report.verification.model_assisted_appraisal === 'performed_not_independently_verified' ? 'MODEL-ASSESSED · NOT VERIFIED' : 'NOT RUN';
  const reportTitle = report.verification.model_assisted_synthesis === 'performed_not_independently_verified'
    ? 'Model-assisted research synthesis'
    : 'Preliminary evidence map';
  const semanticRaw = String(report.verification.semantic_support_check || 'not_performed');
  const semanticStatus = semanticRaw === 'performed_model_assisted_not_independently_verified'
    ? 'MODEL-ASSESSED · NOT VERIFIED'
    : semanticRaw === 'needs_review' ? 'NEEDS REVIEW' : 'NOT RUN';
  const uncitedRaw = String(report.verification.uncited_material_claim_scan || 'not_performed');
  const uncitedDone = uncitedRaw.startsWith('performed_');
  const uncitedStatus = uncitedRaw === 'performed_partial_model_assisted_not_guaranteed'
    ? 'PARTIAL MODEL SCAN'
    : uncitedDone ? 'MODEL SCAN · NOT GUARANTEED' : 'NOT RUN';
  const semanticItems = Array.isArray(report.verification.semantic_audit_items)
    ? report.verification.semantic_audit_items as Array<Record<string, unknown>> : [];
  const semanticBatchCoverage = report.verification.semantic_audit_batch_coverage;
  const conditionalRouting = report.verification.search_coverage?.conditional_statistics_routing;
  const searchCoverage = report.verification.search_coverage;
  const searchLenses = Array.isArray(searchCoverage?.search_lenses) ? searchCoverage.search_lenses : [];
  const searchLensCounts = searchCoverage?.search_lens_counts;
  const citationExpansion = searchCoverage?.citation_expansion;
  const exclusionCounts = searchCoverage?.candidate_exclusion_counts || {};
  const routeRows: Array<{ label: string; outcome: StatisticsRouteOutcome }> = conditionalRouting?.status === 'recorded'
    ? [
        { label: 'World Bank Data360', outcome: conditionalRouting.world_bank_data360 || {} },
        { label: 'ILOSTAT', outcome: conditionalRouting.ilostat || {} },
      ]
    : [];
  const uncitedClaims = Array.isArray(report.verification.uncited_material_claims)
    ? report.verification.uncited_material_claims as Array<Record<string, unknown>> : [];
  const decisionImplications = Array.isArray(report.verification.decision_implications)
    ? report.verification.decision_implications as Array<Record<string, unknown>> : [];
  const claimUnits = Array.isArray(report.verification.claim_units)
    ? report.verification.claim_units as Array<Record<string, unknown>> : [];
  const evidenceSufficiency = report.verification.evidence_sufficiency_v1;
  const claimById = new Map(claims.map((claim) => [claim.id, claim]));
  const semanticDone = semanticStatus !== 'NOT RUN';
  return <div className="report-layout">
    <section className="content-card report-reader">
      <div className="report-header"><div><p className="eyebrow">SAVED RESEARCH REPORT</p><h2>{reportTitle}</h2><span className="report-date">Saved {new Date(report.created_at).toLocaleString()}</span></div><div className="export-actions"><button className="quiet-button" onClick={() => void apiClient.downloadReport(report, 'markdown').catch(onError)}><Download size={14} /> Markdown</button><button className="icon-button" title="Download JSON" onClick={() => void apiClient.downloadReport(report, 'json').catch(onError)}><Download size={15} /></button></div></div>
      {report.evidence_content_withheld && <div className="audit-warning" role="status"><ShieldCheck size={15} /><span>Historical report text is withheld because abstract-version text reuse rights were not recorded. The saved database record is unchanged.</span></div>}
      <div className="report-content"><ReactMarkdown remarkPlugins={[remarkGfm]} components={{ a: renderLink }}>{linkifyCitationMarkers(report.body_markdown)}</ReactMarkdown></div>
      {report.evidence_content_withheld && <section className="withheld-citation-index" aria-label="Cited sources available for inspection"><h3>Citations available for source inspection</h3><p>Report wording is withheld; these saved citation links remain available for provenance review.</p><ul>{Object.entries(report.citation_map).map(([citation, item]) => {
        const citedSource = sources.find((candidate) => candidate.id === item.source_id);
        return citedSource ? <li key={citation}><button type="button" className="citation-link" aria-label={`Open source ${citation} · ${citedSource.title}`} onClick={() => onSelectSource(citedSource)}>{citation} · {citedSource.title}</button></li> : <li key={citation}>{citation} · Source record unavailable</li>;
      })}</ul></section>}
    </section>
    <aside className="content-card audit-card">
      <p className="eyebrow">VERIFICATION</p><h3>What was checked</h3>
      {evidenceSufficiency && <div className="audit-warning" role="status" aria-label="Evidence sufficiency status"><ShieldCheck size={15} /><span><b>Automated evidence status · {evidenceSufficiency.status.replace(/_/g, ' ')}</b><br />This policy result is not independent peer review. Human review: {evidenceSufficiency.human_review_status.replace(/_/g, ' ')}.{evidenceSufficiency.blocking_conditions.length > 0 && <><br /><small>Open conditions: {evidenceSufficiency.blocking_conditions.join('; ')}</small></>}</span></div>}
      <div className="audit-status"><span className="audit-check"><Check size={14} /></span><span><b>Source links</b><small>Deterministic reference integrity</small></span><em>{String(report.verification.status || 'passed').toUpperCase()}</em></div>
      <div className={`audit-status ${semanticDone ? '' : 'off'}`}><span className={semanticDone ? 'audit-check' : 'audit-minus'}>{semanticDone ? <Check size={14} /> : <X size={13} />}</span><span><b>Passage support</b><small>Separate model-assisted semantic review</small></span><em>{semanticStatus}</em></div>
      <div className={`audit-status ${appraisalStatus === 'NOT RUN' ? 'off' : ''}`}><span className={appraisalStatus === 'NOT RUN' ? 'audit-minus' : 'audit-check'}>{appraisalStatus === 'NOT RUN' ? <X size={13} /> : <Check size={14} />}</span><span><b>Source appraisal</b><small>Model-assisted, unverified</small></span><em>{appraisalStatus}</em></div>
      <div className={`audit-status ${uncitedDone ? '' : 'off'}`}><span className={uncitedDone ? 'audit-check' : 'audit-minus'}>{uncitedDone ? <Check size={14} /> : <X size={13} />}</span><span><b>Uncited claims</b><small>Model scan; completeness not guaranteed</small></span><em>{uncitedStatus}</em></div>
      {semanticItems.length > 0 && <details className="audit-detail"><summary>Passage review ({semanticItems.length})</summary>{semanticItems.map((item, index) => <div className="audit-detail-item" key={`${String(item.item_id)}-${index}`}><b>{String(item.item_id)} · {String(item.verdict || 'unassessed').toUpperCase()} · {String(item.status || '')}</b><p>{String(item.rationale || '')}</p></div>)}</details>}
      <details className="audit-detail" open>
        <summary>Semantic audit input coverage</summary>
        {semanticBatchCoverage ? <>
          <div className="audit-detail-item" role="status">
            <b>{semanticBatchCoverage.complete ? 'All planned batches completed' : 'Audit coverage is incomplete'}</b>
            <p>{Number(semanticBatchCoverage.completed_batches || 0)} of {Number(semanticBatchCoverage.expected_batches || 0)} batches completed · {Number(semanticBatchCoverage.assessed_item_ids?.length || 0)} of {Number(semanticBatchCoverage.expected_item_ids?.length || 0)} material items assessed · {Number(semanticBatchCoverage.scan_character_coverage || 0)} of {Number(semanticBatchCoverage.report_characters || 0)} report characters covered.</p>
            <small>Input coverage accounting does not guarantee that the model detected every unsupported statement. Human review: not performed.</small>
          </div>
          {(semanticBatchCoverage.batches || []).map((batch, index) => <div className="audit-detail-item" key={`${String(batch.batch_id || 'batch')}-${index}`}>
            <b>{String(batch.batch_id || `Batch ${index + 1}`)} · {String(batch.status || 'unknown').replace(/_/g, ' ')}</b>
            <p>{batch.scan_end != null && batch.scan_start != null ? `Report characters ${batch.scan_start}–${batch.scan_end}. ` : ''}{batch.provider && batch.model ? `${batch.provider} · ${batch.model}.` : ''}{batch.error_class ? ` ${String(batch.error_class).replace(/_/g, ' ')}.` : ''}</p>
            {batch.usage && <small>Token usage: input {String(batch.usage.input_tokens ?? 'unknown')} · output {String(batch.usage.output_tokens ?? 'unknown')} · reasoning {String(batch.usage.reasoning_tokens ?? 'unknown')} · reported cost {batch.usage.reported_cost_status === 'provider_reported' ? `${String(batch.usage.reported_cost_amount)} ${String(batch.usage.cost_currency || '')}` : 'unknown'}.</small>}
          </div>)}
          {semanticBatchCoverage.unresolved_batch_ids?.length ? <div className="audit-detail-item"><b>Unresolved batches</b><p>{semanticBatchCoverage.unresolved_batch_ids.join(', ')}</p></div> : null}
          {semanticBatchCoverage.skipped_item_ids?.length ? <div className="audit-detail-item"><b>Items that could not be audited</b><p>{semanticBatchCoverage.skipped_item_ids.join(', ')}</p></div> : null}
          {semanticBatchCoverage.output_limit_batch_ids?.length ? <div className="audit-detail-item"><b>Potential output-limit batches</b><p>{semanticBatchCoverage.output_limit_batch_ids.join(', ')}</p></div> : null}
        </> : <div className="audit-detail-item"><p>Batch-level semantic audit coverage was not recorded for this historical report.</p></div>}
      </details>
      {uncitedClaims.length > 0 && <details className="audit-detail" open><summary>Uncited statements flagged ({uncitedClaims.length})</summary>{uncitedClaims.map((item, index) => <div className="audit-detail-item" key={`${String(item.section)}-${index}`}><b>{String(item.section)} · {String(item.recommendation || '').replace(/_/g, ' ')}</b><p>{String(item.text || '')}</p></div>)}</details>}
      <details className="audit-detail" open>
        <summary>Scholarly search coverage</summary>
        {searchCoverage?.status === 'recorded' ? <>
          {searchCoverage.source_governance?.plan_status === 'persisted_at_discovery' && <div className="audit-detail-item">
            <b>Governed source-class coverage · registry {String(searchCoverage.source_governance.registry_version || 'version not recorded')}</b>
            <p>Source classes are planned independently from whether a connector is available or was actually searched.</p>
            <small>Planned: {(searchCoverage.source_governance.planned_classes || []).join(', ') || 'none recorded'} · Searched: {(searchCoverage.source_governance.searched_classes || []).join(', ') || 'none'}</small>
            {Object.entries(searchCoverage.source_governance.class_status || {}).map(([sourceClass, details]) => <small key={sourceClass}>
              {sourceClass.replace(/_/g, ' ')}: {String(details.status || 'status not recorded').replace(/_/g, ' ')} · {Number(details.candidate_count || 0)} candidates · {Number(details.selected_count || 0)} selected
              {searchCoverage.source_governance?.class_selection_reasons?.[sourceClass]?.length
                ? ` · planned because the question matched: ${searchCoverage.source_governance.class_selection_reasons[sourceClass].join(', ')}`
                : ''}
            </small>)}
            {searchCoverage.source_governance.missing_classes?.length ? <small>Missing coverage: {searchCoverage.source_governance.missing_classes.join(', ')}</small> : <small>All planned source classes were searched.</small>}
            <small>{String(searchCoverage.source_governance.interpretation_limit || 'Institution identity does not establish publication quality or truth.')}</small>
          </div>}
          <div className="audit-detail-item">
            <b>{Number(searchCoverage.queries_planned || 0)} planned queries · {Number(searchCoverage.provider_queries_attempted || 0)} provider requests · {Number(searchCoverage.selected_sources || 0)} selected source records</b>
            <p>{Number(searchCoverage.candidate_ledger_records || 0)} candidate records retained for audit. Counterevidence search: {String(searchCoverage.counterevidence_search_status || 'not recorded').replace(/_/g, ' ')}. Stopping reason: {String(searchCoverage.retrieval_stopping_reason || 'not recorded').replace(/_/g, ' ')}.</p>
            <small>{searchCoverage.discovery_completed_at_utc ? `Discovery recorded ${new Date(searchCoverage.discovery_completed_at_utc).toLocaleString()}. ` : ''}Lexical retrieval alignment is not a measure of study quality, methodological reliability, or truth.</small>
          </div>
          {searchCoverage.government_publication_search && <div className="audit-detail-item">
            <b>Official government publication discovery · {String(searchCoverage.government_publication_search.status || 'not recorded').replace(/_/g, ' ')}</b>
            <p>{String(searchCoverage.government_publication_search.provider || 'Government provider')} · {String(searchCoverage.government_publication_search.geography || 'geography not recorded')} · {Number(searchCoverage.government_publication_search.returned_count || 0)} policy-paper metadata records · request dispatched: {Boolean(searchCoverage.government_publication_search.request_dispatched) ? 'yes' : 'no'}.</p>
            <small>Query: {String(searchCoverage.government_publication_search.query || 'not recorded')} · linked content fetched: {Boolean(searchCoverage.government_publication_search.linked_content_fetched) ? 'yes' : 'no'} · API support: {String(searchCoverage.government_publication_search.api_support_status || 'not recorded').replace(/_/g, ' ')}{searchCoverage.government_publication_search.error_code ? ` · ${searchCoverage.government_publication_search.error_code}` : ''}.</small>
          </div>}
          {searchCoverage.general_web_discovery?.schema_version === 1 && <div className="audit-detail-item">
            <b>General public-web discovery · {String(searchCoverage.general_web_discovery.status || 'unknown').replace(/_/g, ' ')} · {Number(searchCoverage.general_web_discovery.request_count || 0)} search request(s)</b>
            <p>{(searchCoverage.general_web_discovery.queries_planned || []).length} question-derived queries · free-plan preflight {String(searchCoverage.general_web_discovery.preflight_status || 'not performed').replace(/_/g, ' ')} · {Number(searchCoverage.general_web_discovery.reserved_credits || 0)} credits reserved · {Number(searchCoverage.general_web_discovery.reported_cost_credits || 0)} credits reported{searchCoverage.general_web_discovery.unresolved_reserved_credits ? ` · ${Number(searchCoverage.general_web_discovery.unresolved_reserved_credits)} credit reservation unresolved` : ''}{searchCoverage.general_web_discovery.account_balance_credits != null ? ` · free-credit balance ${Number(searchCoverage.general_web_discovery.account_balance_credits)}` : ''}{searchCoverage.general_web_discovery.allowance_left_credits != null ? ` · provider plan allowance ${Number(searchCoverage.general_web_discovery.allowance_left_credits)}` : ''}.</p>
            {(searchCoverage.general_web_discovery.queries_planned || []).map((query, index) => <small key={`${query}-${index}`}>Query {index + 1}: {query}</small>)}
            {(searchCoverage.general_web_discovery.hits || []).slice(0, 10).map((hit, index) => <small key={`${String(hit.url || 'lead')}-${index}`}>
              Search lead {Number(hit.rank || index + 1)} · {String(hit.domain || 'domain unavailable')} · <a href={String(hit.url || '#')} target="_blank" rel="noreferrer">{String(hit.title || 'Untitled result')}</a> · unverified discovery lead; snippet is not evidence.
            </small>)}
            {(searchCoverage.general_web_discovery.newly_discovered_organizations || []).map((organization, index) => <small key={`${String(organization.organization_id || 'organization')}-${index}`}>
              Newly discovered: {String(organization.canonical_name || 'Name unavailable')} · {String(organization.official_domain || 'domain unavailable')} · {String(organization.identity_status || 'identity not verified').replace(/_/g, ' ')} · {String(organization.verification_method || 'verification method not recorded').replace(/_/g, ' ')} · identity evidence only; quality not assessed.
            </small>)}
            {searchCoverage.general_web_discovery.official_publication_search && <small>
              Official-site publication catalog: {String(searchCoverage.general_web_discovery.official_publication_search.organization_name || 'not selected')} · {String(searchCoverage.general_web_discovery.official_publication_search.status || 'not attempted').replace(/_/g, ' ')} · {Number(searchCoverage.general_web_discovery.official_publication_search.returned_count || 0)} metadata record(s) · content retrieved: {Boolean(searchCoverage.general_web_discovery.official_publication_search.content_fetched) ? 'yes' : 'no'} · rights: {String(searchCoverage.general_web_discovery.official_publication_search.rights_status || 'not assessed').replace(/_/g, ' ')}.
            </small>}
            <small>Search snippets are not citations or scientific evidence. Official-site reports enter the normal source workflow as metadata-only until content rights and retrieval are separately resolved.</small>
          </div>}
          {searchCoverage.organization_discovery?.schema_version === 1 && <div className="audit-detail-item">
            <b>Dynamic organization discovery · {String(searchCoverage.organization_discovery.status || 'unknown').replace(/_/g, ' ')} · {Number(searchCoverage.organization_discovery.identity_requests_attempted || 0) + Number(searchCoverage.organization_discovery.domain_identity_requests_attempted || 0)} ROR lookups</b>
            <p>{Number(searchCoverage.organization_discovery.organizations?.length || 0)} organizations surfaced through public-web publication leads, scholarly affiliations, and indexed organization records. Web-discovered domains can proceed to bounded official-site publication search after an exact ROR match or a DOI/title/publisher match whose Crossref full-text link names the same domain. These checks establish identity or publication linkage only; catalog metadata, content rights, and methodological quality remain separate.</p>
            {(searchCoverage.organization_discovery.organizations || []).map((organization, index) => <div className="audit-detail-item" key={String(organization.organization_id || 'organization') + '-' + index}>
              <b>{String(organization.canonical_name || 'Name unavailable')} · {String(organization.identity_status || 'identity not verified').replace(/_/g, ' ')}</b>
              <p>{(organization.organization_types || []).join(', ') || 'Organization type unavailable'}{organization.country_code ? ' · ' + organization.country_code : ''} · {organization.registry_match ? 'known in curated registry' : 'new to curated registry'}.</p>
              <small>Official domains: {(organization.official_domains || []).join(', ') || 'none verified'} · Identity method: {String(organization.verification_method || 'not recorded').replace(/_/g, ' ')} · Verified {organization.verification_timestamp ? new Date(organization.verification_timestamp).toLocaleString() : 'time not recorded'}{organization.source_record_updated_at ? ` · ROR record updated ${organization.source_record_updated_at}` : ''} · Publication quality: not assessed.</small>
              {organization.verification_source && <small><a href={organization.verification_source} target="_blank" rel="noreferrer">Open identity evidence<ExternalLink size={12} /></a></small>}
              {organization.limitations?.map((limitation, limitationIndex) => <small key={String(organization.organization_id) + '-limitation-' + limitationIndex}>{limitation}</small>)}
            </div>)}
            {(searchCoverage.organization_discovery.publication_searches || []).map((search, index) => <div className="audit-detail-item" key={String(search.organization_id || 'search') + '-' + index}>
              <b>{String(search.organization_name || 'Institution-filtered publication search')} · {String(search.status || 'unknown').replace(/_/g, ' ')}</b>
              <p>{Number(search.returned_count || 0)} records from {String(search.provider || 'provider unavailable')}{search.filter ? ' · ' + search.filter : ''}{search.error_code ? ' · ' + search.error_code : ''}{search.request_count !== undefined ? ` · ${search.request_count} bounded request(s)` : ''}{search.rights_status ? ` · content rights ${search.rights_status.replace(/_/g, ' ')}` : ''}{search.content_fetched === false ? ' · content not fetched' : ''}.</p>
              {(search.publications || []).map((publication, publicationIndex) => <small key={String(publication.canonical_identity || publication.title || 'publication') + '-' + publicationIndex}>{String(publication.title || 'Untitled record')}{publication.publication_year ? ' · ' + publication.publication_year : ''}{publication.doi ? ' · DOI ' + publication.doi : ''}</small>)}
            </div>)}
            <div className="audit-detail-item">
              <b>Organization-discovered publications selected into this report ({(searchCoverage.organization_discovery.selected_publications || []).length})</b>
              {(searchCoverage.organization_discovery.selected_publications || []).map((publication, index) => {
                const source = sources.find((item) => item.id === publication.source_id);
                return <div key={`${String(publication.source_id || 'source')}-${index}`}>
                  {source
                    ? <button type="button" className="citation-link" aria-label={`Inspect organization-discovered publication ${source.title}`} onClick={() => onSelectSource(source)}>{source.title}</button>
                    : <small>{String(publication.title || 'Selected publication')} · source record unavailable</small>}
                  <small>{publication.organization_name || 'Organization identity unavailable'} · {String(publication.identity_status || 'identity not verified').replace(/_/g, ' ')}{publication.doi ? ` · DOI ${publication.doi}` : ''} · publication quality not assessed</small>
                </div>;
              })}
            </div>
            <small>{String(searchCoverage.organization_discovery.interpretation_limit || 'Identity verification does not establish research quality.')}</small>
          </div>}
          {searchLensCounts && <div className="audit-detail-item"><b>Search lenses: {Number(searchLensCounts.completed || 0)} complete · {Number(searchLensCounts.partial || 0)} partial · {Number(searchLensCounts.failed || 0)} failed · {Number(searchLensCounts.not_attempted || 0)} not attempted</b></div>}
          {searchLenses.map((lens, index) => <div className="audit-detail-item" key={`${String(lens.lens_id || 'lens')}-${index}`}>
            <b>{String(lens.lens_id || `Lens ${index + 1}`)} · {String(lens.category || 'category unavailable').replace(/_/g, ' ')} · {String(lens.status || 'status unavailable').replace(/_/g, ' ')}</b>
            <p><strong>Purpose:</strong> {String(lens.purpose || 'Not recorded')}<br /><strong>Query:</strong> {String(lens.exact_query || 'Not recorded')}</p>
            <small>{Number(lens.candidate_keys?.length || 0)} candidate records · {Number(lens.selected_candidate_keys?.length || 0)} selected from this lens{lens.pagination_state ? ` · ${String(lens.pagination_state).replace(/_/g, ' ')}` : ''}</small>
            {(lens.providers || []).map((provider, providerIndex) => <small key={`${String(provider.provider || 'provider')}-${providerIndex}`}>{String(provider.provider || 'Provider')}: {String(provider.status || 'unknown')}{provider.status === 'completed' ? ` · ${Number(provider.results || 0)} records` : ''}{provider.error_code ? ` · ${String(provider.error_code).replace(/_/g, ' ')}` : ''}</small>)}
          </div>)}
          {Object.keys(exclusionCounts).length > 0 && <div className="audit-detail-item"><b>Candidate exclusions</b><p>{Object.entries(exclusionCounts).map(([reason, count]) => `${reason.replace(/_/g, ' ')}: ${count}`).join(' · ')}</p><small>{Number(searchCoverage.records_excluded_by_source_cap || 0)} excluded by source capacity; {Number(searchCoverage.duplicate_records_excluded || 0)} duplicate records.</small></div>}
          {citationExpansion && <div className="audit-detail-item">
            <b>Citation expansion · {String(citationExpansion.status || searchCoverage.citation_expansion_status || 'not recorded').replace(/_/g, ' ')}</b>
            <p>{Number(citationExpansion.requests_attempted || 0)} bounded metadata requests · {citationExpansion.seed_work_ids?.length || 0} seed studies · {Number(citationExpansion.omitted_backward_count || 0)} backward references omitted from the sample.</p>
            {citationExpansion.sampling_note && <small>{citationExpansion.sampling_note}</small>}
            <small>Reported cost: {citationExpansion.reported_cost_status === 'provider_reported_complete' ? `$${Number(citationExpansion.reported_cost_usd || 0).toFixed(4)} (provider reported)` : String(citationExpansion.reported_cost_status || 'unknown').replace(/_/g, ' ')}.</small>
            {(citationExpansion.errors || []).map((error, index) => <small key={`${String(error.stage || 'error')}-${index}`}>Expansion {String(error.stage || 'stage')}: {String(error.error_code || 'error')}{error.retry_after_seconds != null ? ` · retry-after ${error.retry_after_seconds}s` : ''}</small>)}
          </div>}
        </> : <div className="audit-detail-item"><p>Scholarly search coverage was not recorded for this historical report.</p></div>}
      </details>
      <details className="audit-detail" open>
        <summary>Official statistics routing</summary>
        {routeRows.length > 0 ? routeRows.map(({ label, outcome }) => {
          const reason = outcome.reason_code ? String(outcome.reason_code).replace(/_/g, ' ') : null;
          const detail = outcome.status === 'searched'
            ? `searched · ${Number(outcome.results || 0)} records returned · ${Number(outcome.failures || 0)} request failures`
            : `${String(outcome.status || 'status unavailable').replace(/_/g, ' ')}${reason ? ` · ${reason}` : ''}`;
          return <div className="audit-detail-item" key={label}><b>{label} · {detail}</b></div>;
        }) : <div className="audit-detail-item"><p>Routing was not recorded for this historical report.</p></div>}
      </details>
      {claimUnits.length > 0 && <details className="audit-detail claim-unit-manifest"><summary>Source claim units ({claimUnits.length})</summary><p className="drawer-footnote">Exact source substrings and Unicode codepoint spans. Segmentation is not a truth or support judgment.</p>{claimUnits.map((unit, index) => { const id = String(unit.claim_id || ''); const claim = claimById.get(id); const economics = unit.economic_facets && typeof unit.economic_facets === 'object' ? unit.economic_facets as Record<string, unknown> : null; const rawFacets = economics?.facets && typeof economics.facets === 'object' ? Object.entries(economics.facets as Record<string, unknown>) : []; return <div className="audit-detail-item" key={`${id}-${index}`}><b>{String(unit.atomization_status || 'legacy')} · claim unit</b><p>{String(unit.text || '')}</p><small>Source span [{String(unit.span_start ?? '?')}, {String(unit.span_end ?? '?')})</small>{rawFacets.length > 0 && <small>Economic facets ({String(economics?.status || 'not assessed').replace(/_/g, ' ')}): {rawFacets.map(([name, raw]) => { const facet = raw && typeof raw === 'object' ? raw as Record<string, unknown> : {}; return `${name.replace(/_/g, ' ')}: ${String(facet.value || 'unknown')}`; }).join(' · ')}</small>}{claim && <button className="text-button" onClick={() => onSelectClaim(claim)}>Inspect exact source span <ArrowRight size={13} /></button>}</div>; })}</details>}
      {decisionImplications.length > 0 && <section className="decision-inspector"><p className="eyebrow">CONDITIONAL IMPLICATIONS</p><p className="drawer-footnote">Provisional model interpretations. Inspect cited passages and assumptions before use.</p>{decisionImplications.map((item, index) => <div className="decision-inspector-item" key={`${String(item.action)}-${index}`}><b>{String(item.action || 'implication').replace(/_/g, ' ')}</b><p><strong>Condition</strong> {String(item.condition || '')}</p><p><strong>Rationale</strong> {String(item.rationale || '')}</p>{Array.isArray(item.assumptions) && item.assumptions.length > 0 && <p><strong>Assumptions</strong> {item.assumptions.map(String).join('; ')}</p>}{Array.isArray(item.unknowns) && item.unknowns.length > 0 && <p><strong>Unknowns</strong> {item.unknowns.map(String).join('; ')}</p>}<div className="decision-citations">{(Array.isArray(item.citations) ? item.citations : []).map((citation) => { const key = String(citation); const sourceId = report.citation_map[key]?.source_id; const source = sources.find((candidate) => candidate.id === sourceId); return source ? <button className="citation-link" key={key} onClick={() => onSelectSource(source)}>{key}</button> : null; })}</div></div>)}</section>}
      <div className="audit-warning"><ShieldCheck size={15} /><span>This is an evidence map, not a validated scientific conclusion. Read source excerpts and methods before making a consequential decision.</span></div>
      <div className="audit-meta"><span>Sources in report</span><b>{Object.keys(report.citation_map).length}</b></div><div className="audit-meta"><span>Model synthesis</span><b>{report.model_name || 'Not run'}</b></div>
    </aside>
  </div>;
}

function RetrievalPolicyDetails({ retrieval }: { retrieval: NonNullable<Source['retrieval']> }) {
  return <>
    {retrieval.govuk_content && <>
      <div><span>GOV.UK publication page</span><b>{retrieval.govuk_content.status?.replace(/_/g, ' ') || 'Not recorded'} · {retrieval.govuk_content.passage_count ?? 0} exact passages</b></div>
      {retrieval.govuk_content.publication_url && <div><span>Publisher page</span><a href={retrieval.govuk_content.publication_url} target="_blank" rel="noreferrer">Open GOV.UK publication<ExternalLink size={12} /></a></div>}
      {retrieval.govuk_content.api_url && <div><span>Content API record</span><a href={retrieval.govuk_content.api_url} target="_blank" rel="noreferrer">Open API record<ExternalLink size={12} /></a></div>}
      {retrieval.govuk_content.license_url && <div><span>Reuse basis</span><a href={retrieval.govuk_content.license_url} target="_blank" rel="noreferrer">{retrieval.govuk_content.license_code || 'Reported GOV.UK default OGL'}<ExternalLink size={12} /></a></div>}
      <div><span>Page-body limits</span><b>Default OGL basis, not item-specific verification; linked attachments fetched: {retrieval.govuk_content.attachments_fetched ? 'yes' : 'no'}</b></div>
      {retrieval.govuk_content.rights_limit && <small className="drawer-footnote">{retrieval.govuk_content.rights_limit}</small>}
      {retrieval.govuk_content.document_sha256 && <div><span>Page-body SHA-256</span><b>{retrieval.govuk_content.document_sha256.slice(0, 20)}…</b></div>}
    </>}
    {retrieval.license && <div><span>Reported license</span><b>{retrieval.license}</b></div>}
    {retrieval.license_evidence && <div><span>License evidence</span><b>{retrieval.license_evidence}</b></div>}
    {retrieval.rights_decision && <div><span>Content rights decision</span><b>{retrieval.rights_decision.replace(/_/g, ' ')}</b></div>}
    {retrieval.rights_basis && <div><span>Rights basis</span><b>{retrieval.rights_basis}</b></div>}
    {retrieval.official_page_content && <div><span>Official page extraction</span><b>{retrieval.official_page_content.status || 'Not recorded'}{retrieval.official_page_content.reason_code ? ` · ${retrieval.official_page_content.reason_code.replace(/_/g, ' ')}` : ''} · rights {retrieval.official_page_content.rights_status || 'not assessed'} · retained {retrieval.official_page_content.content_retained ? 'yes' : 'no'}</b></div>}
    {retrieval.openaire_resolution && <div className="institutional-publication-details">
      <span>OpenAIRE repository resolution</span>
      <b>{(retrieval.openaire_resolution.status || 'unknown').replace(/_/g, ' ')}{retrieval.openaire_resolution.repository_name ? ` · ${retrieval.openaire_resolution.repository_name}` : ''}</b>
      {retrieval.openaire_resolution.matched_doi && <small>Exact DOI/title match: {retrieval.openaire_resolution.matched_doi} · {retrieval.openaire_resolution.license_code || 'license not recorded'}</small>}
      {retrieval.openaire_resolution.repository_url && <small><a href={retrieval.openaire_resolution.repository_url} target="_blank" rel="noreferrer">Open repository record<ExternalLink size={12} /></a></small>}
      {retrieval.openaire_resolution.selected_url && <small><a href={retrieval.openaire_resolution.selected_url} target="_blank" rel="noreferrer">Open selected repository PDF<ExternalLink size={12} /></a></small>}
      {retrieval.openaire_resolution.error_code && <small>Lookup issue: {retrieval.openaire_resolution.error_code.replace(/_/g, ' ')}</small>}
      {retrieval.openaire_resolution.reason && <small>{retrieval.openaire_resolution.reason.replace(/_/g, ' ')}</small>}
    </div>}
    {retrieval.site_policy_status && <div><span>Host policy</span><b>{retrieval.site_policy_status.replace(/_/g, ' ')}</b></div>}
    {retrieval.host_policy_id && <div><span>Terms review record</span><b>{retrieval.host_policy_id}</b></div>}
    {retrieval.host_terms_url && <div><span>Reviewed host terms</span><a href={retrieval.host_terms_url} target="_blank" rel="noreferrer">Open terms<ExternalLink size={12} /></a></div>}
    {retrieval.robots_status && <div><span>Robots result</span><b>{retrieval.robots_status.replace(/_/g, ' ')}</b></div>}
    {Object.entries(retrieval.deferred_retries || {}).map(([kind, retry]) => retry && <div key={kind}><span>{kind.toUpperCase()} deferred retry</span><b>{retry.status || 'unknown'}{retry.due_at ? ` · due ${new Date(retry.due_at).toLocaleString()}` : ''}</b></div>)}
    {retrieval.pdf && <div><span>PDF retrieval gate</span><b>{retrieval.pdf.error_code || retrieval.pdf.robots_status || retrieval.pdf.status || 'Not attempted'}</b></div>}
    {retrieval.grobid && <div><span>GROBID parser</span><b>{retrieval.grobid.status || 'Not recorded'}{retrieval.grobid.parser_version ? ` · ${retrieval.grobid.parser_version}` : ''}{retrieval.grobid.error_code ? ` · ${retrieval.grobid.error_code}` : ''}</b></div>}
    {retrieval.jats && <><div><span>Europe PMC full-text status</span><b>{retrieval.jats.status || 'Not recorded'}{retrieval.jats.reason ? ` · ${retrieval.jats.reason.replace(/_/g, ' ')}` : ''}</b></div>{retrieval.jats.pmcid && <div><span>PMC article</span><b>{retrieval.jats.pmcid}</b></div>}<div><span>Article rights decision</span><b>{retrieval.jats.rights_decision || 'Not assessed'}</b></div>{retrieval.jats.raw_license && <div><span>Article license</span><b>{retrieval.jats.raw_license}</b></div>}{retrieval.jats.retrieved_at && <div><span>JATS retrieved</span><b>{new Date(retrieval.jats.retrieved_at).toLocaleString()}</b></div>}</>}
    {retrieval.structured_document && <div><span>Structured extraction</span><b>{retrieval.structured_document.parser_name || 'Parser'} {retrieval.structured_document.parser_version || ''} · {retrieval.structured_document.sections_count || 0} sections · {retrieval.structured_document.passages_count || 0} passages · {retrieval.structured_document.extraction_status || 'unknown'} · Methods/Results {retrieval.structured_document.methods_results_usable ? 'available' : 'not established'}</b></div>}
    {!!retrieval.structured_document?.sections?.length && <details className="audit-detail"><summary>Extracted section headings ({retrieval.structured_document.sections.length}{retrieval.structured_document.section_metadata_truncated ? '+' : ''})</summary>{retrieval.structured_document.sections.map((section) => <p key={section.section_id}><b>{section.normalized_type.replace(/_/g, ' ')}</b>: {section.original_heading || 'Heading not reported'}{section.section_path.length ? ` · ${section.section_path.join(' / ')}` : ''}<small>{section.source_locator}</small></p>)}{retrieval.structured_document.section_metadata_truncated && <small>Additional section metadata was omitted at the storage bound.</small>}</details>}
  </>;
}

function OpenAlexFullTextAvailability({ availability }: { availability: Source['openalex_fulltext_availability'] }) {
  if (!availability) return null;
  const formats = [
    availability.pdf === true ? 'PDF available' : availability.pdf === false ? 'PDF not available' : 'PDF status not reported',
    availability.grobid_xml === true ? 'GROBID TEI available' : availability.grobid_xml === false ? 'GROBID TEI not available' : 'GROBID TEI status not reported',
  ];
  return <><div><span>OpenAlex archived formats</span><b>{formats.join(' · ')}</b></div><div className="openalex-availability-note">Availability metadata only. Veda has not downloaded these files. Availability does not grant reuse rights; OpenAlex content downloads may be metered.</div></>;
}

function SourceDrawer({ source, onClose }: { source: Source; onClose: () => void }) {
  const drawerRef = useRef<HTMLElement>(null);
  useDrawerFocus(drawerRef, onClose);
  const appraisal = source.source_type === 'official_statistics' ? 'Not applicable: descriptive series, not a study' : source.appraisal?.status === 'model_assessed_not_independently_verified' ? 'Model-assisted; not independently verified' : 'Not performed';
  const retrieval = source.retrieval || {};
  const documentHash = retrieval.document_sha256;
  const accessDescription = source.retrieval_status === 'full_text_html'
    ? 'Bounded excerpts from HTML retrieved under a reported license assertion and reviewed host policy; the raw document is not retained.'
    : source.retrieval_status === 'full_text_pdf'
      ? retrieval.structured_document?.parser_name === 'grobid'
        ? 'Section-aware TEI passages parsed from a PDF under a reported license assertion and reviewed host policy; the original PDF and returned TEI are not retained, and OCR is not performed.'
        : 'Bounded embedded-text passages from a PDF retrieved under a reported license assertion and reviewed host policy; the raw document is not retained and OCR is not performed.'
      : source.retrieval_status === 'full_text_jats'
        ? 'Section-aware passages parsed from Europe PMC JATS XML after matching the article identity and permitting reuse under the reported license. Raw XML is not retained.'
      : source.retrieval_status === 'official_publication_page_body'
        ? 'Exact excerpts from the official GOV.UK publication page body. This is not the linked report attachment; the Content API exposes no item-specific licence field, so the default OGL basis and its exceptions remain a limitation.'
      : source.retrieval_status === 'abstract_only'
      ? 'Short abstract excerpt from scholarly metadata.'
      : source.source_type === 'official_statistics'
        ? 'Official descriptive indicator observations; not causal evidence. See the dataset rights basis and source notes.'
        : source.source_type === 'institutional_report'
          ? 'Official institutional publication metadata only. Linked full text was not retrieved and reuse rights were not assessed.'
          : 'Bibliographic metadata only.';
  return <div className="drawer-scrim" onClick={onClose}><aside ref={drawerRef} tabIndex={-1} role="dialog" aria-modal="true" aria-labelledby="source-inspector-title" className="evidence-drawer" onClick={(e) => e.stopPropagation()}><div className="drawer-top"><span className="eyebrow">SOURCE INSPECTOR</span><button className="icon-button" onClick={onClose} aria-label="Close source inspector"><X size={17} /></button></div><div className="drawer-label-row"><span className="source-number">SOURCE</span><span className={`access-badge ${source.retrieval_status}`}>{sourceAccessLabel(source.retrieval_status)}</span></div><h2 id="source-inspector-title">{source.title}</h2><p className="drawer-authors">{source.authors.map(authorLabel).join(', ') || 'Author metadata not available'}{source.published_year ? ` · ${source.published_year}` : ''}</p><div className="drawer-divider" /><h3>Source details</h3><div className="detail-list"><RetrievalPolicyDetails retrieval={retrieval} />{source.doi && <div><span>DOI</span><a href={`https://doi.org/${source.doi}`} target="_blank" rel="noreferrer">{source.doi}<ExternalLink size={12} /></a></div>}<div><span>Publisher</span><b>{source.publisher || 'Not listed'}</b></div><div><span>Evidence access class</span><b>{accessDescription}</b></div><OpenAlexFullTextAvailability availability={source.openalex_fulltext_availability} />{source.institutional_publication && <div className="institutional-publication-details"><span>Official repository record</span><b>{source.institutional_publication.document_type || "World Bank publication"}{source.institutional_publication.report_number ? ` · ${source.institutional_publication.report_number}` : ""} · record {source.institutional_publication.publisher_record_id}</b><small>Retrieved from the public World Bank Documents &amp; Reports API. Full text was not fetched; download and reuse rights have not been assessed.</small></div>}{source.official_publication && <div className="institutional-publication-details"><span>Official publication metadata</span><b>{source.official_publication.document_type.replace(/_/g, " ")} · GOV.UK {source.official_publication.record_path}</b><small>Organizations: {source.official_publication.publishing_organizations.join("; ") || "not listed"}. Search API metadata; a separate Content API page body is shown above when available. The linked report attachment was not fetched, and page-body reuse follows the reported default OGL basis with item-specific exceptions unverified.</small>{source.official_publication.publishing_organization_records.map((organization) => <small key={organization.organization_id}>{organization.canonical_name} · {organization.identity_status.replace(/_/g, " ")} · publisher identity only; quality not assessed. <a href={organization.official_url} target="_blank" rel="noreferrer">Official directory<ExternalLink size={12} /></a></small>)}</div>}{source.official_site_publication && <div className="institutional-publication-details"><span>Official-site publication metadata</span><b>{source.official_site_publication.organization_name} · {source.official_site_publication.result_subtype.replace(/-/g, " ")} #{source.official_site_publication.wordpress_record_id}</b><small>Organization identity: {source.official_site_publication.identity_status.replace(/_/g, " ")} · publication link check: {source.official_site_publication.publisher_verification.replace(/_/g, " ")} · catalog query: {source.official_site_publication.discovery_query} · content was not fetched · content rights and research quality are not assessed.</small><small><a href={source.official_site_publication.api_url} target="_blank" rel="noreferrer">Official catalog record API<ExternalLink size={12} /></a> · <a href={source.official_site_publication.homepage_url} target="_blank" rel="noreferrer">Verified publisher homepage<ExternalLink size={12} /></a></small></div>}{source.abstract_text_available_at_discovery != null && <div><span>Provider abstract at discovery</span><b>{source.abstract_text_available_at_discovery ? 'Available; not retained' : 'Not available'}</b></div>}{source.abstract_text_retention_status && <div><span>Abstract text retention</span><b>{abstractTextRetentionLabel(source.abstract_text_retention_status)}</b></div>}{Object.entries(retrieval.outcomes?.by_format || {}).map(([format, outcome]) => outcome ? <div key={format}><span>{format.toUpperCase()} retrieval outcome</span><b>{retrievalOutcomeLabel(outcome.outcome)}{outcome.reason_code ? ` · ${outcome.reason_code.replace(/_/g, ' ')}` : ''}{outcome.error_code ? ` · ${outcome.error_code}` : ''}{outcome.retry_after_seconds !== undefined ? ` · retry after ${outcome.retry_after_seconds}s` : ''}</b></div> : null)}{retrieval.version && <div><span>Version</span><b>{retrieval.version}</b></div>}{retrieval.retrieved_at && <div><span>Retrieved</span><b>{new Date(retrieval.retrieved_at).toLocaleString()}</b></div>}{retrieval.final_host && <div><span>Fetched host</span><b>{retrieval.final_host}</b></div>}{typeof retrieval.page_count === 'number' && <div><span>PDF pages</span><b>{retrieval.pages_extracted || 0} extracted / {retrieval.page_count}{retrieval.truncated ? " · capped" : ""}</b></div>}{documentHash && <div><span>Document SHA-256</span><b>{documentHash.slice(0, 20)}…</b></div>}{retrieval.error_code && <div><span>Retrieval result</span><b>{retrieval.error_code}</b></div>}<div><span>Method review</span><b>{appraisal}</b></div></div><OrganizationDiscoveryPanel organization={source.organization_provenance} /><SourceGovernancePanel governance={source.source_governance} /><SourceMethodologyPanel appraisal={source.appraisal} passages={source.passages || []} />{source.abstract_excerpt && <><div className="drawer-divider" /><h3>Retrieved abstract excerpt</h3><blockquote className="source-excerpt">“{source.abstract_excerpt}{source.abstract_excerpt.length >= 560 ? '…' : ''}”</blockquote><p className="drawer-footnote">This bounded excerpt came from scholarly metadata. Individual sentences may be linked as source-reported statements.</p></>}{source.statistics && <OfficialStatisticsCard statistics={source.statistics} />}{source.passages?.length ? <><div className="drawer-divider" /><h3>Passages in evidence ledger</h3><div className="passage-stack">{source.passages.map((passage) => <div id={`source-passage-${encodeURIComponent(passage.id)}`} key={passage.id} className="passage-chip"><span>{passage.locator} · {passage.access_level.replace(/_/g, ' ')}</span>{passage.document && <small>Snapshot v{passage.document.schema_version} · {passage.document.source_version} · SHA-256 {passage.document.document_sha256.slice(0, 16)}… · {new Date(passage.document.retrieved_at).toLocaleString()}</small>}{passage.content_withheld_reason ? <p className="audit-warning" role="status">{passage.content}</p> : <p>{passage.content}{passage.truncated ? '…' : ''}</p>}</div>)}</div></> : null}<div className="drawer-bottom">{source.url && <a className="primary-button" href={source.url} target="_blank" rel="noreferrer">Open source <ExternalLink size={14} /></a>}<span>Source metadata from {source.provider}</span></div></aside></div>;
}

function appraisalStatusLabel(status: string) {
  return status.replace(/_/g, ' ');
}

function SourceMethodologyPanel({ appraisal, passages }: { appraisal: Source['appraisal']; passages: Passage[] }) {
  const passageById = new Map(passages.map((passage) => [passage.id, passage]));
  const labels: Record<string, string> = {
    design_type: 'Study design', population: 'Population', geography: 'Geography',
    time_period: 'Time period', sample: 'Sample', identification_strategy: 'Identification strategy',
    intervention_or_exposure: 'Intervention or exposure', comparator: 'Comparator',
    outcomes: 'Outcomes', measure: 'Measure', effect_size_and_uncertainty: 'Effect size and uncertainty',
    limitations: 'Limitations', funding_or_conflicts: 'Funding or conflicts',
    missingness: 'Missingness', external_validity: 'External validity',
  };
  const fields = Object.entries(appraisal.fields || {});
  return <><div className="drawer-divider" /><h3>Methodological appraisal</h3><p className="drawer-footnote">{appraisalStatusLabel(appraisal.status || 'not_assessed')}{appraisal.provider ? ` · ${appraisal.provider}${appraisal.model ? `/${appraisal.model}` : ''}` : ''}. Model judgments are advisory and have not been independently verified.</p>{appraisal.reason && <p className="drawer-footnote">{appraisal.reason}</p>}{fields.length ? <div className="appraisal-fields">{fields.map(([name, field]) => {
    const linkedPassages = (field.passage_ids || []).map((id) => passageById.get(id)).filter((item): item is Passage => !!item);
    return <article className="appraisal-field" key={name}><div className="appraisal-field-heading"><b>{labels[name] || name.replace(/_/g, ' ')}</b><small>{appraisalStatusLabel(field.status)}</small></div><p>{field.value || 'Unknown'}</p><div className="appraisal-passage-links">{linkedPassages.map((passage) => <a className="appraisal-passage-link" key={passage.id} href={`#source-passage-${encodeURIComponent(passage.id)}`} aria-label={`View linked passage ${passage.locator}`}>{passage.locator}</a>)}{!linkedPassages.length && <small>{field.passage_ids?.length ? 'Linked passage unavailable in this source snapshot.' : 'No passage linked.'}</small>}</div></article>;
  })}</div> : <p className="drawer-footnote">No field-level methodological appraisal is available.</p>}</>;
}

function SourceGovernancePanel({ governance }: { governance: Source['source_governance'] }) {
  if (!governance) return null;
  const academicRecords = [
    ...governance.matched_institution_rankings.map((item) => `${item.system} ${item.ranking_year}: rank ${item.rank} (${item.subject_category})`),
    ...governance.matched_journal_classifications.map((item) => `${item.classification} · ${item.system} ${item.ranking_year} · ISSN ${item.issn}${item.subject_category ? ` · ${item.subject_category}` : ''}`),
  ];
  return <><div className="drawer-divider" /><h3>Source identity and registry</h3><div className="detail-list"><div><span>Source class</span><b>{governance.source_classes.map((item) => item.replace(/_/g, ' ').replace(/\b\w/g, (letter) => letter.toUpperCase())).join(', ') || 'Unclassified'}</b></div><div><span>Identity</span><b>{governance.identity_status}{governance.matched_registry_ids.length ? ` · ${governance.matched_registry_ids.join(', ')}` : ''}</b></div><div><span>Registry version</span><b>{governance.registry_version}</b></div><div><span>Academic preference</span><b>{governance.academic_preference === 'NONE' ? 'No verified ranking/list match' : governance.academic_preference}</b></div>{academicRecords.map((item) => <div key={item}><span>Verified classification</span><b>{item}</b></div>)}{governance.matched_identity_provenance.map((item,index) => <div key={index}><span>Identity provenance · {item.registry_id} · {item.verified_at}</span><a href={item.source_url}>Open registry evidence</a></div>)}{governance.matched_institution_identifiers.map((item,index) => <div key={index}><span>Institution identifier · {item.registry_id}</span><b>{item.namespace}: {item.identifier}</b></div>)}{(governance.matched_organization_identifiers || []).map((item,index) => <div key={index}><span>Organization identifier · {item.registry_id}</span><b>{item.namespace}: {item.identifier}</b></div>)}<div><span>Discovery adapter</span><b>{governance.discovery_status.replace(/_/g, ' ')}</b></div><div><span>Institutional quality review</span><b>{governance.quality_review_status}</b></div><div><span>Document methodology</span><b>Not assessed by source identity; document-level review required</b></div></div><p className="drawer-footnote">Institutional identity, ranking, or list membership is not evidence that this publication is relevant, methodologically sound, or true. Selection still requires question relevance and document-level appraisal.</p></>;
}

function OrganizationDiscoveryPanel({ organization }: { organization: Source['organization_provenance'] }) {
  if (!organization) return null;
  const crossrefLinkedDomainOnly = /crossref.*linked.*domain/i.test(organization.verification_method);
  const publisherLinkedDomain = organization.publisher_linked_domain ||
    (crossrefLinkedDomainOnly ? organization.official_domain : undefined);
  return <><div className="drawer-divider" /><h3>Organization discovery provenance</h3><div className="detail-list">
    <div><span>Organization</span><b>{organization.organization_name}</b></div>
    <div><span>Identity status</span><b>{organization.identity_status.replace(/_/g, ' ')}</b></div>
    <div><span>Identity method</span><b>{organization.verification_method.replace(/_/g, ' ')}</b></div>
    {!crossrefLinkedDomainOnly && organization.official_domain && <div><span>Verified official domain</span><b>{organization.official_domain}</b></div>}
    {publisherLinkedDomain && <div><span>Publisher-linked domain · official site not independently verified</span><b>{publisherLinkedDomain}</b></div>}
    {organization.publisher_verification && <div><span>Publication publisher check</span><b>{organization.publisher_verification.replace(/_/g, ' ')}</b></div>}
    {organization.official_publication_url && <div><span>Publication link</span><a href={organization.official_publication_url} target="_blank" rel="noreferrer">Open publication link<ExternalLink size={12} /></a></div>}
    {organization.publication_discovery_provider && <div><span>Publication discovery and verification</span><b>{organization.publication_discovery_provider}</b></div>}
    {organization.publication_content_access && <div><span>Publication content</span><b>{organization.publication_content_access.replace(/_/g, ' ')}</b></div>}
    {organization.publication_rights_status && <div><span>Publication rights</span><b>{organization.publication_rights_status.replace(/_/g, ' ')}</b></div>}
    {organization.openalex_institution_id && <div><span>OpenAlex institution</span><b>{organization.openalex_institution_id}</b></div>}
    {organization.verification_source && <div><span>Identity evidence</span><a href={organization.verification_source} target="_blank" rel="noreferrer">Open verification record <ExternalLink size={12} /></a></div>}
    <div><span>Publication quality</span><b>Not assessed by organization identity</b></div>
  </div><p className="drawer-footnote">Identity evidence supports the listed organization/domain or publisher-publication relationship only. It does not establish the publication’s relevance, methodology, conclusions, or reuse rights.</p></>;
}

function ClaimMethodologyPanel({ appraisal, passages }: { appraisal: Claim['appraisal']['methodology_appraisal']; passages: Passage[] }) {
  if (!appraisal) return null;
  const passageById = new Map(passages.map((passage) => [passage.id, passage]));
  const linkedPassages = appraisal.passage_ids.map((id) => passageById.get(id)).filter((item): item is Passage => !!item);
  return <><div className="drawer-divider" /><h3>Methodological relationship</h3><p className="drawer-footnote"><b>{appraisal.relationship}</b> · {appraisalStatusLabel(appraisal.status)}{appraisal.provider ? ` · ${appraisal.provider}${appraisal.model ? `/${appraisal.model}` : ''}` : ''}. This is a model-assisted interpretation, not an independent validation.</p><p className="methodology-rationale">{appraisal.rationale || 'No rationale was recorded.'}</p>{linkedPassages.length > 0 ? <div className="methodology-passages">{linkedPassages.map((passage) => <article className="methodology-passage" key={passage.id}><span>{passage.locator}</span><p>“{passage.content}”</p></article>)}</div> : <p className="drawer-footnote">{appraisal.passage_ids.length ? 'The stored passage references could not be resolved to this source.' : 'No passage was linked to this assessment.'}</p>}</>;
}

function OfficialStatisticsCard({ statistics }: { statistics: NonNullable<Source['statistics']> }) {
  return <><div className="drawer-divider" /><h3>Official statistical series</h3><p className="drawer-footnote">Descriptive time-series observations are not study estimates or causal evidence.</p><div className="detail-list"><div><span>Indicator</span><b>{statistics.indicator_name} · {statistics.indicator_id}</b></div><div><span>Database</span><b>{statistics.dataset_name}</b></div><div><span>Geography and period</span><b>{statistics.observations.map((item) => `${item.geography_name} · ${item.period}`).join(', ') || 'Not available'}</b></div><div><span>Measurement unit (metadata)</span><b>{statistics.measurement_unit || 'Not supplied'}</b></div><div><span>Observation unit codes</span><b>{statistics.observations.map((item) => [item.unit_measure, item.unit_type, item.unit_multiplier !== null ? `multiplier ${item.unit_multiplier}` : null].filter(Boolean).join(' / ') || 'Not supplied').join(', ')}</b></div><div><span>Reuse license</span><b>{statistics.license || 'Not verified'}</b></div><div><span>Attribution</span><b>{statistics.attribution}</b></div><div><span>Periodicity</span><b>{statistics.periodicity || "Not supplied"}</b></div><div><span>Metadata updated</span><b>{statistics.source_update_date || "Not supplied"}</b></div><div><span>Retrieved</span><b>{new Date(statistics.retrieved_at).toLocaleString()}</b></div></div>{statistics.definition && <p className="drawer-footnote"><b>Definition.</b> {statistics.definition}</p>}{statistics.methodology && <p className="drawer-footnote"><b>Methodology.</b> {statistics.methodology}</p>}{statistics.limitations && <p className="drawer-footnote"><b>Limitations.</b> {statistics.limitations}</p>}{statistics.observations.length > 0 && <div className="detail-list"><span>Reported values as supplied</span>{statistics.observations.map((item, index) => <div key={`${item.period}-${index}`}><b>{item.geography_name} · {item.period}: {item.value}</b><span>{[item.unit_measure, item.unit_type, item.unit_multiplier !== null ? `multiplier ${item.unit_multiplier}` : null, item.observation_status ? `status ${item.observation_status}` : null].filter(Boolean).join(" / ") || "No unit or status codes supplied"}</span></div>)}</div>}{statistics.data_sources.length > 0 && <div className="detail-list"><span>Indicator data contributors</span>{statistics.data_sources.map((item, index) => <div key={`${item.name}-${index}`}><b>{item.organization || item.publisher || item.name || 'Source listed in metadata'}</b>{item.url?.startsWith('https://') && <a href={item.url} target="_blank" rel="noreferrer">Open source<ExternalLink size={12} /></a>}</div>)}</div>}<div className="detail-list"><div><span>Dataset page</span><a href={statistics.dataset_url} target="_blank" rel="noreferrer">{statistics.dataset_name}<ExternalLink size={12} /></a></div><div><span>Dataset terms</span><a href={statistics.dataset_terms_url} target="_blank" rel="noreferrer">Reuse terms<ExternalLink size={12} /></a></div>{statistics.license_url && <div><span>License text</span><a href={statistics.license_url} target="_blank" rel="noreferrer">CC BY 4.0<ExternalLink size={12} /></a></div>}</div></>;
}

function EvidenceDrawer({ claim, onClose, preloadedEvidence }: { claim: Claim; onClose: () => void; preloadedEvidence?: ClaimEvidence }) {
  const drawerRef = useRef<HTMLElement>(null);
  useDrawerFocus(drawerRef, onClose);
  const [evidence, setEvidence] = useState<ClaimEvidence | null>(preloadedEvidence || null);
  const [error, setError] = useState('');
  useEffect(() => {
    if (preloadedEvidence) { setEvidence(preloadedEvidence); setError(''); return; }
    setEvidence(null);
    apiClient.getClaimEvidence(claim.id).then(setEvidence).catch((err: unknown) => setError(err instanceof Error ? err.message : 'Could not load passage.'));
  }, [claim.id, preloadedEvidence]);
  const economic = evidence?.claim.economic_facets;
  const methodology = evidence?.claim.appraisal?.methodology_appraisal;
  const sourceSentence = evidence?.claim.source_sentence || evidence?.passage.content || '';
  const spanStart = evidence?.claim.span_start;
  const spanEnd = evidence?.claim.span_end;
  const sourceChars = Array.from(sourceSentence);
  const spanIsExact = Number.isInteger(spanStart) && Number.isInteger(spanEnd)
    && (spanStart as number) >= 0 && (spanEnd as number) > (spanStart as number)
    && (spanEnd as number) <= sourceChars.length
    && sourceChars.slice(spanStart as number, spanEnd as number).join('') === evidence?.claim.text;
  const economicNames: Record<string, string> = { population: 'Population', intervention_or_exposure: 'Intervention or exposure', comparator: 'Comparator', outcome: 'Outcome', estimate: 'Reported estimate or value', uncertainty: 'Uncertainty', geography: 'Geography', time_period: 'Time period', measure: 'Measure' };
  return <div className="drawer-scrim" onClick={onClose}><aside ref={drawerRef} tabIndex={-1} role="dialog" aria-modal="true" aria-labelledby="claim-inspector-title" className="evidence-drawer" onClick={(e) => e.stopPropagation()}><div className="drawer-top"><span className="eyebrow">CLAIM EVIDENCE</span><button className="icon-button" onClick={onClose} aria-label="Close evidence inspector"><X size={17} /></button></div>{error ? <div className="not-ready">{error}</div> : !evidence ? <div className="loading-panel"><LoaderCircle className="spin" /></div> : <><span className="access-badge caution">SOURCE-REPORTED · NOT INDEPENDENTLY VERIFIED</span><h2 id="claim-inspector-title">{evidence.claim.text}</h2><div className="drawer-divider" /><h3>Exact source sentence</h3><div className="evidence-quote claim-source-quote"><span>{evidence.passage.locator} · {evidence.claim.atomization_status || 'legacy whole sentence'}{evidence.claim.atomization_version ? ` · v${evidence.claim.atomization_version}` : ''}</span>{evidence.claim.text_withheld_reason ? <p className="audit-warning" role="status">{sourceSentence}</p> : <p>{spanIsExact ? <>{sourceChars.slice(0, spanStart as number).join('')}<mark className="claim-span-highlight">{sourceChars.slice(spanStart as number, spanEnd as number).join('')}</mark>{sourceChars.slice(spanEnd as number).join('')}</> : sourceSentence}</p>}{Number.isInteger(spanStart) && Number.isInteger(spanEnd) && <small>Unicode codepoint span [{spanStart}, {spanEnd}){spanIsExact ? '' : ' · stored span did not match the exact source text; no highlight shown'}</small>}</div><div className="drawer-divider" /><h3>Supporting passage link</h3><div className="evidence-quote"><span>{evidence.passage.locator}</span><p>{evidence.passage.content_withheld_reason ? evidence.passage.content : `“${evidence.passage.content}”`}</p></div>{economic && <><div className="drawer-divider" /><h3>Economic evidence facets</h3><p className="drawer-footnote">{economic.evidence_kind.replace(/_/g, ' ')} · {economic.status.replace(/_/g, ' ')}{economic.provider ? ` · ${economic.provider}/${economic.model || 'model not recorded'}` : ''}. Facet values are model assessed or deterministic transcriptions, not independently verified.</p><div className="economic-facets">{Object.entries(economicNames).map(([key, label]) => { const facet = economic.facets[key]; return <div key={key}><span>{label}</span><b>{facet?.value || 'unknown'}</b><small>{(facet?.status || 'not assessed').replace(/_/g, ' ')}</small></div>; })}</div></>}<ClaimMethodologyPanel appraisal={methodology} passages={evidence.methodology_passages || []} /><h3>Source</h3><div className="source-link-card"><b>{evidence.source.title}</b><span>{evidence.source.doi || 'No DOI listed'}</span></div><div className="audit-warning"><ShieldCheck size={15} /><span>The stored passage link is valid. Methodology and semantic support are model-assisted interpretations, not independent verification of research truth.</span></div></>}</aside></div>;
}

function useDrawerFocus(dialogRef: React.RefObject<HTMLElement>, onClose: () => void) {
  const closeRef = useRef(onClose);
  useEffect(() => { closeRef.current = onClose; }, [onClose]);
  useEffect(() => {
    const previousFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const focusable = () => dialogRef.current?.querySelectorAll<HTMLElement>(
      'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])',
    );
    const items = () => [...(focusable() || [])].filter((item) => item.getClientRects().length > 0);
    const first = items()[0];
    (first || dialogRef.current)?.focus();
    const handleKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') { closeRef.current(); return; }
      if (event.key !== 'Tab') return;
      const visibleItems = items();
      if (!visibleItems.length) { event.preventDefault(); dialogRef.current?.focus(); return; }
      const firstItem = visibleItems[0];
      const lastItem = visibleItems[visibleItems.length - 1];
      if (event.shiftKey && (document.activeElement === firstItem || document.activeElement === dialogRef.current)) {
        event.preventDefault(); lastItem.focus();
      } else if (!event.shiftKey && document.activeElement === lastItem) {
        event.preventDefault(); firstItem.focus();
      }
    };
    window.addEventListener('keydown', handleKey);
    return () => {
      window.removeEventListener('keydown', handleKey);
      if (previousFocus?.isConnected) previousFocus.focus();
    };
  }, []);
}

function Modal({ title, children, onClose, wide = false }: { title: string; children: React.ReactNode; onClose: () => void; wide?: boolean }) {
  const dialogRef = useRef<HTMLElement>(null);
  const closeRef = useRef(onClose);
  useEffect(() => { closeRef.current = onClose; }, [onClose]);
  useEffect(() => {
    const previousFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const focusable = () => dialogRef.current?.querySelectorAll<HTMLElement>(
      'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])',
    );
    const initialFocus = dialogRef.current?.querySelector<HTMLElement>(
      'input:not([disabled]), textarea:not([disabled]), select:not([disabled])',
    );
    const first = initialFocus || focusable()?.[0];
    (first || dialogRef.current)?.focus();
    const handleKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') { closeRef.current(); return; }
      if (event.key !== 'Tab') return;
      const items = [...(focusable() || [])].filter((item) => item.getClientRects().length > 0);
      if (!items.length) { event.preventDefault(); dialogRef.current?.focus(); return; }
      const firstItem = items[0];
      const lastItem = items[items.length - 1];
      if (event.shiftKey && (document.activeElement === firstItem || document.activeElement === dialogRef.current)) {
        event.preventDefault(); lastItem.focus();
      } else if (!event.shiftKey && document.activeElement === lastItem) {
        event.preventDefault(); firstItem.focus();
      }
    };
    window.addEventListener('keydown', handleKey);
    return () => {
      window.removeEventListener('keydown', handleKey);
      if (previousFocus?.isConnected) previousFocus.focus();
    };
  }, []);
  return <div className="modal-scrim" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}><section ref={dialogRef} tabIndex={-1} className={`modal-card ${wide ? 'wide' : ''}`} role="dialog" aria-modal="true" aria-labelledby="modal-heading"><div className="modal-heading"><div><p className="eyebrow">VEDA WORKSPACE</p><h2 id="modal-heading">{title}</h2></div><button className="icon-button" onClick={onClose} aria-label="Close dialog"><X size={18} /></button></div>{children}</section></div>;
}

function authorLabel(author: { given?: string; family?: string; name?: string }) { return author.name || [author.given, author.family].filter(Boolean).join(' '); }
function prettyStatus(value: string) { return value.replace(/_/g, ' ').replace(/\b\w/g, (letter) => letter.toUpperCase()); }
function stageLabel(value: string) { return ({ planning: 'Building the research plan', discovery: 'Discovering scholarly sources', extraction: 'Extracting source statements', appraisal: 'Recording appraisal status', comparison: 'Comparing evidence scope', verification: 'Checking evidence links', synthesis: 'Preparing the evidence map', complete: 'Research run complete' } as Record<string, string>)[value] || prettyStatus(value); }


