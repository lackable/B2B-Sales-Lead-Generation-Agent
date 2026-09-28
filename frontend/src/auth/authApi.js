import { apiJson } from '../lib/http';

/** Public bootstrap/recovery calls skip the 401 redirect — they are not failures. */
export const fetchSetupStatus = () => apiJson('/auth/setup-status', { skipAuthRedirect: true });

export const setupAdmin = (username, password) =>
  apiJson('/auth/setup', { method: 'POST', json: { username, password }, skipAuthRedirect: true });

export const login = (username, password) =>
  apiJson('/auth/login', { method: 'POST', json: { username, password }, skipAuthRedirect: true });

export const logout = () => apiJson('/auth/logout', { method: 'POST' });

export const fetchMe = () => apiJson('/auth/me', { skipAuthRedirect: true });

export const changePassword = (currentPassword, newPassword) =>
  apiJson('/auth/password/change', {
    method: 'POST',
    json: { current_password: currentPassword, new_password: newPassword },
  });

export const resetPassword = (username, recoveryCode, newPassword) =>
  apiJson('/auth/password/reset', {
    method: 'POST',
    json: { username, recovery_code: recoveryCode, new_password: newPassword },
    skipAuthRedirect: true,
  });

export const regenerateRecoveryCode = (password) =>
  apiJson('/auth/recovery-code/regenerate', { method: 'POST', json: { password } });

export const listUsers = () => apiJson('/admin/users');

export const createUser = (username, role) =>
  apiJson('/admin/users', { method: 'POST', json: { username, role } });

export const updateUser = (userId, patch) =>
  apiJson(`/admin/users/${userId}`, { method: 'PATCH', json: patch });

export const revokeUserSessions = (userId) =>
  apiJson(`/admin/users/${userId}/revoke-sessions`, { method: 'POST' });
