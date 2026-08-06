import { useState } from 'react';
import TimerBadge from './TimerBadge';

/**
 * QueryPanel — user inputs a profile description and triggers the Shortlister run.
 */
export default function QueryPanel({ onSubmit, disabled, status }) {
  const [query, setQuery] = useState('');

  function handleSubmit(e) {
    e.preventDefault();
    const trimmed = query.trim();
    if (trimmed) onSubmit(trimmed);
  }

  const isRunning = status === 'running';

  return (
    <div className="panel">
      <div className="panel-header">
        <span className="panel-header-title">Target Profile Query</span>
        {status !== 'idle' && (
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <TimerBadge status={status} />
            <StatusPill status={status} />
          </div>
        )}
      </div>

      <div className="panel-body">
        <form onSubmit={handleSubmit} className="query-input-wrapper">
          <textarea
            id="shortlister-query-input"
            className="query-textarea"
            value={query}
            onChange={e => setQuery(e.target.value)}
            placeholder="Describe the company profile you are looking for. Include sector, size, geography, or any other filters..."
            disabled={disabled}
            rows={4}
            aria-label="Company profile query"
          />
          <div className="form-footer">
            <span className="form-hint">
              {isRunning
                ? 'Pipeline is running. Do not navigate away.'
                : 'The Shortlister agent will screen, research, and verify companies matching your profile.'}
            </span>
            <button
              id="btn-run-shortlister"
              type="submit"
              className="btn btn-primary"
              disabled={disabled || !query.trim()}
            >
              {isRunning ? 'Running...' : 'Run Shortlister'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

function StatusPill({ status }) {
  const labels = {
    running: 'Running',
    done: 'Completed',
    error: 'Error',
    idle: 'Idle',
  };
  return (
    <span className={`status-pill status-pill--${status}`}>
      <span className={`status-dot ${status === 'running' ? 'status-dot--running' : ''}`} />
      {labels[status] ?? status}
    </span>
  );
}
