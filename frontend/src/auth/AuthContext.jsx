import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import { setUnauthorizedHandler } from '../lib/http';
import * as authApi from './authApi';

const AuthContext = createContext(null);

/**
 * AuthProvider — owns the session: who is signed in, whether the first-run
 * setup is still pending, and an "expired" flag for the login screen.
 */
export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [needsSetup, setNeedsSetup] = useState(false);
  const [loading, setLoading] = useState(true);
  const [expired, setExpired] = useState(false);

  const refresh = useCallback(async () => {
    try {
      const status = await authApi.fetchSetupStatus();
      setNeedsSetup(status.needs_setup);

      if (status.needs_setup) {
        setUser(null);
        return;
      }

      try {
        setUser(await authApi.fetchMe());
        setExpired(false);
      } catch {
        setUser(null);
      }
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  useEffect(() => {
    setUnauthorizedHandler(() => {
      setUser(null);
      setExpired(true);
    });
    return () => setUnauthorizedHandler(null);
  }, []);

  const signIn = useCallback(async (username, password) => {
    const authenticated = await authApi.login(username, password);
    setUser(authenticated);
    setNeedsSetup(false);
    setExpired(false);
    return authenticated;
  }, []);

  const signOut = useCallback(async () => {
    try {
      await authApi.logout();
    } catch {
      // The cookie may already be gone; the local state is what matters.
    }
    setUser(null);
    setExpired(false);
  }, []);

  const completeSetup = useCallback(async (username, password) => {
    const result = await authApi.setupAdmin(username, password);
    setUser(result.user);
    setNeedsSetup(false);
    return result;
  }, []);

  const value = useMemo(
    () => ({ user, needsSetup, loading, expired, signIn, signOut, completeSetup, refresh, setUser }),
    [user, needsSetup, loading, expired, signIn, signOut, completeSetup, refresh],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used inside an AuthProvider');
  }
  return context;
}
