import { useState } from 'react';
import API from '../api';

/**
 * ExcelExportButton — triggers GET /export/consolidated, streams the .xlsx
 * as a browser download, and saves a copy server-side in output/exports/.
 *
 * No props required — the backend reads all data from its own state
 * (shortlister companies, extracted location, DMs, email store).
 */
export default function ExcelExportButton() {
  const [exporting, setExporting] = useState(false);
  const [error, setError]         = useState(null);
  const [done, setDone]           = useState(false);

  const handleExport = async () => {
    setExporting(true);
    setError(null);
    setDone(false);

    try {
      const res = await fetch(`${API}/export/consolidated`);

      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || `HTTP ${res.status}`);
      }

      // Resolve filename from Content-Disposition header
      const cd       = res.headers.get('Content-Disposition') || '';
      const match    = cd.match(/filename="?([^";\r\n]+)"?/);
      const filename = match ? match[1] : `export_${Date.now()}.xlsx`;

      // Trigger browser download
      const blob = await res.blob();
      const url  = URL.createObjectURL(blob);
      const a    = document.createElement('a');
      a.href     = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);

      setDone(true);
      setTimeout(() => setDone(false), 3500);
    } catch (e) {
      setError(e.message);
      setTimeout(() => setError(null), 6000);
    } finally {
      setExporting(false);
    }
  };

  /* ── Render ──────────────────────────────────────────────────────────────── */

  const bg = done
    ? 'linear-gradient(135deg, #059669 0%, #047857 100%)'
    : exporting
    ? '#4b5563'
    : 'linear-gradient(135deg, #0ea5e9 0%, #0369a1 100%)';

  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-start', gap: '4px' }}>
      <button
        id="excel-export-btn"
        className="btn btn-primary"
        onClick={handleExport}
        disabled={exporting}
        title="Export Company Overview + Decision Makers to a 2-sheet .xlsx"
        style={{
          fontSize: '12px',
          padding: '6px 14px',
          fontWeight: 600,
          background: bg,
          border: 'none',
          display: 'inline-flex',
          alignItems: 'center',
          gap: '6px',
          transition: 'background 0.3s ease',
        }}
      >
        {exporting ? (
          <>
            <span
              style={{
                display: 'inline-block',
                width: '13px',
                height: '13px',
                border: '2px solid rgba(255,255,255,0.35)',
                borderTopColor: '#fff',
                borderRadius: '50%',
                animation: 'spin 0.8s linear infinite',
                flexShrink: 0,
              }}
            />
            Generating Excel…
          </>
        ) : done ? (
          '✅ Downloaded!'
        ) : (
          '📊 Export to Excel'
        )}
      </button>

      {error && (
        <span
          style={{
            fontSize: '11px',
            color: '#dc2626',
            maxWidth: '240px',
            lineHeight: 1.4,
          }}
        >
          ⚠️ {error}
        </span>
      )}
    </div>
  );
}
