import {
  AuthTokenResponse,
  ChatMessageResponse,
  ChatSessionCreateResponse,
  Contact,
  ContactGroup,
  ContactGroupListResponse,
  ContactListResponse,
  CurrentUser,
  CreateJobResponse,
  EmailLogListResponse,
  HtmlSummaryGenerateRequest,
  HtmlSummaryResponse,
  JobStatusResponse,
  MeetingEmailSendRequest,
  MeetingEmailSendResponse,
  MeetingDetail,
  MeetingListResponse,
  MeetingMutationResponse,
  MeetingTermsResponse,
  RealtimeSessionCreateRequest,
  RealtimeSessionMutationResponse,
  RealtimeSessionResponse,
  SmtpTestResponse,
  StatsOverviewResponse,
  TodoItem,
  TodoListResponse,
  TodoStatusLogsResponse,
  TranscriptResponse,
  UploadMetadataResponse,
  UserSmtpSettings,
} from "@/types/api";
import {
  clearAuthTokens,
  getAccessToken,
  getRefreshToken,
  setAuthTokens,
} from "@/lib/auth";

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000/api";

const DEFAULT_TIMEOUT_MS = 15_000;
const CHAT_REQUEST_TIMEOUT_MS = 90_000;
const AUTH_IGNORED_PATHS = new Set([
  "/auth/login",
  "/auth/register",
  "/auth/refresh",
]);
let refreshPromise: Promise<string | null> | null = null;

export type ApiRequestOptions = {
  signal?: AbortSignal;
  timeoutMs?: number;
};

type ApiErrorPayload = {
  detail?: string | string[] | Record<string, unknown>;
  message?: string;
  code?: string;
  details?: unknown;
};

export class ApiError extends Error {
  status: number;
  code?: string;
  details?: unknown;
  isAbort: boolean;
  isTimeout: boolean;

  constructor(options: {
    message: string;
    status?: number;
    code?: string;
    details?: unknown;
    isAbort?: boolean;
    isTimeout?: boolean;
  }) {
    super(options.message);
    this.name = "ApiError";
    this.status = options.status ?? 0;
    this.code = options.code;
    this.details = options.details;
    this.isAbort = options.isAbort ?? false;
    this.isTimeout = options.isTimeout ?? false;
  }
}

export function getApiBaseUrl(): string {
  return API_BASE_URL;
}

async function resolveHeaders(initHeaders?: HeadersInit): Promise<Headers> {
  const headers = new Headers(initHeaders ?? {});
  const token = await getAccessToken();
  if (token && !headers.has("Authorization")) {
    headers.set("Authorization", `Bearer ${token}`);
  }
  return headers;
}

async function tryRefreshAccessToken(): Promise<string | null> {
  if (typeof window === "undefined") {
    return null;
  }

  if (!refreshPromise) {
    refreshPromise = (async () => {
      const refreshToken = await getRefreshToken();
      if (!refreshToken) {
        return null;
      }

      const response = await fetch(`${API_BASE_URL}/auth/refresh`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ refresh_token: refreshToken }),
      });

      if (!response.ok) {
        return null;
      }

      const payload = (await response.json()) as AuthTokenResponse;
      if (!payload.access_token || !payload.refresh_token) {
        return null;
      }

      setAuthTokens(payload.access_token, payload.refresh_token);
      return payload.access_token;
    })().finally(() => {
      refreshPromise = null;
    });
  }

  return refreshPromise;
}

async function handleUnauthorized(path: string) {
  if (AUTH_IGNORED_PATHS.has(path)) {
    return;
  }

  clearAuthTokens();

  if (typeof window !== "undefined") {
    if (window.location.pathname !== "/login") {
      const next = encodeURIComponent(window.location.pathname + window.location.search);
      window.location.href = `/login?next=${next}`;
    }
    return;
  }

  const { redirect } = await import("next/navigation");
  redirect("/login");
}

function formatErrorMessage(payload: ApiErrorPayload | null, status: number): string {
  if (!payload) {
    return `API request failed: ${status}`;
  }

  if (typeof payload.detail === "string" && payload.detail.trim()) {
    return payload.detail;
  }

  if (Array.isArray(payload.detail) && payload.detail.length > 0) {
    return payload.detail
      .map((item) => {
        if (typeof item === "string") return item;
        if (item && typeof item === "object") {
          const detailItem = item as { msg?: unknown };
          if (detailItem.msg !== undefined) {
            return String(detailItem.msg);
          }
        }
        return JSON.stringify(item);
      })
      .join("; ");
  }

  if (typeof payload.message === "string" && payload.message.trim()) {
    return payload.message;
  }

  return `API request failed: ${status}`;
}

function mergeAbortSignals(signal?: AbortSignal, timeoutSignal?: AbortSignal): AbortSignal | undefined {
  if (!signal) return timeoutSignal;
  if (!timeoutSignal) return signal;

  const controller = new AbortController();
  const abort = () => controller.abort();

  if (signal.aborted || timeoutSignal.aborted) {
    controller.abort();
    return controller.signal;
  }

  signal.addEventListener("abort", abort, { once: true });
  timeoutSignal.addEventListener("abort", abort, { once: true });
  return controller.signal;
}

async function parseErrorPayload(response: Response): Promise<ApiErrorPayload | null> {
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

async function requestJson<T>(
  path: string,
  init: RequestInit = {},
  options: ApiRequestOptions = {},
  retryAfterRefresh = true,
): Promise<T> {
  const timeoutMs = options.timeoutMs ?? DEFAULT_TIMEOUT_MS;
  const timeoutController = new AbortController();
  const timer = setTimeout(() => timeoutController.abort(), timeoutMs);
  const signal = mergeAbortSignals(options.signal, timeoutController.signal);

  try {
    const headers = await resolveHeaders(init.headers);
    const response = await fetch(`${API_BASE_URL}${path}`, {
      ...init,
      cache: "no-store",
      signal,
      headers,
    });

    if (!response.ok) {
      if (response.status === 401 && retryAfterRefresh && !AUTH_IGNORED_PATHS.has(path)) {
        const refreshedToken = await tryRefreshAccessToken();
        if (refreshedToken) {
          return requestJson<T>(path, init, options, false);
        }
      }
      if (response.status === 401) {
        await handleUnauthorized(path);
      }
      const payload = await parseErrorPayload(response);
      throw new ApiError({
        message: formatErrorMessage(payload, response.status),
        status: response.status,
        code: payload?.code,
        details: payload?.details ?? payload?.detail,
      });
    }

    return response.json() as Promise<T>;
  } catch (error) {
    if (
      typeof window === "undefined" &&
      error &&
      typeof error === "object" &&
      "digest" in error &&
      String(error.digest).startsWith("NEXT_REDIRECT")
    ) {
      throw error;
    }
    if (error instanceof ApiError) {
      throw error;
    }

    if (error instanceof DOMException && error.name === "AbortError") {
      const isUserAbort = options.signal?.aborted === true;
      throw new ApiError({
        message: isUserAbort ? "\u8bf7\u6c42\u5df2\u53d6\u6d88" : `\u8bf7\u6c42\u8d85\u65f6\uff08>${timeoutMs}ms\uff09`, 
        isAbort: isUserAbort,
        isTimeout: !isUserAbort,
      });
    }

    throw new ApiError({
      message: error instanceof Error ? error.message : "\u8bf7\u6c42\u5931\u8d25",
    });
  } finally {
    clearTimeout(timer);
  }
}

export function getMeetings(
  params?: {
    page?: number;
    pageSize?: number;
    search?: string;
    duration?: string;
    environment?: string;
  },
  options?: ApiRequestOptions,
): Promise<MeetingListResponse> {
  const searchParams = new URLSearchParams();
  if (params?.page !== undefined) searchParams.set("page", String(params.page));
  if (params?.pageSize !== undefined) {
    searchParams.set("page_size", String(params.pageSize));
  }
  if (params?.search) searchParams.set("search", params.search);
  if (params?.duration) searchParams.set("duration", params.duration);
  if (params?.environment) searchParams.set("environment", params.environment);

  const suffix = searchParams.toString();
  return requestJson<MeetingListResponse>(
    `/meetings${suffix ? `?${suffix}` : ""}`,
    {},
    options,
  );
}

export function registerUser(
  payload: {
    username: string;
    email: string;
    password: string;
    display_name?: string;
  },
  options?: ApiRequestOptions,
): Promise<CurrentUser> {
  return requestJson<CurrentUser>(
    "/auth/register",
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
    },
    options,
  );
}

export function loginUser(
  payload: { login: string; password: string },
  options?: ApiRequestOptions,
): Promise<AuthTokenResponse> {
  return requestJson<AuthTokenResponse>(
    "/auth/login",
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
    },
    options,
  );
}

export function refreshAccessToken(
  refreshToken: string,
  options?: ApiRequestOptions,
): Promise<AuthTokenResponse> {
  return requestJson<AuthTokenResponse>(
    "/auth/refresh",
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ refresh_token: refreshToken }),
    },
    options,
  );
}

export function getCurrentUser(options?: ApiRequestOptions): Promise<CurrentUser> {
  return requestJson<CurrentUser>("/auth/me", {}, options);
}

export function updateCurrentUserProfile(
  payload: { display_name: string },
  options?: ApiRequestOptions,
): Promise<CurrentUser> {
  return requestJson<CurrentUser>(
    "/auth/profile",
    {
      method: "PATCH",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
    },
    options,
  );
}

export function changeCurrentUserPassword(
  payload: { current_password: string; new_password: string },
  options?: ApiRequestOptions,
): Promise<MeetingMutationResponse> {
  return requestJson<MeetingMutationResponse>(
    "/auth/password",
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
    },
    options,
  );
}

export function getCurrentUserSmtpSettings(
  options?: ApiRequestOptions,
): Promise<UserSmtpSettings> {
  return requestJson<UserSmtpSettings>("/auth/smtp", {}, options);
}

export function updateCurrentUserSmtpSettings(
  payload: { smtp_host: string; smtp_port: number; smtp_password?: string },
  options?: ApiRequestOptions,
): Promise<UserSmtpSettings> {
  return requestJson<UserSmtpSettings>(
    "/auth/smtp",
    {
      method: "PUT",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
    },
    options,
  );
}

export function testCurrentUserSmtpSettings(
  payload: { recipient_email?: string } = {},
  options?: ApiRequestOptions,
): Promise<SmtpTestResponse> {
  return requestJson<SmtpTestResponse>(
    "/auth/smtp/test",
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
    },
    options,
  );
}

export function logoutUser(options?: ApiRequestOptions): Promise<MeetingMutationResponse> {
  return requestJson<MeetingMutationResponse>(
    "/auth/logout",
    {
      method: "POST",
    },
    options,
  );
}

export function getMeeting(
  meetingId: string | number,
  options?: ApiRequestOptions,
): Promise<MeetingDetail> {
  return requestJson<MeetingDetail>(`/meetings/${meetingId}`, {}, options);
}

export function updateMeetingProjectName(
  meetingId: string | number,
  projectName: string,
  options?: ApiRequestOptions,
): Promise<MeetingMutationResponse> {
  return requestJson<MeetingMutationResponse>(
    `/meetings/${meetingId}/project`,
    {
      method: "PATCH",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ project_name: projectName }),
    },
    options,
  );
}

export function deleteMeeting(
  meetingId: string | number,
  options?: ApiRequestOptions,
): Promise<MeetingMutationResponse> {
  return requestJson<MeetingMutationResponse>(
    `/meetings/${meetingId}`,
    {
      method: "DELETE",
    },
    options,
  );
}

export function getMeetingTerms(
  meetingId: string | number,
  options?: ApiRequestOptions,
): Promise<MeetingTermsResponse> {
  return requestJson<MeetingTermsResponse>(`/meetings/${meetingId}/terms`, {}, options);
}

export function regenerateMeeting(
  meetingId: string | number,
  payload: { terms?: string[] },
  options?: ApiRequestOptions,
): Promise<CreateJobResponse> {
  return requestJson<CreateJobResponse>(
    `/meetings/${meetingId}/regenerate`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
    },
    options,
  );
}

export function getTranscript(
  meetingId: string | number,
  options?: ApiRequestOptions,
): Promise<TranscriptResponse> {
  return requestJson<TranscriptResponse>(`/meetings/${meetingId}/transcript`, {}, options);
}

export function getStatsOverview(options?: ApiRequestOptions): Promise<StatsOverviewResponse> {
  return requestJson<StatsOverviewResponse>("/stats/overview", {}, options);
}

export function getTodos(
  params?: {
    meetingId?: number;
    status?: string;
    priority?: string;
    includeCancelled?: boolean;
  },
  options?: ApiRequestOptions,
): Promise<TodoListResponse> {
  const searchParams = new URLSearchParams();
  if (params?.meetingId !== undefined) searchParams.set("meeting_id", String(params.meetingId));
  if (params?.status) searchParams.set("status", params.status);
  if (params?.priority) searchParams.set("priority", params.priority);
  if (params?.includeCancelled !== undefined) {
    searchParams.set("include_cancelled", String(params.includeCancelled));
  }
  const suffix = searchParams.toString();
  return requestJson<TodoListResponse>(`/todos${suffix ? `?${suffix}` : ""}`, {}, options);
}

export function createTodo(
  meetingId: number,
  payload: {
    content: string;
    assignee?: string | null;
    due_date?: string | null;
    priority?: string;
  },
  options?: ApiRequestOptions,
): Promise<TodoItem> {
  return requestJson<TodoItem>(
    `/meetings/${meetingId}/todos`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
    },
    options,
  );
}

export function updateTodo(
  todoId: number,
  payload: {
    content?: string;
    assignee?: string | null;
    due_date?: string | null;
    priority?: string;
  },
  options?: ApiRequestOptions,
): Promise<TodoItem> {
  return requestJson<TodoItem>(
    `/todos/${todoId}`,
    {
      method: "PATCH",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
    },
    options,
  );
}

export function updateTodoStatus(
  todoId: number,
  payload: {
    status: string;
    reason?: string | null;
  },
  options?: ApiRequestOptions,
): Promise<TodoItem> {
  return requestJson<TodoItem>(
    `/todos/${todoId}/status`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
    },
    options,
  );
}

export function getTodoLogs(
  todoId: number,
  options?: ApiRequestOptions,
): Promise<TodoStatusLogsResponse> {
  return requestJson<TodoStatusLogsResponse>(`/todos/${todoId}/logs`, {}, options);
}

export function getContacts(options?: ApiRequestOptions): Promise<ContactListResponse> {
  return requestJson<ContactListResponse>("/contacts", {}, options);
}

export function createContact(
  payload: {
    name: string;
    email: string;
    note?: string;
    group_ids?: number[];
  },
  options?: ApiRequestOptions,
): Promise<Contact> {
  return requestJson<Contact>(
    "/contacts",
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
    },
    options,
  );
}

export function updateContact(
  contactId: number,
  payload: {
    name: string;
    email: string;
    note?: string;
    group_ids?: number[];
  },
  options?: ApiRequestOptions,
): Promise<Contact> {
  return requestJson<Contact>(
    `/contacts/${contactId}`,
    {
      method: "PATCH",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
    },
    options,
  );
}

export function deleteContact(
  contactId: number,
  options?: ApiRequestOptions,
): Promise<MeetingMutationResponse> {
  return requestJson<MeetingMutationResponse>(
    `/contacts/${contactId}`,
    {
      method: "DELETE",
    },
    options,
  );
}

export function getContactGroups(options?: ApiRequestOptions): Promise<ContactGroupListResponse> {
  return requestJson<ContactGroupListResponse>("/contact-groups", {}, options);
}

export function createContactGroup(
  payload: {
    group_name: string;
    member_ids?: number[];
  },
  options?: ApiRequestOptions,
): Promise<ContactGroup> {
  return requestJson<ContactGroup>(
    "/contact-groups",
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
    },
    options,
  );
}

export function updateContactGroup(
  groupId: number,
  payload: {
    group_name: string;
    member_ids?: number[];
  },
  options?: ApiRequestOptions,
): Promise<ContactGroup> {
  return requestJson<ContactGroup>(
    `/contact-groups/${groupId}`,
    {
      method: "PATCH",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
    },
    options,
  );
}

export function deleteContactGroup(
  groupId: number,
  options?: ApiRequestOptions,
): Promise<MeetingMutationResponse> {
  return requestJson<MeetingMutationResponse>(
    `/contact-groups/${groupId}`,
    {
      method: "DELETE",
    },
    options,
  );
}

export function getMeetingEmailLogs(
  meetingId: number,
  options?: ApiRequestOptions,
): Promise<EmailLogListResponse> {
  return requestJson<EmailLogListResponse>(`/meetings/${meetingId}/email-logs`, {}, options);
}

export function sendMeetingEmail(
  meetingId: number,
  payload: MeetingEmailSendRequest,
  options?: ApiRequestOptions,
): Promise<MeetingEmailSendResponse> {
  return requestJson<MeetingEmailSendResponse>(
    `/meetings/${meetingId}/emails/send`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
    },
    {
      ...options,
      timeoutMs: options?.timeoutMs ?? 120_000,
    },
  );
}

export function getUploadMetadata(
  options?: ApiRequestOptions,
): Promise<UploadMetadataResponse> {
  return requestJson<UploadMetadataResponse>("/meta/upload", {}, options);
}

export function createMeetingProcessJob(
  formData: FormData,
  options?: ApiRequestOptions,
): Promise<CreateJobResponse> {
  return requestJson<CreateJobResponse>(
    "/meetings/process",
    {
      method: "POST",
      body: formData,
    },
    options,
  );
}

export function getJob(
  jobId: string,
  options?: ApiRequestOptions,
): Promise<JobStatusResponse> {
  return requestJson<JobStatusResponse>(`/jobs/${jobId}`, {}, options);
}

export function getHtmlSummary(
  meetingId: string | number,
  options?: ApiRequestOptions,
): Promise<HtmlSummaryResponse> {
  return requestJson<HtmlSummaryResponse>(`/meetings/${meetingId}/html-summary`, {}, options);
}

export function generateHtmlSummary(
  meetingId: string | number,
  payload: HtmlSummaryGenerateRequest,
  options?: ApiRequestOptions,
): Promise<HtmlSummaryResponse> {
  return requestJson<HtmlSummaryResponse>(
    `/meetings/${meetingId}/html-summary/generate`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
    },
    options,
  );
}

export function createChatSession(
  payload: {
    mode: "single" | "cross";
    meeting_id?: number;
  },
  options?: ApiRequestOptions,
): Promise<ChatSessionCreateResponse> {
  return requestJson<ChatSessionCreateResponse>(
    "/chat/sessions",
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
    },
    options,
  );
}

export function sendChatMessage(
  sessionId: string,
  message: string,
  options?: ApiRequestOptions,
): Promise<ChatMessageResponse> {
  return requestJson<ChatMessageResponse>(
    `/chat/sessions/${sessionId}/messages`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ message }),
    },
    {
      ...options,
      timeoutMs: options?.timeoutMs ?? CHAT_REQUEST_TIMEOUT_MS,
    },
  );
}

export function createRealtimeSession(
  payload: RealtimeSessionCreateRequest,
  options?: ApiRequestOptions,
): Promise<RealtimeSessionResponse> {
  return requestJson<RealtimeSessionResponse>(
    "/realtime/sessions",
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
    },
    options,
  );
}

export function getRealtimeSession(
  sessionId: string,
  options?: ApiRequestOptions,
): Promise<RealtimeSessionResponse> {
  return requestJson<RealtimeSessionResponse>(`/realtime/sessions/${sessionId}`, {}, options);
}

export function uploadRealtimeChunk(
  sessionId: string,
  formData: FormData,
  options?: ApiRequestOptions,
): Promise<RealtimeSessionResponse> {
  return requestJson<RealtimeSessionResponse>(
    `/realtime/sessions/${sessionId}/chunks`,
    {
      method: "POST",
      body: formData,
    },
    {
      ...options,
      timeoutMs: options?.timeoutMs ?? 30_000,
    },
  );
}

export function stopRealtimeSession(
  sessionId: string,
  options?: ApiRequestOptions,
): Promise<RealtimeSessionResponse> {
  return requestJson<RealtimeSessionResponse>(
    `/realtime/sessions/${sessionId}/stop`,
    {
      method: "POST",
    },
    options,
  );
}

export function diarizeRealtimeSession(
  sessionId: string,
  options?: ApiRequestOptions,
): Promise<RealtimeSessionResponse> {
  return requestJson<RealtimeSessionResponse>(
    `/realtime/sessions/${sessionId}/diarize`,
    {
      method: "POST",
    },
    {
      ...options,
      timeoutMs: options?.timeoutMs ?? 120_000,
    },
  );
}

export function createRealtimeGenerateJob(
  sessionId: string,
  options?: ApiRequestOptions,
): Promise<CreateJobResponse> {
  return requestJson<CreateJobResponse>(
    `/realtime/sessions/${sessionId}/generate`,
    {
      method: "POST",
    },
    options,
  );
}

export function deleteRealtimeSession(
  sessionId: string,
  options?: ApiRequestOptions,
): Promise<RealtimeSessionMutationResponse> {
  return requestJson<RealtimeSessionMutationResponse>(
    `/realtime/sessions/${sessionId}`,
    {
      method: "DELETE",
    },
    options,
  );
}
