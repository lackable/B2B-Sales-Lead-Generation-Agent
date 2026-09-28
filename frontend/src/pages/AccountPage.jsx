import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useAuth } from '../auth/AuthContext';
import { regenerateRecoveryCode } from '../auth/authApi';
import AuthCard from '../components/auth/AuthCard';
import RecoveryCodeDialog from '../components/auth/RecoveryCodeDialog';

/** AccountPage — who you are, rotate the recovery code, sign out. */
export default function AccountPage() {
  const { user, signOut } = useAuth();
  const [password, setPassword] = useState('');
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const [issuedCode, setIssuedCode] = useState(null);

  const submit = async (event) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const result = await regenerateRecoveryCode(password);
      setIssuedCode(result.recovery_code);
      setPassword('');
    } catch (rotateError) {
      setError(rotateError.message);
    } finally {
      setBusy(false);
    }
  };

  if (issuedCode) {
    return (
      <RecoveryCodeDialog
        title="Your new recovery code"
        description="The previous code no longer works. Save this replacement:"
        secrets={[{ label: 'Recovery code', value: issuedCode }]}
        onContinue={() => setIssuedCode(null)}
        continueLabel="Done"
      />
    );
  }

  return (
    <AuthCard
      title="Your account"
      subtitle={user?.username}
      footer={<Link to="/">Back to the dashboard</Link>}
    >
      <dl className="account-facts">
        <div className="account-fact">
          <dt>Username</dt>
          <dd>{user?.username}</dd>
        </div>
        <div className="account-fact">
          <dt>Role</dt>
          <dd>{user?.role}</dd>
        </div>
        <div className="account-fact">
          <dt>Last sign-in</dt>
          <dd>{formatTimestamp(user?.last_login_at) ?? 'This is your first session'}</dd>
        </div>
      </dl>

      <div className="auth-links auth-links--stacked">
        <Link to="/change-password">Change password</Link>
        <button type="button" className="link-button" onClick={signOut}>
          Sign out
        </button>
      </div>

      <form className="auth-form" onSubmit={submit}>
        <span className="field-label">Regenerate recovery code</span>
        <span className="field-hint">
          The old code stops working immediately. Confirm your password to receive a new one.
        </span>

        {error && (
          <div className="auth-notice auth-notice--error" role="alert">
            {error}
          </div>
        )}

        <label className="field">
          <span className="field-label">Password</span>
          <input
            className="field-input"
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            disabled={busy}
          />
        </label>

        <button className="btn btn-secondary" type="submit" disabled={busy || !password}>
          {busy ? 'Generating…' : 'Generate a new code'}
        </button>
      </form>
    </AuthCard>
  );
}

/** The API stores naive UTC timestamps, so mark them as UTC before parsing. */
function formatTimestamp(value) {
  if (!value) return null;
  const iso = /[zZ]|[+-]\d{2}:\d{2}$/.test(value) ? value : `${value}Z`;
  const parsed = new Date(iso);
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString();
}
