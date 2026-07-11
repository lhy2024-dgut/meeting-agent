"use client";

import { getAccessTokenClient } from "@/lib/auth";
import { getApiBaseUrl } from "@/lib/api";

type ApiErrorPayload = {
  detail?: string | string[] | Record<string, unknown>;
  message?: string;
};

function formatBrowserError(payload: ApiErrorPayload | null, status: number): string {
  if (!payload) {
    return `API request failed: ${status}`;
  }
  if (typeof payload.detail === "string" && payload.detail.trim()) {
    return payload.detail;
  }
  if (Array.isArray(payload.detail) && payload.detail.length > 0) {
    return payload.detail.map((item) => String(item)).join("; ");
  }
  if (typeof payload.message === "string" && payload.message.trim()) {
    return payload.message;
  }
  return `API request failed: ${status}`;
}

async function parseBrowserError(response: Response): Promise<ApiErrorPayload | null> {
  const contentType = response.headers.get("content-type") ?? "";
  try {
    if (contentType.includes("application/json")) {
      return (await response.json()) as ApiErrorPayload;
    }
    const text = await response.text();
    if (text.trim()) {
      return { detail: text };
    }
  } catch {
    return null;
  }
  return null;
}

export async function requestBrowserJson<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers ?? {});
  const token = getAccessTokenClient();
  if (token && !headers.has("Authorization")) {
    headers.set("Authorization", `Bearer ${token}`);
  }

  const response = await fetch(`${getApiBaseUrl()}${path}`, {
    ...init,
    cache: "no-store",
    headers,
  });

  if (!response.ok) {
    const payload = await parseBrowserError(response);
    throw new Error(formatBrowserError(payload, response.status));
  }

  return response.json() as Promise<T>;
}
