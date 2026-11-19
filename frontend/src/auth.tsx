import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { api, setUnauthorizedHandler, tokenStore } from "./api";
import type { TokenOut, User } from "./api";

interface AuthState {
  user: User | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<User>;
  register: (name: string, email: string, password: string) => Promise<User>;
  logout: () => void;
  /** Store a fresh token + user (e.g. after subscribing to Prime). */
  applyToken: (t: TokenOut) => void;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  const logout = useCallback(() => {
    tokenStore.set(null);
    setUser(null);
  }, []);

  const applyToken = useCallback((t: TokenOut) => {
    tokenStore.set(t.access_token);
    setUser(t.user);
  }, []);

  useEffect(() => {
    setUnauthorizedHandler(logout);
    // Re-read the user on load: Prime may have expired since the token was issued.
    if (!tokenStore.get()) {
      setLoading(false);
      return;
    }
    api<User>("/api/users/me")
      .then(setUser)
      .catch(() => logout())
      .finally(() => setLoading(false));
  }, [logout]);

  const value = useMemo<AuthState>(
    () => ({
      user,
      loading,
      logout,
      applyToken,
      async login(email, password) {
        const t = await api<TokenOut>("/api/auth/login", {
          method: "POST",
          body: { email, password },
        });
        applyToken(t);
        return t.user;
      },
      async register(name, email, password) {
        const t = await api<TokenOut>("/api/auth/register", {
          method: "POST",
          body: { name, email, password },
        });
        applyToken(t);
        return t.user;
      },
    }),
    [user, loading, logout, applyToken],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth outside AuthProvider");
  return ctx;
}
