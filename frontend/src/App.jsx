import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';
import { AuthProvider } from './auth/AuthContext';
import RequireAdmin from './auth/RequireAdmin';
import RequireAuth from './auth/RequireAuth';
import AccountPage from './pages/AccountPage';
import ChangePasswordPage from './pages/ChangePasswordPage';
import DashboardPage from './pages/DashboardPage';
import LoginPage from './pages/LoginPage';
import ResetPasswordPage from './pages/ResetPasswordPage';
import SetupPage from './pages/SetupPage';
import UsersPage from './pages/admin/UsersPage';

/**
 * App — routing shell.
 *
 * Public: /setup (first run), /login, /reset-password.
 * Everything else is behind RequireAuth; /admin/users also needs RequireAdmin.
 */
export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Routes>
          <Route path="/setup" element={<SetupPage />} />
          <Route path="/login" element={<LoginPage />} />
          <Route path="/reset-password" element={<ResetPasswordPage />} />

          <Route element={<RequireAuth />}>
            <Route path="/" element={<DashboardPage />} />
            <Route path="/change-password" element={<ChangePasswordPage />} />
            <Route path="/account" element={<AccountPage />} />
            <Route element={<RequireAdmin />}>
              <Route path="/admin/users" element={<UsersPage />} />
            </Route>
          </Route>

          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  );
}
