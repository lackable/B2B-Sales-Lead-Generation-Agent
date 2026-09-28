import { Navigate, Outlet, useLocation } from 'react-router-dom';
import { useAuth } from './AuthContext';

/**
 * RequireAuth — gate for every signed-in area.
 *
 * Sends the visitor to /setup on a fresh install, to /login without a session,
 * and to /change-password while a temporary password is still in use.
 */
export default function RequireAuth() {
  const { user, needsSetup, loading } = useAuth();
  const location = useLocation();

  if (loading) {
    return <div className="auth-shell"><span className="auth-loading">Checking your session…</span></div>;
  }

  if (needsSetup) {
    return <Navigate to="/setup" replace />;
  }

  if (!user) {
    return <Navigate to="/login" replace state={{ from: location.pathname + location.search }} />;
  }

  if (user.must_change_password && location.pathname !== '/change-password') {
    return <Navigate to="/change-password" replace />;
  }

  return <Outlet />;
}
