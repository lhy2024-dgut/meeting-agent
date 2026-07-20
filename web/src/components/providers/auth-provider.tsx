"use client";

import { createContext, ReactNode, useContext, useEffect, useState } from "react";
import { usePathname, useRouter } from "next/navigation";

import { CurrentUser } from "@/types/api";
import {
  clearAuthTokens,
  getAccessTokenClient,
  getRefreshTokenClient,
  isAuthPath,
  setAuthTokens,
} from "@/lib/auth";
import { loginUser, logoutUser, registerUser } from "@/lib/api";

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000/api";

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

async function fetchCurrentUser(token?: string | null): Promise<CurrentUser | null> {
  try {
    const headers = new Headers();
    if (token) {
      headers.set("Authorization", `Bearer ${token}`);
    }
    const res = await fetch(`${API_BASE_URL}/auth/me`, {
      headers,
      cache: "no-store",
    });
    if (!res.ok) return null;
    return (await res.json()) as CurrentUser;
  } catch {
    return null;
  }
}

async function silentRefresh(): Promise<string | null> {
  const refreshToken = getRefreshTokenClient();
  if (!refreshToken) return null;
  try {
    const res = await fetch(`${API_BASE_URL}/auth/refresh`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: refreshToken }),
      cache: "no-store",
    });
    if (!res.ok) return null;
    const data = (await res.json()) as { access_token?: string; refresh_token?: string };
    if (!data.access_token || !data.refresh_token) return null;
    setAuthTokens(data.access_token, data.refresh_token);
    return data.access_token;
  } catch {
    return null;
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [user, setUser] = useState<CurrentUser | null>(null);
  const [loading, setLoading] = useState(true);

  async function refreshUser() {
    setLoading(true);

    let token = getAccessTokenClient();
    let currentUser = await fetchCurrentUser(token);

    if (!currentUser) {
      const newToken = await silentRefresh();
      if (newToken) {
        token = newToken;
        currentUser = await fetchCurrentUser(token);
      }
    }

    if (!currentUser) {
      clearAuthTokens();
      setUser(null);
      setLoading(false);
      if (pathname && !isAuthPath(pathname)) {
        router.replace(`/login?next=${encodeURIComponent(pathname)}`);
      }
      return;
    }

    setUser(currentUser);
    setLoading(false);
    if (pathname && isAuthPath(pathname)) {
      router.replace("/");
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
