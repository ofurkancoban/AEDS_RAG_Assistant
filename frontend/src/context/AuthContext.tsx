import React, { createContext, useCallback, useContext, useEffect, useState } from 'react';
import { Identity, createGuestSession, getMe, login as apiLogin } from '../api/client';

interface AuthContextValue {
  /** The identity the backend says we are acting as - guest or registered. */
  identity: Identity | null;
  email: string | null;
  role: 'admin' | 'user' | null;
  /** True only for a registered account; a guest session is not "logged in". */
  isAuthenticated: boolean;
  isAdmin: boolean;
  isGuest: boolean;
  /** How to name the current session on screen: a staff email, or a short
      anonymous session id so a visitor can still refer to their own session. */
  sessionLabel: string | null;
  /** False until a session has been established, so views can wait for it. */
  isReady: boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

const TOKEN_KEY = 'access_token';

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [identity, setIdentity] = useState<Identity | null>(null);
  const [isReady, setIsReady] = useState(false);

  /** Mints a new anonymous identity and adopts it. */
  const startGuestSession = useCallback(async () => {
    const { access_token } = await createGuestSession();
    localStorage.setItem(TOKEN_KEY, access_token);
    setIdentity(await getMe());
  }, []);

  // Identity comes from the server rather than from decoding the JWT locally:
  // a local decode cannot tell an expired token from a valid one, so a stale
  // token left the UI convinced it was still signed in while every request
  // 401'd.
  useEffect(() => {
    let cancelled = false;

    (async () => {
      try {
        if (localStorage.getItem(TOKEN_KEY)) {
          try {
            const me = await getMe();
            if (!cancelled) setIdentity(me);
            return;
          } catch {
            // Token no longer usable - start over as a guest rather than
            // leaving the visitor stuck with a dead session.
            localStorage.removeItem(TOKEN_KEY);
          }
        }
        await startGuestSession();
      } catch (e) {
        console.error('Could not establish a session:', e);
      } finally {
        if (!cancelled) setIsReady(true);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [startGuestSession]);

  async function login(emailInput: string, password: string) {
    const { access_token } = await apiLogin(emailInput, password);
    localStorage.setItem(TOKEN_KEY, access_token);
    setIdentity(await getMe());
  }

  async function logout() {
    // Signing out returns the visitor to anonymous use rather than to a
    // broken tokenless state - and to a *new* guest identity, so whoever uses
    // this browser next does not inherit the previous account's threads.
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem('account_email');
    setIdentity(null);
    try {
      await startGuestSession();
    } catch (e) {
      console.error('Could not start a guest session after logout:', e);
    }
  }

  const value: AuthContextValue = {
    identity,
    email: identity && !identity.is_guest ? identity.email : null,
    role: identity?.role ?? null,
    isAuthenticated: Boolean(identity && !identity.is_guest),
    isAdmin: identity?.role === 'admin' && !identity.is_guest,
    isGuest: Boolean(identity?.is_guest),
    // Guest addresses are "guest-<uuid>@aeds.local"; the first block of the
    // uuid is short enough to read out and unique enough to identify a
    // session, without implying the visitor has an account.
    sessionLabel: identity
      ? identity.is_guest
        ? `Session ${identity.email.slice(6, 14)}`
        : identity.email
      : null,
    isReady,
    login,
    logout,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) throw new Error('useAuth must be used within AuthProvider');
  return context;
}
