import { APIRequestContext, expect, Page } from "@playwright/test";

const WEB_BASE_URL = process.env.PLAYWRIGHT_BASE_URL || "http://127.0.0.1:3000";
const API_BASE_URL =
  process.env.PLAYWRIGHT_API_BASE_URL || "http://127.0.0.1:8000";
const ACCESS_TOKEN_COOKIE = "meeting_agent_access_token";
const REFRESH_TOKEN_COOKIE = "meeting_agent_refresh_token";

const USE_ADMIN_ACCOUNT =
  (process.env.PLAYWRIGHT_E2E_USE_ADMIN || "true").toLowerCase() !== "false";

const TEST_USER = {
  username: process.env.PLAYWRIGHT_E2E_USERNAME || (USE_ADMIN_ACCOUNT ? "admin" : "e2e_user"),
  email:
    process.env.PLAYWRIGHT_E2E_EMAIL ||
    (USE_ADMIN_ACCOUNT ? "admin@example.com" : "e2e_user@example.com"),
  password:
    process.env.PLAYWRIGHT_E2E_PASSWORD ||
    (USE_ADMIN_ACCOUNT ? "ChangeMe123!" : "StrongPass123"),
  display_name: USE_ADMIN_ACCOUNT ? "Administrator" : "E2E User",
};

type AuthTokens = {
  access_token: string;
  refresh_token: string;
};

let authPromise: Promise<AuthTokens> | null = null;

async function sleep(ms: number) {
  await new Promise((resolve) => setTimeout(resolve, ms));
}

async function fetchJson(
  path: string,
  init?: RequestInit,
  expectedStatuses: number[] = [200],
) {
  const response = await fetch(`${API_BASE_URL}${path}`, init);
  if (!expectedStatuses.includes(response.status)) {
    const text = await response.text();
    throw new Error(`Request failed: ${response.status} ${path} ${text}`);
  }
  if (response.status === 204) {
    return null;
  }
  return response.json();
}

async function createTestUserIfNeeded() {
  if (USE_ADMIN_ACCOUNT) {
    return;
  }
  await fetchJson(
    "/api/auth/register",
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(TEST_USER),
    },
    [201, 409],
  );
}

async function loginTestUser(): Promise<AuthTokens> {
  return (await fetchJson("/api/auth/login", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      login: TEST_USER.username,
      password: TEST_USER.password,
    }),
  })) as AuthTokens;
}

async function ensureAuthTokens(): Promise<AuthTokens> {
  if (!authPromise) {
    authPromise = (async () => {
      let lastError: unknown = null;
      for (let attempt = 0; attempt < 10; attempt += 1) {
        try {
          return await loginTestUser();
        } catch (error) {
          lastError = error;
          try {
            await createTestUserIfNeeded();
            return await loginTestUser();
          } catch (registerError) {
            lastError = registerError;
          }
          await sleep(1000);
        }
      }
      throw lastError instanceof Error ? lastError : new Error("Failed to create E2E auth session");
    })();
  }

  return authPromise;
}

export async function getAuthHeaders(): Promise<Record<string, string>> {
  const tokens = await ensureAuthTokens();
  return {
    Authorization: `Bearer ${tokens.access_token}`,
  };
}

async function ensureLoggedIn(page: Page) {
  const tokens = await ensureAuthTokens();
  await page.context().addCookies([
    {
      name: ACCESS_TOKEN_COOKIE,
      value: tokens.access_token,
      url: WEB_BASE_URL,
      sameSite: "Lax",
    },
    {
      name: REFRESH_TOKEN_COOKIE,
      value: tokens.refresh_token,
      url: WEB_BASE_URL,
      sameSite: "Lax",
    },
  ]);
}

export async function waitForAppReady(page: Page, path: string) {
  await ensureLoggedIn(page);
  await page.goto(path, { waitUntil: "domcontentloaded" });
  await page.waitForLoadState("networkidle", { timeout: 30_000 }).catch(() => undefined);
  await page.waitForTimeout(500);
}

export async function waitForApiMeeting(request: APIRequestContext, meetingId: number) {
  const response = await request.get(`${API_BASE_URL}/api/meetings/${meetingId}`, {
    headers: await getAuthHeaders(),
  });
  expect(response.ok()).toBeTruthy();
  return response.json();
}

export async function waitForEnabledTextarea(page: Page, placeholderText: string) {
  const textarea = page.getByPlaceholder(placeholderText);
  await expect(textarea).toBeVisible();
  await expect(textarea).toBeEnabled({ timeout: 30_000 });
  return textarea;
}

export async function waitForApiJson<T>(
  request: APIRequestContext,
  path: string,
): Promise<T> {
  const response = await request.get(`${API_BASE_URL}${path}`, {
    headers: await getAuthHeaders(),
  });
  expect(response.ok()).toBeTruthy();
  return response.json() as Promise<T>;
}

export async function waitForApiDelete(
  request: APIRequestContext,
  meetingId: number,
): Promise<boolean> {
  const response = await request.get(`${API_BASE_URL}/api/meetings/${meetingId}`, {
    headers: await getAuthHeaders(),
  });
  return response.status() === 404;
}

export async function waitForMeetingByTitle<T extends { items: Array<{ title: string }> }>(
  request: APIRequestContext,
  title: string,
): Promise<T> {
  const response = await request.get(
    `${API_BASE_URL}/api/meetings?page=0&page_size=50&search=${encodeURIComponent(title)}`,
    {
      headers: await getAuthHeaders(),
    },
  );
  expect(response.ok()).toBeTruthy();
  return response.json() as Promise<T>;
}
