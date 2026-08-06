import { useState, useEffect, useCallback } from 'react';
import API from './api';
import Header from './components/Header';
import QueryPanel from './components/QueryPanel';
import LogStream from './components/LogStream';
import ExcelPreview from './components/ExcelPreview';
import LinkedInPanel from './components/LinkedInPanel';
import DecisionMakersPanel from './components/DecisionMakersPanel';
import TimerBadge from './components/TimerBadge';
import useAgentTelemetry from './hooks/useAgentTelemetry';
import AgentRunVisualizer from '../../agent-run-visualizer (2).jsx';

/**
 * App — root component orchestrating the two-phase pipeline:
 *   Phase 1: Shortlister Agent (query → live log → Excel preview)
 *   Phase 2: LinkedIn Finder Agent (company selection → live log)
 */
export default function App() {
  const [activeView, setActiveView] = useState('pipeline');
  const {
    state: telemetryState,
    beginLocalRun,
    markStartError,
    reset: resetTelemetry,
  } = useAgentTelemetry(API);

  // ── Shortlister state ────────────────────────────────────────────
  const [shortlisterStatus, setShortlisterStatus] = useState('idle');
  const [shortlisterError, setShortlisterError] = useState(null);
  const [shortlisterStreaming, setShortlisterStreaming] = useState(false);
  const [companies, setCompanies] = useState([]);

  // ── LinkedIn Finder state ────────────────────────────────────────
  const [linkedinStatus, setLinkedinStatus] = useState('idle');
  const [linkedinError, setLinkedinError] = useState(null);
  const [linkedinStreaming, setLinkedinStreaming] = useState(false);
  const [currentCompany, setCurrentCompany] = useState(null);
  const [linkedinProgress, setLinkedinProgress] = useState({ completed: 0, total: 0 });

  // ── Poll shortlister status while running ────────────────────────
  useEffect(() => {
    if (shortlisterStatus !== 'running') return;

    const poll = async () => {
      try {
        const res = await fetch(`${API}/shortlister/status`);
        if (!res.ok) return;
        const data = await res.json();
        if (data.status !== 'running') {
          setShortlisterStatus(data.status);
          setCompanies(data.companies ?? []);
          if (data.error) setShortlisterError(data.error);
        }
      } catch {
        // Network hiccup — keep polling
      }
    };

    const interval = setInterval(poll, 2000);
    return () => clearInterval(interval);
  }, [shortlisterStatus]);

  // ── Poll linkedin status while running ───────────────────────────
  useEffect(() => {
    if (linkedinStatus !== 'running') return;

    const poll = async () => {
      try {
        const res = await fetch(`${API}/linkedin/status`);
        if (!res.ok) return;
        const data = await res.json();
        setCurrentCompany(data.current_company ?? null);
        if (data.total_count) {
          setLinkedinProgress({ completed: data.completed_count ?? 0, total: data.total_count });
        }
        if (data.status !== 'running') {
          setLinkedinStatus(data.status);
          setCurrentCompany(null);
          if (data.error) setLinkedinError(data.error);
        }
      } catch {
        // Network hiccup — keep polling
      }
    };

    const interval = setInterval(poll, 2000);
    return () => clearInterval(interval);
  }, [linkedinStatus]);

  // ── Handlers ─────────────────────────────────────────────────────

  const handleShortlisterRun = useCallback(async (query) => {
    setShortlisterError(null);
    setCompanies([]);
    setLinkedinStatus('idle');
    setLinkedinError(null);
    setLinkedinStreaming(false);
    beginLocalRun(query);

    try {
      const res = await fetch(`${API}/shortlister/run`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query }),
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail ?? `HTTP ${res.status}`);
      }

      setShortlisterStatus('running');
      setShortlisterStreaming(true);
    } catch (e) {
      setShortlisterStatus('error');
      setShortlisterError(e.message);
      markStartError(e.message);
    }
  }, [beginLocalRun, markStartError]);

  const handleLinkedinRun = useCallback(async (selectedCompanies, concurrency = 10) => {
    setLinkedinError(null);
    setCurrentCompany(null);
    setLinkedinProgress({ completed: 0, total: selectedCompanies.length });

    try {
      const res = await fetch(`${API}/linkedin/run`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          companies: selectedCompanies.map(c => ({
            company_name: c.company_name,
            linkedin_url: c.linkedin_url ?? '',
            website:      c.website ?? '',
          })),
          concurrency: concurrency,
        }),
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail ?? `HTTP ${res.status}`);
      }

      setLinkedinStatus('running');
      setLinkedinStreaming(true);
    } catch (e) {
      setLinkedinStatus('error');
      setLinkedinError(e.message);
    }
  }, []);

  const handleDownload = useCallback(() => {
    window.open(`${API}/shortlister/download`, '_blank');
  }, []);

  const handleReset = useCallback(async () => {
    try {
      await fetch(`${API}/reset`, { method: 'POST' });
    } catch {
      // ignore
    }
    setShortlisterStatus('idle');
    setShortlisterError(null);
    setShortlisterStreaming(false);
    setCompanies([]);
    setLinkedinStatus('idle');
    setLinkedinError(null);
    setLinkedinStreaming(false);
    setCurrentCompany(null);
    resetTelemetry();
  }, [resetTelemetry]);

  // ── Derived flags ─────────────────────────────────────────────────
  const showLinkedinSection =
    shortlisterStatus === 'done' || linkedinStatus !== 'idle';

  return (
    <div className="app">
      <Header
        shortlisterStatus={shortlisterStatus}
        linkedinStatus={linkedinStatus}
        onReset={handleReset}
      />

      <nav className="view-tabs" aria-label="Application views">
        <button
          className={`view-tab ${activeView === 'pipeline' ? 'view-tab--active' : ''}`}
          onClick={() => setActiveView('pipeline')}
        >
          Pipeline
        </button>
        <button
          className={`view-tab ${activeView === 'visualizer' ? 'view-tab--active' : ''}`}
          onClick={() => setActiveView('visualizer')}
        >
          Live Visualizer
          {telemetryState.run?.status === 'running' && <span className="view-tab-live" />}
        </button>
      </nav>

      {activeView === 'pipeline' ? (
      <main className="main">

        {/* ── Phase 1: Shortlister ─────────────────────────────────── */}
        <section className="section" aria-label="Shortlister Agent">
          <div className="section-header">
            <span className="section-number" aria-hidden="true">1</span>
            <h1 className="section-title">Shortlister Agent</h1>
            {shortlisterStatus !== 'idle' && (
              <span className="section-status" style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                <TimerBadge status={shortlisterStatus} />
                <StatusPill status={shortlisterStatus} />
              </span>
            )}
          </div>

          <QueryPanel
            onSubmit={handleShortlisterRun}
            disabled={shortlisterStatus === 'running'}
            status={shortlisterStatus}
          />

          {shortlisterStreaming && (
            <LogStream
              url={`${API}/shortlister/stream`}
              active={shortlisterStreaming}
              onDone={() => setShortlisterStreaming(false)}
              label="Shortlister Execution Log"
            />
          )}

          {shortlisterError && (
            <div className="alert alert--error" role="alert">
              <span className="alert-label">Error</span>
              <span>{shortlisterError}</span>
            </div>
          )}

          {shortlisterStatus === 'done' && companies.length > 0 && (
            <ExcelPreview
              companies={companies}
              onDownload={handleDownload}
            />
          )}

          {shortlisterStatus === 'done' && (
            <div className="alert alert--success" role="status" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '12px', marginTop: '16px', backgroundColor: 'rgba(16, 185, 129, 0.1)', borderColor: 'rgba(16, 185, 129, 0.3)' }}>
              <div>
                <strong style={{ display: 'block', marginBottom: '2px', color: '#10B981' }}>🎉 Parallel Pipeline Execution Complete!</strong>
                <span style={{ fontSize: '13px' }}>Company shortlisting and executive contact discovery executed in parallel. Your 2-Tab Consolidated Excel report is ready.</span>
              </div>
              <button
                className="btn btn-primary"
                onClick={handleDownload}
                style={{ padding: '10px 18px', fontWeight: 600 }}
              >
                📥 Download Consolidated Excel (.xlsx)
              </button>
            </div>
          )}
        </section>

        {/* ── Phase 2: LinkedIn Finder ──────────────────────────────── */}
        {showLinkedinSection && (
          <section className="section" aria-label="LinkedIn Finder Agent">
            <div className="section-header">
              <span className="section-number" aria-hidden="true">2</span>
              <h2 className="section-title">LinkedIn Finder Agent</h2>
              {linkedinStatus !== 'idle' && (
                <span className="section-status" style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                  <TimerBadge status={linkedinStatus} />
                  <StatusPill status={linkedinStatus} />
                </span>
              )}
              {currentCompany && (
                <span style={{ marginLeft: 'auto', fontSize: 12, color: 'var(--text-muted)' }}>
                  Active: <strong style={{ color: 'var(--text)' }}>{currentCompany}</strong>
                  {linkedinProgress.total > 0 && ` (${linkedinProgress.completed}/${linkedinProgress.total} completed)`}
                </span>
              )}
            </div>

            <LinkedInPanel
              companies={companies}
              onRun={handleLinkedinRun}
              disabled={linkedinStatus === 'running'}
              status={linkedinStatus}
            />

            <DecisionMakersPanel linkedinStatus={linkedinStatus} />

            {linkedinStreaming && (
              <LogStream
                url={`${API}/linkedin/stream`}
                active={linkedinStreaming}
                onDone={() => setLinkedinStreaming(false)}
                label="LinkedIn Finder Execution Log"
              />
            )}

            {linkedinError && (
              <div className="alert alert--error" role="alert">
                <span className="alert-label">Error</span>
                <span>{linkedinError}</span>
              </div>
            )}

            {linkedinStatus === 'done' && (
              <div className="alert alert--info" role="status">
                <span className="alert-label">Done</span>
                <span>
                  LinkedIn Finder completed. Output files are saved in{' '}
                  <code style={{ fontFamily: 'var(--font-mono)', fontSize: 12 }}>
                    Linkedin Finder Agent/output/
                  </code>{' '}
                  and{' '}
                  <code style={{ fontFamily: 'var(--font-mono)', fontSize: 12 }}>
                    output/linkedin/
                  </code>.
                </span>
              </div>
            )}
          </section>
        )}

      </main>
      ) : (
        <main className="main main--visualizer">
          <AgentRunVisualizer telemetry={telemetryState} />
        </main>
      )}
    </div>
  );
}

function StatusPill({ status }) {
  const labels = { running: 'Running', done: 'Completed', error: 'Error', idle: 'Idle' };
  const isRunning = status === 'running';
  return (
    <span className={`status-pill status-pill--${status}`}>
      <span className={`status-dot ${isRunning ? 'status-dot--running' : ''}`} />
      {labels[status] ?? status}
    </span>
  );
}
