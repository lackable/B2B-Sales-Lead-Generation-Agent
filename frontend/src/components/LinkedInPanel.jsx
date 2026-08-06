import { useState, useEffect, useCallback } from 'react';
import API from '../api';
import TimerBadge from './TimerBadge';

/**
 * LinkedInPanel — shows the company table from Shortlister output,
 * lets the user select companies, triggers the LinkedIn Finder agent,
 * and provides direct download buttons for company-specific Excel reports.
 */
export default function LinkedInPanel({ companies, onRun, disabled, status }) {
  const [selected, setSelected] = useState(new Set());
  const [concurrency, setConcurrency] = useState(10);
  const [reports, setReports] = useState([]);

  // Select all by default whenever companies list changes
  useEffect(() => {
    setSelected(new Set(companies.map((_, i) => i)));
  }, [companies]);

  // Fetch generated LinkedIn Excel reports
  const fetchReports = useCallback(async () => {
    try {
      const res = await fetch(`${API}/linkedin/files`);
      if (!res.ok) return;
      const data = await res.json();
      setReports(data.files ?? []);
    } catch {
      // ignore
    }
  }, []);

  useEffect(() => {
    fetchReports();
    const interval = setInterval(fetchReports, 3000);
    return () => clearInterval(interval);
  }, [fetchReports, status]);

  function toggle(i) {
    setSelected(prev => {
      const next = new Set(prev);
      if (next.has(i)) next.delete(i);
      else next.add(i);
      return next;
    });
  }

  function toggleAll() {
    if (selected.size === companies.length) {
      setSelected(new Set());
    } else {
      setSelected(new Set(companies.map((_, i) => i)));
    }
  }

  function handleRun() {
    const payload = [...selected].sort((a, b) => a - b).map(i => ({
      company_name: companies[i].company_name,
      linkedin_url: companies[i].linkedin_url ?? '',
      website:      companies[i].website ?? '',
    }));
    onRun(payload, Number(concurrency) || 10);
  }

  const isRunning = status === 'running';
  const allSelected = selected.size === companies.length;

  return (
    <div className="panel">
      <div className="panel-header">
        <span className="panel-header-title">Company Input — LinkedIn Finder</span>
        {status !== 'idle' && (
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <TimerBadge status={status} />
            <span className={`status-pill status-pill--${status}`}>
              <span className={`status-dot ${isRunning ? 'status-dot--running' : ''}`} />
              {isRunning ? 'Running' : status === 'done' ? 'Completed' : 'Error'}
            </span>
          </div>
        )}
      </div>

      <div className="panel-body" style={{ padding: 0 }}>
        <div className="panel-desc" style={{ padding: '14px 18px', paddingBottom: 0 }}>
          Select the companies to process. Company Name, LinkedIn URL, and Website are passed
          from the Shortlister results. Location is automatically inherited from your initial target query.
        </div>

        <div className="table-container" style={{ border: 'none', borderTop: '1px solid var(--border)', marginTop: 14 }}>
          <table className="data-table">
            <thead>
              <tr>
                <th style={{ width: 44, textAlign: 'center' }}>
                  <input
                    type="checkbox"
                    id="linkedin-select-all"
                    checked={allSelected}
                    onChange={toggleAll}
                    disabled={disabled}
                    title={allSelected ? 'Deselect all' : 'Select all'}
                  />
                </th>
                <th>Company Name</th>
                <th>Ticker</th>
                <th>LinkedIn URL</th>
                <th>Website</th>
                <th style={{ textAlign: 'center', minWidth: 150 }}>Company Excel</th>
              </tr>
            </thead>
            <tbody>
              {companies.map((c, i) => (
                <CompanyRow
                  key={i}
                  index={i}
                  company={c}
                  checked={selected.has(i)}
                  disabled={disabled}
                  status={status}
                  reports={reports}
                  onToggle={toggle}
                />
              ))}
            </tbody>
          </table>
        </div>

        <div className="linkedin-footer" style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '12px 18px', gap: '16px' }}>
          <span className="selection-label">
            <strong>{selected.size}</strong> of {companies.length}{' '}
            {companies.length === 1 ? 'company' : 'companies'} selected
            {reports.length > 0 && (
              <span style={{ marginLeft: '12px', color: 'var(--success)', fontWeight: 500 }}>
                ({reports.length} Excel {reports.length === 1 ? 'report' : 'reports'} available)
              </span>
            )}
          </span>
          
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
            <label htmlFor="concurrency-input" style={{ fontSize: '13px', color: 'var(--text-muted)', display: 'flex', alignItems: 'center', gap: '6px' }}>
              Concurrency Limit:
              <input
                id="concurrency-input"
                type="number"
                min="1"
                max="50"
                value={concurrency}
                onChange={e => setConcurrency(Math.max(1, parseInt(e.target.value) || 1))}
                disabled={disabled}
                style={{
                  width: '60px',
                  padding: '4px 8px',
                  borderRadius: '4px',
                  border: '1px solid var(--border)',
                  background: 'var(--bg-input)',
                  color: 'var(--text)',
                  fontSize: '13px'
                }}
              />
            </label>

            <button
              id="btn-run-linkedin"
              className="btn btn-primary"
              onClick={handleRun}
              disabled={disabled || selected.size === 0}
            >
              {isRunning ? 'Running Parallel...' : 'Run LinkedIn Finder'}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

function CompanyRow({ index, company, checked, disabled, status, reports, onToggle }) {
  const matchingReport = findMatchingReport(company, reports);

  return (
    <tr className={checked ? 'row-selected' : ''}>
      <td style={{ textAlign: 'center' }}>
        <input
          type="checkbox"
          id={`linkedin-select-${index}`}
          checked={checked}
          onChange={() => onToggle(index)}
          disabled={disabled}
        />
      </td>
      <td style={{ fontWeight: 500 }}>{company.company_name || '—'}</td>
      <td className="cell-mono">{company.ticker || '—'}</td>
      <td>
        {company.linkedin_url ? (
          <a href={company.linkedin_url} target="_blank" rel="noreferrer" title={company.linkedin_url}>
            {truncate(company.linkedin_url, 40)}
          </a>
        ) : (
          <span className="cell-muted">Not available</span>
        )}
      </td>
      <td>
        {company.website ? (
          <a href={company.website} target="_blank" rel="noreferrer" title={company.website}>
            {truncate(company.website, 35)}
          </a>
        ) : (
          <span className="cell-muted">Not available</span>
        )}
      </td>
      <td style={{ textAlign: 'center' }}>
        {matchingReport ? (
          <button
            id={`btn-download-${index}`}
            className="btn btn-secondary"
            style={{
              padding: '4px 10px',
              fontSize: '12px',
              gap: '4px',
              display: 'inline-flex',
              alignItems: 'center',
              borderColor: '#93c5fd',
              color: '#1d4ed8',
              background: '#eff6ff',
              cursor: 'pointer'
            }}
            onClick={() => window.open(`${API}${matchingReport.download_url}`, '_blank')}
            title={`Download ${matchingReport.filename}`}
          >
            📥 Download Excel
          </button>
        ) : (
          <span className="cell-muted" style={{ fontSize: '12px' }}>
            {status === 'running' ? 'Processing...' : '—'}
          </span>
        )}
      </td>
    </tr>
  );
}

function findMatchingReport(company, reports) {
  if (!reports || reports.length === 0) return null;
  const nameClean = (company.company_name || '').replace(/[^a-zA-Z0-9]/g, '').toLowerCase();
  const tickerClean = (company.ticker || '').replace(/[^a-zA-Z0-9]/g, '').toLowerCase();

  for (const r of reports) {
    const fileClean = r.filename.replace(/[^a-zA-Z0-9]/g, '').toLowerCase();
    if (nameClean && nameClean.length > 2 && fileClean.includes(nameClean)) return r;
    if (tickerClean && tickerClean.length > 2 && fileClean.includes(tickerClean)) return r;
  }
  return null;
}

function truncate(str, max) {
  if (!str) return '';
  return str.length > max ? str.slice(0, max) + '…' : str;
}

