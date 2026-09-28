import { useState } from 'react';
import { Link, Navigate, useNavigate } from 'react-router-dom';
import { useAuth } from '../auth/AuthContext';
import { resetPassword } from '../auth/authApi';
import AuthCard from '../components/auth/AuthCard';
import RecoveryCodeDialog from '../components/auth/RecoveryCodeDialog';

/** ResetPasswordPage — username + recovery code + new password, no session needed. */
export default function ResetPasswordPage() {
  const { user, needsSetup, loading } = useAuth();
  const navigate = useNavigate();
  const [username, setUsername] = useState('');
  const [recoveryCode, setRecoveryCode] = useState('');
  const [password, setPassword] = useState('');
  const [confirmation, setConfirmation] = useState('');
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const [issuedCode, setIssuedCode] = useState(null);

  if (loading) {
    return <div className="auth-shell"><span className="auth-loading">Loading…</span></div>;
  }
  if (needsSetup) {
    return <Navigate to="/setup" replace />;
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
      const result = await resetPassword(username.trim(), recoveryCode, password);
      setIssuedCode(result.recovery_code);
    } catch (resetError) {
      setError(resetError.message);
    } finally {
      setBusy(false);
    }
  };

  if (issuedCode) {
    return (
      <RecoveryCodeDialog
        title="Your new recovery code"
        description="The old code has been used up and every session was signed out. Save the replacement:"
        secrets={[{ label: 'Recovery code', value: issuedCode }]}
        onContinue={() => navigate('/login', { replace: true })}
        continueLabel="Go to sign in"
      />
    );
  }

  return (
    <AuthCard
      title="Reset your password"
      subtitle="Use the recovery code you saved when the account was created"
      footer={
        <>
          {user ? <Link to="/">Back to the dashboard</Link> : <Link to="/login">Back to sign in</Link>}
        </>
      }
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
        </label>

        <label className="field">
          <span className="field-label">Recovery code</span>
          <input
            className="field-input field-input--code"
            type="text"
            placeholder="K7Q2-9XMP-4HDA-ZR8N-TW3C"
            value={recoveryCode}
            onChange={(event) => setRecoveryCode(event.target.value.toUpperCase())}
            disabled={busy}
          />
        </label>

        <label className="field">
          <span className="field-label">New password</span>
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
          <span className="field-label">Confirm new password</span>
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
          disabled={busy || !username.trim() || !recoveryCode.trim() || !password || !confirmation}
        >
          {busy ? 'Resetting…' : 'Reset password'}
        </button>
      </form>
    </AuthCard>
  );
}
