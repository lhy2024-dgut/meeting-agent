"use client";

import { createContext, ReactNode, useContext, useEffect, useState } from "react";
import { usePathname, useRouter } from "next/navigation";

import { CurrentUser } from "@/types/api";
import { clearAuthTokens, isAuthPath, setAuthTokens } from "@/lib/auth";
import { getCurrentUser, loginUser, logoutUser, registerUser } from "@/lib/api";

type AuthContextValue = {
  user: CurrentUser | null;
  loading: boolean;
  authenticated: boolean;
  login: (payload: { login: string; password: string }) => Promise<void>;
  register: (payload: {
    username: string;
    email: string;
    password: string;
    display_name?: string;
  }) => Promise<void>;
  logout: () => Promise<void>;
  refreshUser: () => Promise<void>;
};

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [user, setUser] = useState<CurrentUser | null>(null);
  const [loading, setLoading] = useState(true);

  async function refreshUser() {
    setLoading(true);
    try {
      const nextUser = await getCurrentUser();
      setUser(nextUser);
      if (pathname && isAuthPath(pathname)) {
        router.replace("/");
      }
    } catch {
      clearAuthTokens();
      setUser(null);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    const timer = window.setTimeout(() => {
      void refreshUser();
    }, 0);
    return () => window.clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pathname]);

  async function login(payload: { login: string; password: string }) {
    const tokens = await loginUser(payload);
    setAuthTokens(tokens.access_token, tokens.refresh_token);
    await refreshUser();
  }

  async function register(payload: {
    username: string;
    email: string;
    password: string;
    display_name?: string;
  }) {
    await registerUser(payload);
    await login({ login: payload.username, password: payload.password });
  }

  async function logout() {
    try {
      await logoutUser();
    } catch {
      // Ignore logout API errors; local session cleanup is sufficient.
    } finally {
      clearAuthTokens();
      await refreshUser();
      router.replace("/");
    }
  }

  const value: AuthContextValue = {
    user,
    loading,
    authenticated: Boolean(user),
    login,
    register,
    logout,
    refreshUser,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within AuthProvider");
  }
  return context;
}
