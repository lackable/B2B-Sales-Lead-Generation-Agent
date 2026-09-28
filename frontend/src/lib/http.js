import API from '../api';

/**
 * ApiError — thrown by apiJson when the backend answers with a non-2xx status.
 * `status` carries the HTTP code so callers can react (403, 409, ...).
 */
export class ApiError extends Error {
  constructor(message, status) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
}

// AuthProvider registers a handler here so an expired session drops the user
// instead of leaving the UI stuck on a spinner.
let unauthorizedHandler = null;

export function setUnauthorizedHandler(handler) {
  unauthorizedHandler = handler;
}

/**
 * apiFetch — every backend call goes through here.
 *
 *  • sends the session cookie (`credentials: 'include'`)
 *  • serializes `json` and sets the content type
 *  • reports 401s to the auth layer, which routes back to /login
 */
export async function apiFetch(path, options = {}) {
  const { json, headers, skipAuthRedirect = false, ...rest } = options;

  const init = {
    credentials: 'include',
    ...rest,
    headers: { ...headers },
  };

  if (json !== undefined) {
    init.body = JSON.stringify(json);
    init.headers['Content-Type'] = 'application/json';
  }

  const response = await fetch(`${API}${path}`, init);

  if (response.status === 401 && !skipAuthRedirect) {
    unauthorizedHandler?.();
  }

  return response;
}

/** apiJson — apiFetch plus JSON parsing and `{detail}` error messages. */
export async function apiJson(path, options) {
  const response = await apiFetch(path, options);
  const data = await response.json().catch(() => ({}));

  if (!response.ok) {
    throw new ApiError(data.detail ?? `HTTP ${response.status}`, response.status);
  }

  return data;
}
