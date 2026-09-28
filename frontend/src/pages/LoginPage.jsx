import { useState } from 'react';
import { Link, Navigate } from 'react-router-dom';
import { useAuth } from '../auth/AuthContext';
import AuthCard from '../components/auth/AuthCard';

/** LoginPage — username + password; usernames are case-insensitive. */
export default function LoginPage() {
  const { user, needsSetup, loading, expired, signIn } = useAuth();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  if (loading) {
    return <div className="auth-shell"><span className="auth-loading">Loading…</span></div>;
  }
  if (needsSetup) {
    return <Navigate to="/setup" replace />;
  }
  if (user) {
    return <Navigate to="/" replace />;
  }

  const submit = async (event) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await signIn(username.trim(), password);
    } catch (loginError) {
      setError(loginError.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <AuthCard
      title="Sign in"
      subtitle="Agent Pipeline · Shortlister + LinkedIn Finder"
      footer={<Link to="/reset-password">Forgot your password?</Link>}
    >
      {expired && (
        <div className="auth-notice auth-notice--warning" role="status">
          Your session expired. Please sign in again.
        </div>
      )}

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

        <button className="btn btn-primary" type="submit" disabled={busy || !username.trim() || !password}>
          {busy ? 'Signing in…' : 'Sign in'}
        </button>
      </form>
    </AuthCard>
  );
}
