"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import * as api from "@/lib/api/client";
import type { User } from "@/lib/api/types";

/**
 * Session state for the cookie session.
 *
 * The cookie is HttpOnly, so the frontend cannot see it: on load it asks
 * `GET /api/auth/session` and trusts the answer. Nothing is kept in
 * localStorage. A 401 from any later call flips the state to signed out,
 * and the route guard sends the user to /login with a return URL.
 */
export type AuthStatus = "loading" | "signedIn" | "signedOut";

interface AuthState {
  status: AuthStatus;
  user: User | null;
  /** True when a session that was working got rejected, so login can say why. */
  expired: boolean;
}

interface AuthContextValue extends AuthState {
  signIn: (email: string, password: string) => Promise<User>;
  signOut: () => Promise<void>;
  changePassword: (current: string, next: string) => Promise<User>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const queryClient = useQueryClient();
  const [state, setState] = useState<AuthState>({ status: "loading", user: null, expired: false });

  useEffect(() => {
    api.setAuthHandlers({
      onUnauthorized: () => {
        setState((prev) =>
          prev.status === "signedOut" ? prev : { status: "signedOut", user: null, expired: prev.status === "signedIn" },
        );
        queryClient.clear();
      },
      onPasswordChangeRequired: () => {
        setState((prev) => (prev.user ? { ...prev, user: { ...prev.user, must_change_password: true } } : prev));
      },
    });
    return () => api.setAuthHandlers({});
  }, [queryClient]);

  useEffect(() => {
    let cancelled = false;
    api
      .getSession()
      .then(({ user }) => {
        if (!cancelled) setState({ status: "signedIn", user, expired: false });
      })
      .catch(() => {
        // 401 (not signed in) and a network failure both end at the login screen.
        if (!cancelled) setState({ status: "signedOut", user: null, expired: false });
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const signIn = useCallback(
    async (email: string, password: string) => {
      const { user } = await api.login(email, password);
      queryClient.clear();
      setState({ status: "signedIn", user, expired: false });
      return user;
    },
    [queryClient],
  );

  const signOut = useCallback(async () => {
    // Clear locally whatever the server says: a failed call must not leave
    // the user apparently signed in.
    try {
      await api.logout();
    } catch {
      /* the session is already gone */
    }
    queryClient.clear();
    setState({ status: "signedOut", user: null, expired: false });
  }, [queryClient]);

  const changePassword = useCallback(async (current: string, next: string) => {
    const { user } = await api.changePassword(current, next);
    setState({ status: "signedIn", user, expired: false });
    return user;
  }, []);

  const value = useMemo(
    () => ({ ...state, signIn, signOut, changePassword }),
    [state, signIn, signOut, changePassword],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const value = useContext(AuthContext);
  if (!value) throw new Error("useAuth must be used inside <AuthProvider>");
  return value;
}
