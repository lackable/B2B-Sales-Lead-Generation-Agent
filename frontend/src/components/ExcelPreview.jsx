/**
 * ExcelPreview — displays shortlisted companies in a data table
 * and provides a download button for the Excel report.
 */
export default function ExcelPreview({ companies, onDownload }) {
  if (!companies || companies.length === 0) return null;

  return (
    <div className="panel">
      <div className="results-actions">
        <p className="results-count">
          Shortlist: <span>{companies.length}</span>{' '}
          {companies.length === 1 ? 'company' : 'companies'} verified
        </p>
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: '4px' }}>
          <button
            id="btn-download-excel"
            className="btn btn-primary"
            onClick={onDownload}
            style={{ fontWeight: 600, padding: '10px 18px', fontSize: '14px' }}
          >
            📥 Download Consolidated Excel Report (.xlsx)
          </button>
          <span style={{ fontSize: '11px', color: 'var(--text-muted, #9CA3AF)', fontStyle: 'italic' }}>
            Includes 2 Tabs: 1. Company Shortlist | 2. Decision Maker Contacts
          </span>
        </div>
      </div>

      <div className="table-container">
        <table className="data-table">
          <thead>
            <tr>
              <th style={{ width: 36 }}>#</th>
              <th>Company Name</th>
              <th>Ticker</th>
              <th>Industry</th>
              <th>Revenue (TTM)</th>
              <th>Net Income</th>
              <th>Employees</th>
              <th>Website</th>
              <th>LinkedIn</th>
              <th>LinkedIn Status</th>
            </tr>
          </thead>
          <tbody>
            {companies.map((c, i) => (
              <tr key={i}>
                <td className="cell-num">{i + 1}</td>
                <td style={{ fontWeight: 500 }}>{c.company_name || '—'}</td>
                <td className="cell-mono">{c.ticker || '—'}</td>
                <td>{c.industry || '—'}</td>
                <td className="cell-mono">{formatNumber(c.revenue)}</td>
                <td className="cell-mono">{formatNumber(c.net_income)}</td>
                <td className="cell-mono">{c.employees || '—'}</td>
                <td>
                  {c.website ? (
                    <a href={c.website} target="_blank" rel="noreferrer" title={c.website}>
                      {truncate(c.website, 35)}
                    </a>
                  ) : <span className="cell-muted">Not available</span>}
                </td>
                <td>
                  {c.linkedin_url ? (
                    <a href={c.linkedin_url} target="_blank" rel="noreferrer">
                      View Profile
                    </a>
                  ) : <span className="cell-muted">Not available</span>}
                </td>
                <td>
                  <LinkedInBadge value={c.linkedin_confirmed} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function LinkedInBadge({ value }) {
  if (!value || value === 'None' || value === 'nan') {
    return <span className="badge badge--muted">Unknown</span>;
  }
  if (value === 'Verified') {
    return <span className="badge badge--success">Verified</span>;
  }
  return <span className="badge badge--warning">{value}</span>;
}

function formatNumber(val) {
  if (!val || val === 'None' || val === 'nan' || val === '') return '—';
  const n = parseFloat(String(val).replace(/,/g, ''));
  if (!isNaN(n)) {
    if (Math.abs(n) >= 1e9) return `${(n / 1e9).toFixed(2)}B`;
    if (Math.abs(n) >= 1e6) return `${(n / 1e6).toFixed(2)}M`;
    if (Math.abs(n) >= 1e3) return `${(n / 1e3).toFixed(1)}K`;
    return n.toLocaleString();
  }
  return String(val);
}

function truncate(str, max) {
  if (!str) return '';
  return str.length > max ? str.slice(0, max) + '…' : str;
}
