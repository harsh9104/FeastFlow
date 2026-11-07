import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { api, setUnauthorizedHandler, tokenStore } from "../api/client";
import type { Tier, User } from "../api/types";

interface AuthState {
  user: User | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<User>;
  register: (full_name: string, email: string, password: string, tier: Tier) => Promise<void>;
  logout: () => void;
  setTier: (tier: Tier) => Promise<void>;
}

const Ctx = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(!!tokenStore.get());

  const logout = useCallback(() => {
    tokenStore.clear();
    setUser(null);
  }, []);

  useEffect(() => {
    setUnauthorizedHandler(logout);
    if (!tokenStore.get()) return;
    api<User>("/users/me")
      .then(setUser)
      .catch(logout)
      .finally(() => setLoading(false));
  }, [logout]);

  const value = useMemo<AuthState>(
    () => ({
      user,
      loading,
      logout,
      async login(email, password) {
        const r = await api<{ access_token: string; user: User }>("/auth/login", {
          method: "POST",
          body: { email, password },
        });
        tokenStore.set(r.access_token);
        setUser(r.user);
        return r.user;
      },
      async register(full_name, email, password, subscription_tier) {
        await api("/auth/register", {
          method: "POST",
          body: { full_name, email, password, subscription_tier },
        });
      },
      async setTier(tier) {
        const u = await api<User>("/users/me/subscription", {
          method: "PATCH",
          body: { subscription_tier: tier },
        });
        setUser(u);
      },
    }),
    [user, loading, logout],
  );
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useAuth() {
  const v = useContext(Ctx);
  if (!v) throw new Error("useAuth outside AuthProvider");
  return v;
}
