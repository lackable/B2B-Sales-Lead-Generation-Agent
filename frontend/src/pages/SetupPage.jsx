import { useState } from 'react';
import { Navigate, useNavigate } from 'react-router-dom';
import { useAuth } from '../auth/AuthContext';
import AuthCard from '../components/auth/AuthCard';
import RecoveryCodeDialog from '../components/auth/RecoveryCodeDialog';

/** SetupPage — first-run only: the first account becomes the administrator. */
export default function SetupPage() {
  const { needsSetup, loading, completeSetup } = useAuth();
  const navigate = useNavigate();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [confirmation, setConfirmation] = useState('');
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null);

  if (loading) {
    return <div className="auth-shell"><span className="auth-loading">Loading…</span></div>;
  }
  if (!needsSetup && !result) {
    return <Navigate to="/login" replace />;
  }

  const submit = async (event) => {
    event.preventDefault();
    if (password !== confirmation) {
      setError('The two passwords do not match.');
      return;
    }
    setBusy(true);
    setError(null);
    try {
      setResult(await completeSetup(username.trim(), password));
    } catch (setupError) {
      setError(setupError.message);
    } finally {
      setBusy(false);
    }
  };

  if (result) {
    return (
      <RecoveryCodeDialog
        title="Your recovery code"
        description={`Welcome, ${result.user.username}. This recovery code is the only way to reset your password if you forget it.`}
        secrets={[{ label: 'Recovery code', value: result.recovery_code }]}
        onContinue={() => navigate('/', { replace: true })}
        continueLabel="Continue to the dashboard"
      />
    );
  }

  return (
    <AuthCard
      title="Create the administrator"
      subtitle="First run — this account manages every other user"
    >
      {error && (
        <div className="auth-notice auth-notice--error" role="alert">
          {error}
        </div>
      )}

      <form className="auth-form" onSubmit={submit}>
        <label className="field">
          <span className="field-label">Username</span>
          <input
            className="field-input"
            type="text"
            autoComplete="username"
            autoFocus
            value={username}
            onChange={(event) => setUsername(event.target.value)}
            disabled={busy}
          />
          <span className="field-hint">3–32 characters: letters, digits, dot, underscore or hyphen.</span>
        </label>

        <label className="field">
          <span className="field-label">Password</span>
          <input
            className="field-input"
            type="password"
            autoComplete="new-password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            disabled={busy}
          />
          <span className="field-hint">At least 12 characters, and not the same as the username.</span>
        </label>

        <label className="field">
          <span className="field-label">Confirm password</span>
          <input
            className="field-input"
            type="password"
            autoComplete="new-password"
            value={confirmation}
            onChange={(event) => setConfirmation(event.target.value)}
            disabled={busy}
          />
        </label>

        <button
          className="btn btn-primary"
          type="submit"
          disabled={busy || !username.trim() || !password || !confirmation}
        >
          {busy ? 'Creating…' : 'Create administrator'}
        </button>
      </form>
    </AuthCard>
  );
}
