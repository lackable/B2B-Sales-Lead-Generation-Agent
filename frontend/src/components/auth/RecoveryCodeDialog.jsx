import { useState } from 'react';

/**
 * RecoveryCodeDialog — shows one-time secrets exactly once.
 *
 * Used for the recovery code issued at setup, the temporary password plus
 * recovery code of an admin-created account, and rotated recovery codes. The
 * Continue button stays disabled until the values have been acknowledged.
 */
export default function RecoveryCodeDialog({ title, description, secrets, onContinue, continueLabel = 'Continue' }) {
  const [copiedLabel, setCopiedLabel] = useState(null);
  const [acknowledged, setAcknowledged] = useState(false);

  const copy = async (label, value) => {
    try {
      await navigator.clipboard.writeText(value);
      setCopiedLabel(label);
      setTimeout(() => setCopiedLabel(null), 2000);
    } catch {
      // Clipboard access can be blocked; the code is visible and downloadable.
    }
  };

  const download = () => {
    const lines = secrets.map(({ label, value }) => `${label}: ${value}`).join('\n');
    const blob = new Blob([`Agent Pipeline credentials\n\n${lines}\n`], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = 'agent-pipeline-credentials.txt';
    document.body.appendChild(anchor);
    anchor.click();
    document.body.removeChild(anchor);
    URL.revokeObjectURL(url);
  };

  return (
    <div className="dialog-backdrop">
      <div className="dialog" role="dialog" aria-modal="true" aria-label={title ?? 'One-time credentials'}>
        <div className="dialog-header">
          <span className="dialog-title">{title ?? 'Save these values now'}</span>
        </div>

        <div className="dialog-body">
          <p className="dialog-text">{description}</p>

          {secrets.map(({ label, value }) => (
            <div className="secret-row" key={label}>
              <span className="secret-label">{label}</span>
              <div className="secret-value">
                <code className="code-display">{value}</code>
                <button type="button" className="btn btn-secondary" onClick={() => copy(label, value)}>
                  {copiedLabel === label ? '✓ Copied' : 'Copy'}
                </button>
              </div>
            </div>
          ))}

          <div className="auth-notice auth-notice--warning">
            These values are shown once and never again.
          </div>

          <label className="checkbox-row">
            <input
              type="checkbox"
              checked={acknowledged}
              onChange={(event) => setAcknowledged(event.target.checked)}
            />
            <span>I have saved this information somewhere safe</span>
          </label>
        </div>

        <div className="dialog-footer">
          <button type="button" className="btn btn-secondary" onClick={download}>
            Download .txt
          </button>
          <button type="button" className="btn btn-primary" disabled={!acknowledged} onClick={onContinue}>
            {continueLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
