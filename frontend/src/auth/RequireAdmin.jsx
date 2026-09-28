import { Navigate, Outlet } from 'react-router-dom';
import { useAuth } from './AuthContext';

/** RequireAdmin — nested inside RequireAuth; non-admins go back to the dashboard. */
export default function RequireAdmin() {
  const { user } = useAuth();

  if (user?.role !== 'admin') {
    return <Navigate to="/" replace />;
  }

  return <Outlet />;
}
