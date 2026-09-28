import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../auth/AuthContext';
import { changePassword } from '../auth/authApi';
import AuthCard from '../components/auth/AuthCard';
import RecoveryCodeDialog from '../components/auth/RecoveryCodeDialog';

/**
 * ChangePasswordPage — both the forced first-login change (the account was
 * created with a temporary password) and a voluntary change from the account page.
 */
export default function ChangePasswordPage() {
  const { user, setUser } = useAuth();
  const navigate = useNavigate();
  const [currentPassword, setCurrentPassword] = useState('');
  const [password, setPassword] = useState('');
  const [confirmation, setConfirmation] = useState('');
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const [issuedCode, setIssuedCode] = useState(null);

  const forced = Boolean(user?.must_change_password);

  const submit = async (event) => {
    event.preventDefault();
    if (password !== confirmation) {
      setError('The two passwords do not match.');
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const result = await changePassword(currentPassword, password);
      setUser(result.user);
      if (result.recovery_code) {
        setIssuedCode(result.recovery_code);
      } else {
        navigate('/account', { replace: true });
      }
    } catch (changeError) {
      setError(changeError.message);
    } finally {
      setBusy(false);
    }
  };

  if (issuedCode) {
    return (
      <RecoveryCodeDialog
        title="Your new recovery code"
        description="Your password has been changed and the recovery code you were given has been replaced. Save the new one:"
        secrets={[{ label: 'Recovery code', value: issuedCode }]}
        onContinue={() => navigate('/', { replace: true })}
        continueLabel="Continue to the dashboard"
      />
    );
  }

  return (
    <AuthCard
      title={forced ? 'Choose your own password' : 'Change your password'}
      subtitle={forced ? 'Your temporary password must be replaced before you continue' : user?.username}
      footer={forced ? null : <Link to="/account">Back to your account</Link>}
    >
      {forced && (
        <div className="auth-notice auth-notice--warning" role="status">
          You signed in with a temporary password. Set your own password to continue — a fresh recovery
          code will be issued with it.
        </div>
      )}

      {error && (
        <div className="auth-notice auth-notice--error" role="alert">
          {error}
        </div>
      )}

      <form className="auth-form" onSubmit={submit}>
        <label className="field">
          <span className="field-label">Current password</span>
          <input
            className="field-input"
            type="password"
            autoComplete="current-password"
            autoFocus
            value={currentPassword}
            onChange={(event) => setCurrentPassword(event.target.value)}
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
          disabled={busy || !currentPassword || !password || !confirmation}
        >
          {busy ? 'Saving…' : 'Change password'}
        </button>
      </form>
    </AuthCard>
  );
}
