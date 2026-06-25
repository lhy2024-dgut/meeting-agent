const ACCESS_TOKEN_COOKIE = "meeting_agent_access_token";
const REFRESH_TOKEN_COOKIE = "meeting_agent_refresh_token";
const COOKIE_MAX_AGE_SECONDS = 60 * 60 * 24 * 30;

function setCookie(name: string, value: string, maxAgeSeconds = COOKIE_MAX_AGE_SECONDS) {
  if (typeof document === "undefined") return;
  document.cookie = `${name}=${encodeURIComponent(value)}; Path=/; Max-Age=${maxAgeSeconds}; SameSite=Lax`;
}

function getCookie(name: string): string | null {
  if (typeof document === "undefined") return null;
  const prefix = `${name}=`;
  const match = document.cookie
    .split("; ")
    .find((entry) => entry.startsWith(prefix));
  return match ? decodeURIComponent(match.slice(prefix.length)) : null;
}

function deleteCookie(name: string) {
  if (typeof document === "undefined") return;
  document.cookie = `${name}=; Path=/; Max-Age=0; SameSite=Lax`;
}

export function setAuthTokens(accessToken: string, refreshToken: string) {
  setCookie(ACCESS_TOKEN_COOKIE, accessToken);
  setCookie(REFRESH_TOKEN_COOKIE, refreshToken);
}

export function clearAuthTokens() {
  deleteCookie(ACCESS_TOKEN_COOKIE);
  deleteCookie(REFRESH_TOKEN_COOKIE);
}

export function getAccessTokenClient(): string | null {
  return getCookie(ACCESS_TOKEN_COOKIE);
}

export function getRefreshTokenClient(): string | null {
  return getCookie(REFRESH_TOKEN_COOKIE);
}

export async function getAccessToken(): Promise<string | null> {
  if (typeof window !== "undefined") {
    return getAccessTokenClient();
  }

  try {
    const { cookies } = await import("next/headers");
    const store = await cookies();
    return store.get(ACCESS_TOKEN_COOKIE)?.value ?? null;
  } catch {
    return null;
  }
}

export async function getRefreshToken(): Promise<string | null> {
  if (typeof window !== "undefined") {
    return getRefreshTokenClient();
  }

  try {
    const { cookies } = await import("next/headers");
    const store = await cookies();
    return store.get(REFRESH_TOKEN_COOKIE)?.value ?? null;
  } catch {
    return null;
  }
}

export function isAuthPath(pathname: string): boolean {
  return pathname === "/login" || pathname === "/register";
}

export function getAuthCookieNames() {
  return {
    access: ACCESS_TOKEN_COOKIE,
    refresh: REFRESH_TOKEN_COOKIE,
  };
}
