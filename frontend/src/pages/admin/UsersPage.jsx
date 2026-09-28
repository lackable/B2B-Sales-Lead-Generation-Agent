import { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { useAuth } from '../../auth/AuthContext';
import { createUser, listUsers, revokeUserSessions, updateUser } from '../../auth/authApi';
import RecoveryCodeDialog from '../../components/auth/RecoveryCodeDialog';

/** UsersPage — administrator-only user management. */
export default function UsersPage() {
  const { user: currentUser } = useAuth();
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [busyId, setBusyId] = useState(null);

  const [newUsername, setNewUsername] = useState('');
  const [newRole, setNewRole] = useState('user');
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState(null);
  const [created, setCreated] = useState(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const data = await listUsers();
      setUsers(data.users ?? []);
      setError(null);
    } catch (listError) {
      setError(listError.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const submitCreate = async (event) => {
    event.preventDefault();
    setCreating(true);
    setCreateError(null);
    try {
      const result = await createUser(newUsername.trim(), newRole);
      setCreated(result);
      setNewUsername('');
      setNewRole('user');
      await refresh();
    } catch (creationError) {
      setCreateError(creationError.message);
    } finally {
      setCreating(false);
    }
  };

  const patchUser = async (account, patch) => {
    setBusyId(account.id);
    setError(null);
    try {
      await updateUser(account.id, patch);
      await refresh();
    } catch (updateError) {
      setError(updateError.message);
    } finally {
      setBusyId(null);
    }
  };

  const revokeSessions = async (account) => {
    setBusyId(account.id);
    setError(null);
    try {
      await revokeUserSessions(account.id);
    } catch (revokeError) {
      setError(revokeError.message);
    } finally {
      setBusyId(null);
    }
  };

  if (created) {
    return (
      <RecoveryCodeDialog
        title={`Credentials for ${created.user.username}`}
        description="Hand these over securely. The password must be changed at first sign-in, which issues a new recovery code."
        secrets={[
          { label: 'Temporary password', value: created.temporary_password },
          { label: 'Recovery code', value: created.recovery_code },
        ]}
        onContinue={() => setCreated(null)}
        continueLabel="Done"
      />
    );
  }

  return (
    <div className="app">
      <header className="header">
        <div className="header-brand">
          <span className="header-title">Agent Pipeline</span>
          <span className="header-subtitle">Administration</span>
        </div>
        <div className="header-right">
          <div className="header-user">
            <span className="header-username">{currentUser?.username}</span>
            <Link className="header-nav-link" to="/">Dashboard</Link>
            <Link className="header-nav-link" to="/account">Account</Link>
          </div>
        </div>
      </header>

      <main className="main">
        <section className="section" aria-label="Create user">
          <div className="section-header">
            <span className="section-number" aria-hidden="true">+</span>
            <h1 className="section-title">Create user</h1>
          </div>

          <div className="panel">
            <div className="panel-body">
              {createError && (
                <div className="auth-notice auth-notice--error" role="alert">
                  {createError}
                </div>
              )}
              <form className="users-create-form" onSubmit={submitCreate}>
                <label className="field">
                  <span className="field-label">Username</span>
                  <input
                    className="field-input"
                    type="text"
                    value={newUsername}
                    onChange={(event) => setNewUsername(event.target.value)}
                    placeholder="jane.doe"
                    disabled={creating}
                  />
                </label>

                <label className="field">
                  <span className="field-label">Role</span>
                  <select
                    className="field-input"
                    value={newRole}
                    onChange={(event) => setNewRole(event.target.value)}
                    disabled={creating}
                  >
                    <option value="user">User</option>
                    <option value="admin">Administrator</option>
                  </select>
                </label>

                <button className="btn btn-primary" type="submit" disabled={creating || newUsername.trim().length < 3}>
                  {creating ? 'Creating…' : 'Create user'}
                </button>
              </form>
              <p className="field-hint">
                The server generates a temporary password and a recovery code, both shown exactly once.
              </p>
            </div>
          </div>
        </section>

        <section className="section" aria-label="All users">
          <div className="section-header">
            <span className="section-number" aria-hidden="true">{users.length}</span>
            <h2 className="section-title">Users</h2>
            <span className="section-status">
              <button className="btn btn-secondary" type="button" onClick={refresh} disabled={loading}>
                {loading ? 'Refreshing…' : 'Refresh'}
              </button>
            </span>
          </div>

          {error && (
            <div className="auth-notice auth-notice--error" role="alert">
              {error}
            </div>
          )}

          <div className="panel">
            <div className="table-container" style={{ border: 'none' }}>
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Username</th>
                    <th>Role</th>
                    <th>Status</th>
                    <th>Password</th>
                    <th>Last sign-in</th>
                    <th style={{ minWidth: 260 }}>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {users.map((account) => {
                    const isSelf = account.id === currentUser?.id;
                    const busy = busyId === account.id;
                    return (
                      <tr key={account.id}>
                        <td style={{ fontWeight: 600 }}>
                          {account.username}
                          {isSelf && <span className="badge badge--muted" style={{ marginLeft: 8 }}>you</span>}
                        </td>
                        <td>
                          <select
                            className="field-input field-input--compact"
                            value={account.role}
                            disabled={busy || isSelf}
                            onChange={(event) => patchUser(account, { role: event.target.value })}
                          >
                            <option value="user">User</option>
                            <option value="admin">Administrator</option>
                          </select>
                        </td>
                        <td>
                          <span className={`badge ${account.is_active ? 'badge--success' : 'badge--warning'}`}>
                            {account.is_active ? 'Active' : 'Disabled'}
                          </span>
                        </td>
                        <td>
                          {account.must_change_password
                            ? <span className="badge badge--warning">Temporary</span>
                            : <span className="badge badge--muted">Set by user</span>}
                        </td>
                        <td className="cell-muted">{formatTimestamp(account.last_login_at) ?? 'never'}</td>
                        <td>
                          <div className="row-actions">
                            <button
                              className="btn btn-secondary"
                              type="button"
                              disabled={busy || isSelf}
                              onClick={() => patchUser(account, { is_active: !account.is_active })}
                            >
                              {account.is_active ? 'Disable' : 'Enable'}
                            </button>
                            <button
                              className="btn btn-secondary"
                              type="button"
                              disabled={busy}
                              onClick={() => revokeSessions(account)}
                            >
                              Revoke sessions
                            </button>
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                  {users.length === 0 && !loading && (
                    <tr>
                      <td colSpan={6} className="cell-muted" style={{ textAlign: 'center', padding: 28 }}>
                        No users yet.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </section>
      </main>
    </div>
  );
}

/** The API stores naive UTC timestamps, so mark them as UTC before parsing. */
function formatTimestamp(value) {
  if (!value) return null;
  const iso = /[zZ]|[+-]\d{2}:\d{2}$/.test(value) ? value : `${value}Z`;
  const parsed = new Date(iso);
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString();
}
