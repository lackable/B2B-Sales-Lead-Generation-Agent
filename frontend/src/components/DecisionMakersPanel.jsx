import { useState, useEffect, useCallback } from 'react';
import API from '../api';
import ExcelExportButton from './ExcelExportButton';

/**
 * DecisionMakersPanel — displays the extracted Decision Makers (DMs) list
 * grouped by company and lets the user:
 *  • Call Hunter.io Email Finder API per DM (individual button)
 *  • Run Smart Enrichment: gates on Email Count endpoint (free), then
 *    sequentially finds emails per company stopping at 3 per company,
 *    and pins those DMs to the top of the list with a ⭐ badge.
 */
export default function DecisionMakersPanel({ linkedinStatus }) {
  const [dms, setDms] = useState([]);
  const [loading, setLoading] = useState(false);
  const [searchTerm, setSearchTerm] = useState('');

  // { [dmId]: { loading: boolean, data?: dict, error?: string } }
  const [emailResults, setEmailResults] = useState({});
  const [copiedId, setCopiedId] = useState(null);
  const [bulkFinding, setBulkFinding] = useState(false);

  // Smart enrichment state
  const [smartEnriching, setSmartEnriching] = useState(false);
  const [smartProgress, setSmartProgress] = useState('');  // status message
  const [smartEnrichedIds, setSmartEnrichedIds] = useState(new Set()); // DM ids enriched via smart
  const [noIndexedIds, setNoIndexedIds] = useState(new Set());         // DM ids with count=0

  const fetchDMs = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch(`${API}/linkedin/decision-makers`);
      if (res.ok) {
        const data = await res.json();
        setDms(data.decision_makers ?? []);
      }
    } catch {
      // ignore
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchDMs();
  }, [fetchDMs, linkedinStatus]);

  // ── Persist email to backend store (best-effort, silent) ────────────────────

  const storeEmail = useCallback(async (companyName, dmName, email) => {
    if (!email || !dmName || !companyName) return;
    try {
      await fetch(`${API}/hunter/store-email`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ company_name: companyName, dm_name: dmName, email }),
      });
    } catch {
      // Silent — store-email is best-effort and must not disrupt the UI flow
    }
  }, []);

  // ── Individual Find Email ────────────────────────────────────────────────────

  const handleFindEmail = async (dm) => {
    setEmailResults(prev => ({
      ...prev,
      [dm.id]: { loading: true }
    }));

    try {
      const res = await fetch(`${API}/hunter/find-email`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          linkedin_url: dm.linkedin_url,
          full_name: dm.name,
          company: dm.company_name,
          domain: extractDomain(dm.company_website),
        }),
      });

      const data = await res.json();

      if (!res.ok) {
        const errDetail = data.detail || (data.errors && data.errors[0]?.details) || 'Failed to find email';
        setEmailResults(prev => ({
          ...prev,
          [dm.id]: { loading: false, error: errDetail }
        }));
        return;
      }

      setEmailResults(prev => ({
        ...prev,
        [dm.id]: { loading: false, data: data }
      }));

      // Persist to backend email store so the Excel export can include it
      const foundEmail = data?.data?.email;
      if (foundEmail) {
        storeEmail(dm.company_name, dm.name, foundEmail);
      }
    } catch (err) {
      setEmailResults(prev => ({
        ...prev,
        [dm.id]: { loading: false, error: err.message || 'Network error' }
      }));
    }
  };

  // ── Bulk Find All ────────────────────────────────────────────────────────────

  const handleBulkFind = async () => {
    setBulkFinding(true);
    for (const dm of filteredDMs) {
      if (!dm.linkedin_url) continue;
      if (emailResults[dm.id]?.data?.data?.email) continue;
      await handleFindEmail(dm);
    }
    setBulkFinding(false);
  };

  // ── Smart Enrichment ─────────────────────────────────────────────────────────

  const handleSmartEnrich = async () => {
    if (dms.length === 0) return;
    setSmartEnriching(true);
    setSmartProgress('⚡ Checking email counts per company…');

    try {
      const res = await fetch(`${API}/hunter/smart-enrich`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          decision_makers: dms.map(dm => ({
            id: dm.id,
            name: dm.name,
            linkedin_url: dm.linkedin_url || '',
            company_name: dm.company_name,
            company_website: dm.company_website || '',
            position: dm.position,
          })),
        }),
      });

      const data = await res.json();

      if (!res.ok) {
        setSmartProgress(`⚠️ Smart enrichment error: ${data.detail || 'Unknown error'}`);
        return;
      }

      const { enriched = [], no_indexed_dm_ids = [], total_emails_found = 0,
              skipped_companies = [], stopped_at_cap_companies = [] } = data;

      // Merge email results for enriched DMs
      const newEmailResults = {};
      for (const item of enriched) {
        newEmailResults[item.id] = {
          loading: false,
          data: item.raw,
          smartEnriched: true,
        };
      }
      setEmailResults(prev => ({ ...prev, ...newEmailResults }));
      setSmartEnrichedIds(new Set(enriched.map(e => e.id)));
      setNoIndexedIds(new Set(no_indexed_dm_ids));

      // Persist all found emails to backend store
      for (const item of enriched) {
        const dm = dms.find(d => d.id === item.id);
        const foundEmail = item.raw?.data?.email;
        if (dm && foundEmail) {
          storeEmail(dm.company_name, dm.name, foundEmail);
        }
      }

      // Build a readable summary
      const parts = [];
      if (total_emails_found > 0) parts.push(`✅ ${total_emails_found} email${total_emails_found !== 1 ? 's' : ''} found`);
      if (skipped_companies.length > 0) parts.push(`⛔ ${skipped_companies.length} company(s) had no indexed emails`);
      if (stopped_at_cap_companies.length > 0) parts.push(`🎯 Capped at 3 for: ${stopped_at_cap_companies.join(', ')}`);
      setSmartProgress(parts.length > 0 ? parts.join(' · ') : 'No emails found.');

    } catch (err) {
      setSmartProgress(`⚠️ Network error: ${err.message}`);
    } finally {
      setSmartEnriching(false);
    }
  };

  // ── Copy ─────────────────────────────────────────────────────────────────────

  const handleCopyEmail = (email, id) => {
    if (!email) return;
    navigator.clipboard.writeText(email);
    setCopiedId(id);
    setTimeout(() => setCopiedId(null), 2000);
  };

  // ── Filter + Sort ─────────────────────────────────────────────────────────────
  // Enriched DMs (via smart search) are always sorted to the top.

  const filteredDMs = dms
    .filter(dm => {
      const q = searchTerm.toLowerCase();
      return (
        (dm.name || '').toLowerCase().includes(q) ||
        (dm.position || '').toLowerCase().includes(q) ||
        (dm.company_name || '').toLowerCase().includes(q)
      );
    })
    .sort((a, b) => {
      const aEnriched = smartEnrichedIds.has(a.id) ? 0 : 1;
      const bEnriched = smartEnrichedIds.has(b.id) ? 0 : 1;
      return aEnriched - bEnriched;
    });

  return (
    <div className="panel" style={{ marginTop: '24px' }}>
      <div className="panel-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '10px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <span className="panel-header-title">Decision Makers &amp; Email Finder</span>
          <span className="badge" style={{ background: '#e0e7ff', color: '#3730a3', padding: '2px 8px', borderRadius: '12px', fontSize: '12px', fontWeight: 600 }}>
            {dms.length} {dms.length === 1 ? 'DM Found' : 'DMs Found'}
          </span>
        </div>
        <div style={{ display: 'flex', gap: '10px', alignItems: 'center', flexWrap: 'wrap' }}>
          <button
            className="btn btn-secondary"
            onClick={fetchDMs}
            disabled={loading}
            style={{ fontSize: '12px', padding: '6px 12px' }}
          >
            {loading ? 'Refreshing...' : '🔄 Refresh List'}
          </button>
          {filteredDMs.length > 0 && (
            <button
              className="btn btn-secondary"
              onClick={handleBulkFind}
              disabled={bulkFinding || smartEnriching}
              style={{ fontSize: '12px', padding: '6px 12px' }}
            >
              {bulkFinding ? 'Finding Emails...' : '📧 Find All Emails'}
            </button>
          )}
          {dms.length > 0 && (
            <button
              className="btn btn-primary"
              onClick={handleSmartEnrich}
              disabled={smartEnriching || bulkFinding}
              style={{
                fontSize: '12px',
                padding: '6px 14px',
                fontWeight: 600,
                background: smartEnriching
                  ? 'linear-gradient(135deg, #6366f1 0%, #4f46e5 100%)'
                  : 'linear-gradient(135deg, #f59e0b 0%, #d97706 100%)',
                border: 'none',
                display: 'flex',
                alignItems: 'center',
                gap: '6px',
              }}
            >
              {smartEnriching ? (
                <>
                  <span
                    className="spinner"
                    style={{
                      width: '13px', height: '13px',
                      border: '2px solid rgba(255,255,255,0.4)',
                      borderTopColor: '#fff',
                      borderRadius: '50%',
                      animation: 'spin 0.8s linear infinite',
                      display: 'inline-block',
                    }}
                  />
                  Running Smart Enrichment…
                </>
              ) : (
                '⚡ Smart Email Enrichment'
              )}
            </button>
          )}
          {/* Export to Excel — always visible once DMs are loaded */}
          {dms.length > 0 && <ExcelExportButton />}
        </div>
      </div>

      {/* Smart enrichment progress banner */}
      {smartProgress && (
        <div style={{
          padding: '8px 18px',
          background: smartEnriching ? 'rgba(245, 158, 11, 0.1)' : 'rgba(16, 185, 129, 0.08)',
          borderBottom: `1px solid ${smartEnriching ? 'rgba(245, 158, 11, 0.25)' : 'rgba(16, 185, 129, 0.2)'}`,
          fontSize: '13px',
          fontWeight: 500,
          color: smartEnriching ? '#92400e' : '#065f46',
          display: 'flex',
          alignItems: 'center',
          gap: '8px',
        }}>
          {smartEnriching && (
            <span
              style={{
                display: 'inline-block',
                width: '12px', height: '12px',
                border: '2px solid #f59e0b',
                borderTopColor: 'transparent',
                borderRadius: '50%',
                animation: 'spin 0.8s linear infinite',
              }}
            />
          )}
          {smartProgress}
        </div>
      )}

      <div className="panel-body" style={{ padding: 0 }}>
        <div style={{ padding: '12px 18px', display: 'flex', gap: '16px', alignItems: 'center', background: 'var(--bg-card-header, #f9fafb)', borderBottom: '1px solid var(--border, #e5e7eb)' }}>
          <input
            type="text"
            placeholder="🔍 Filter by Name, Position, or Company..."
            value={searchTerm}
            onChange={e => setSearchTerm(e.target.value)}
            style={{
              flex: 1,
              padding: '8px 14px',
              borderRadius: '6px',
              border: '1px solid var(--border, #d1d5db)',
              fontSize: '13px',
              background: 'var(--bg-input, #ffffff)',
              color: 'var(--text)'
            }}
          />
          {searchTerm && (
            <span style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
              Showing {filteredDMs.length} of {dms.length}
            </span>
          )}
        </div>

        {filteredDMs.length === 0 ? (
          <div style={{ padding: '36px', textAlign: 'center', color: 'var(--text-muted)' }}>
            {dms.length === 0 ? (
              <div>
                <p style={{ fontSize: '14px', marginBottom: '6px' }}>No decision makers extracted yet.</p>
                <span style={{ fontSize: '12px', color: '#6b7280' }}>Run the LinkedIn Finder agent above to extract key personnel and find their emails.</span>
              </div>
            ) : (
              <p style={{ fontSize: '14px' }}>No decision makers match search query &quot;{searchTerm}&quot;.</p>
            )}
          </div>
        ) : (
          <div className="table-container" style={{ border: 'none' }}>
            <table className="data-table">
              <thead>
                <tr>
                  <th style={{ minWidth: 160 }}>Company</th>
                  <th style={{ minWidth: 180 }}>Decision Maker</th>
                  <th>Position</th>
                  <th>LinkedIn Profile</th>
                  <th style={{ minWidth: 260 }}>Hunter Email Action / Result</th>
                </tr>
              </thead>
              <tbody>
                {filteredDMs.map(dm => {
                  const state = emailResults[dm.id] || {};
                  const resultData = state.data?.data;
                  const isSmartEnriched = smartEnrichedIds.has(dm.id);
                  const isNoIndexed = noIndexedIds.has(dm.id);

                  return (
                    <tr
                      key={dm.id}
                      style={isSmartEnriched ? {
                        background: 'linear-gradient(90deg, rgba(245,158,11,0.06) 0%, transparent 100%)',
                        borderLeft: '3px solid #f59e0b',
                      } : {}}
                    >
                      {/* Company */}
                      <td style={{ fontWeight: 600 }}>
                        {isSmartEnriched && (
                          <span title="Found via Smart Enrichment" style={{ marginRight: '5px', fontSize: '13px' }}>⭐</span>
                        )}
                        {dm.company_name}
                        {dm.company_website && (
                          <div style={{ fontSize: '11px', fontWeight: 400, marginTop: '2px' }}>
                            <a href={dm.company_website} target="_blank" rel="noreferrer" style={{ color: '#4f46e5' }}>
                              {extractDomain(dm.company_website)} ↗
                            </a>
                          </div>
                        )}
                      </td>

                      {/* Name */}
                      <td style={{ fontWeight: 500 }}>{dm.name || '—'}</td>

                      {/* Position */}
                      <td style={{ color: 'var(--text-muted)', fontSize: '13px' }}>{dm.position || '—'}</td>

                      {/* LinkedIn */}
                      <td>
                        {dm.linkedin_url ? (
                          <a href={dm.linkedin_url} target="_blank" rel="noreferrer" style={{ display: 'inline-flex', alignItems: 'center', gap: '4px', color: '#2563eb' }}>
                            <span>Profile</span> ↗
                          </a>
                        ) : (
                          <span style={{ color: '#9ca3af', fontSize: '12px' }}>N/A</span>
                        )}
                      </td>

                      {/* Hunter Action / Result */}
                      <td>
                        {isNoIndexed ? (
                          /* Company had 0 emails indexed — show label, no button */
                          <span style={{
                            display: 'inline-flex', alignItems: 'center', gap: '5px',
                            fontSize: '12px', color: '#6b7280', fontStyle: 'italic',
                          }}>
                            <span>⛔</span> No emails indexed for this domain
                          </span>
                        ) : state.loading ? (
                          <span style={{ display: 'inline-flex', alignItems: 'center', gap: '6px', fontSize: '12px', color: '#4f46e5', fontWeight: 500 }}>
                            <span className="spinner" style={{ width: '14px', height: '14px', border: '2px solid #6366f1', borderTopColor: 'transparent', borderRadius: '50%', animation: 'spin 0.8s linear infinite' }} />
                            Fetching from Hunter...
                          </span>
                        ) : resultData ? (
                          <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                            {resultData.email ? (
                              <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
                                {isSmartEnriched && (
                                  <span style={{
                                    fontSize: '10px', fontWeight: 700, padding: '1px 6px',
                                    borderRadius: '10px', background: '#fef3c7', color: '#92400e',
                                    letterSpacing: '0.03em',
                                  }}>
                                    ⭐ SMART FIND
                                  </span>
                                )}
                                <span style={{ fontFamily: 'var(--font-mono, monospace)', fontWeight: 600, color: '#065f46', background: '#d1fae5', padding: '3px 8px', borderRadius: '4px', fontSize: '13px' }}>
                                  {resultData.email}
                                </span>
                                {resultData.score !== undefined && resultData.score !== null && (
                                  <span style={{
                                    fontSize: '11px', fontWeight: 700, padding: '2px 6px', borderRadius: '10px',
                                    background: resultData.score > 70 ? '#dcfce7' : resultData.score > 40 ? '#fef9c3' : '#fee2e2',
                                    color: resultData.score > 70 ? '#15803d' : resultData.score > 40 ? '#a16207' : '#b91c1c',
                                  }}>
                                    {resultData.score}% score
                                  </span>
                                )}
                                <button
                                  className="btn btn-secondary"
                                  onClick={() => handleCopyEmail(resultData.email, dm.id)}
                                  style={{ padding: '2px 6px', fontSize: '11px', gap: '2px' }}
                                  title="Copy Email"
                                >
                                  {copiedId === dm.id ? '✓ Copied' : '📋 Copy'}
                                </button>
                              </div>
                            ) : (
                              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                                <span style={{ fontSize: '12px', color: '#dc2626', fontWeight: 500 }}>
                                  No email address found
                                </span>
                                <button
                                  className="btn btn-secondary"
                                  onClick={() => handleFindEmail(dm)}
                                  style={{ padding: '2px 6px', fontSize: '11px' }}
                                >
                                  Retry
                                </button>
                              </div>
                            )}
                          </div>
                        ) : state.error ? (
                          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                            <span style={{ fontSize: '12px', color: '#b91c1c' }} title={state.error}>
                              ⚠️ {state.error.length > 35 ? state.error.slice(0, 35) + '…' : state.error}
                            </span>
                            <button
                              className="btn btn-secondary"
                              onClick={() => handleFindEmail(dm)}
                              style={{ padding: '2px 6px', fontSize: '11px' }}
                            >
                              Retry
                            </button>
                          </div>
                        ) : (
                          /* Default: show Find Email button (only if LinkedIn URL exists) */
                          dm.linkedin_url ? (
                            <button
                              className="btn btn-secondary"
                              onClick={() => handleFindEmail(dm)}
                              style={{
                                padding: '5px 12px', fontSize: '12px', fontWeight: 500,
                                borderColor: '#c7d2fe', color: '#3730a3', background: '#eef2ff',
                              }}
                            >
                              📧 Find Email
                            </button>
                          ) : (
                            <span style={{ color: '#9ca3af', fontSize: '12px' }}>No LinkedIn URL</span>
                          )
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}

function extractDomain(url) {
  if (!url) return '';
  try {
    const raw = url.startsWith('http') ? url : `https://${url}`;
    const parsed = new URL(raw);
    return parsed.hostname.replace(/^www\./, '');
  } catch {
    return url.replace(/^https?:\/\//, '').replace(/^www\./, '').split('/')[0];
  }
}
