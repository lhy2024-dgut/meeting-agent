"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import { ApiError, getMeeting, getTranscript } from "@/lib/api";
import { formatMeetingListDate } from "@/lib/format";
import { buildSourceLocatorSnippet, resolveSourcePreview } from "@/lib/source-target";
import { useChatSession } from "@/hooks/use-chat-session";
import { useAuth } from "@/components/providers/auth-provider";
import {
  MeetingDetail,
  MeetingSourceType,
  MeetingSummary,
  RagResultItem,
  TranscriptResponse,
} from "@/types/api";
import { Card, EmptyState } from "@/components/ui/cards";
import { Pill } from "@/components/ui/pills";
import { PrivacyUnlockForm } from "@/components/privacy/privacy-unlock-form";
import { PrivacyUnlockResponse } from "@/types/api";

type ChatMode = "single" | "cross";
type CrossPrivacyScope = "public_only" | "all";

type UnlockGrant = {
  token: string;
  expiresAt: string;
};

const SUGGESTIONS = ["主要议题", "待办事项", "决议内容", "谁负责什么？"];
const IS_DEV = process.env.NODE_ENV !== "production";
const DEBUG_EVENT_LIMIT = 20;
const MEETING_CONTEXT_TTL_MS = 5 * 60 * 1000;

type CachedMeetingContext = {
  meeting: MeetingDetail | null;
  transcript: TranscriptResponse | null;
  cachedAt: number;
};

const meetingContextCache = new Map<number, CachedMeetingContext>();
const meetingContextPromiseCache = new Map<number, Promise<CachedMeetingContext>>();
const meetingContextDebug = {
  enabled: false,
  hits: 0,
  misses: 0,
  expired: 0,
  clears: 0,
  inflightReused: 0,
  events: [] as string[],
};

type ChatWorkspaceProps = {
  meetings: MeetingSummary[];
};

function clearMeetingContextCache() {
  meetingContextCache.clear();
  meetingContextPromiseCache.clear();
  if (IS_DEV) {
    meetingContextDebug.clears += 1;
    pushMeetingCacheDebugEvent("clear cache");
  }
}

function isCacheEntryExpired(entry: CachedMeetingContext): boolean {
  return Date.now() - entry.cachedAt > MEETING_CONTEXT_TTL_MS;
}

function pushMeetingCacheDebugEvent(message: string) {
  const timestamp = new Date().toLocaleTimeString("zh-CN", { hour12: false });
  const line = `[${timestamp}] ${message}`;
  meetingContextDebug.events = [line, ...meetingContextDebug.events].slice(
    0,
    DEBUG_EVENT_LIMIT,
  );
  if (meetingContextDebug.enabled) {
    console.info(`[meeting-cache] ${line}`);
  }
}

async function loadMeetingContext(
  meetingId: number,
  includeTranscript: boolean,
): Promise<CachedMeetingContext> {
  const cached = meetingContextCache.get(meetingId);
  if (cached && isCacheEntryExpired(cached)) {
    meetingContextCache.delete(meetingId);
    if (IS_DEV) {
      meetingContextDebug.expired += 1;
      pushMeetingCacheDebugEvent(`expire meeting=${meetingId}`);
    }
  }

  const freshCached = meetingContextCache.get(meetingId);
  if (freshCached && (!includeTranscript || freshCached.transcript)) {
    if (IS_DEV) {
      meetingContextDebug.hits += 1;
      pushMeetingCacheDebugEvent(
        `hit meeting=${meetingId} transcript=${includeTranscript ? "yes" : "no"}`,
      );
    }
    return freshCached;
  }

  const inFlight = meetingContextPromiseCache.get(meetingId);
  if (inFlight) {
    if (IS_DEV) {
      meetingContextDebug.inflightReused += 1;
      pushMeetingCacheDebugEvent(`reuse inflight meeting=${meetingId}`);
    }
    const resolved = await inFlight;
    if (!includeTranscript || resolved.transcript) {
      return resolved;
    }
  }

  const request = (async () => {
    if (IS_DEV) {
      meetingContextDebug.misses += 1;
      pushMeetingCacheDebugEvent(
        `miss meeting=${meetingId} transcript=${includeTranscript ? "yes" : "no"}`,
      );
    }

    const resolved = {
      meeting: freshCached?.meeting ?? (await getMeeting(meetingId).catch(() => null)),
      transcript:
        freshCached?.transcript ??
        (includeTranscript ? await getTranscript(meetingId).catch(() => null) : null),
      cachedAt: Date.now(),
    };

    meetingContextCache.set(meetingId, resolved);
    return resolved;
  })();

  meetingContextPromiseCache.set(meetingId, request);

  try {
    return await request;
  } finally {
    meetingContextPromiseCache.delete(meetingId);
  }
}

export function ChatWorkspace({ meetings }: ChatWorkspaceProps) {
  const [mode, setMode] = useState<ChatMode>("single");
  const [selectedMeetingId, setSelectedMeetingId] = useState<number | null>(
    meetings[0]?.id ?? null,
  );
  const [debugEnabled, setDebugEnabled] = useState(false);
  const [debugTick, setDebugTick] = useState(0);
  const [crossPrivacyScope, setCrossPrivacyScope] = useState<CrossPrivacyScope>("public_only");
  const [crossUnlock, setCrossUnlock] = useState<UnlockGrant | null>(null);
  const [meetingUnlocks, setMeetingUnlocks] = useState<Record<number, UnlockGrant>>({});
  const effectiveSelectedMeetingId = selectedMeetingId ?? meetings[0]?.id ?? null;

  const selectedMeeting = useMemo(
    () =>
      meetings.find((meeting) => meeting.id === effectiveSelectedMeetingId) ?? null,
    [effectiveSelectedMeetingId, meetings],
  );
  const selectedMeetingUnlock = selectedMeeting ? meetingUnlocks[selectedMeeting.id] ?? null : null;
  const selectedMeetingNeedsUnlock = Boolean(selectedMeeting?.is_private && !selectedMeetingUnlock);
  const crossNeedsUnlock = mode === "cross" && crossPrivacyScope === "all" && !crossUnlock;

  function rememberMeetingUnlock(result: PrivacyUnlockResponse) {
    if (!selectedMeeting) return;
    setMeetingUnlocks((current) => ({
      ...current,
      [selectedMeeting.id]: {
        token: result.unlock_token,
        expiresAt: result.expires_at,
      },
    }));
  }

  function rememberCrossUnlock(result: PrivacyUnlockResponse) {
    setCrossUnlock({ token: result.unlock_token, expiresAt: result.expires_at });
  }

  function clearSelectedMeetingUnlock() {
    if (!selectedMeeting) return;
    setMeetingUnlocks((current) => {
      const next = { ...current };
      delete next[selectedMeeting.id];
      return next;
    });
  }

  useEffect(() => {
    if (!IS_DEV) {
      return;
    }
    meetingContextDebug.enabled = debugEnabled;
  }, [debugEnabled]);

  if (meetings.length === 0) {
    return (
      <div className="space-y-5">
        <div>
          <h1 className="page-title">{"\u4f1a\u8bae\u95ee\u7b54"}</h1>
        </div>
        <Card>
          <EmptyState
            icon="?"
            title={"\u6682\u65e0\u4f1a\u8bae\u8bb0\u5f55"}
            description={"\u8bf7\u5148\u4e0a\u4f20\u5e76\u5904\u7406\u4f1a\u8bae\u97f3\u89c6\u9891\uff0c\u7136\u540e\u518d\u4f7f\u7528\u5355\u573a\u95ee\u7b54\u6216\u8de8\u4f1a\u8bae\u68c0\u7d22\u3002"}
          />
        </Card>
      </div>
    );
  }

  return (
    <div className="space-y-5">
      <div className="space-y-2">
        <h1 className="page-title">{"\u4f1a\u8bae\u95ee\u7b54"}</h1>
        <div className="text-[14px] leading-6 text-[var(--text-secondary)]">
          {"\u63d0\u4f9b\u4e24\u79cd\u95ee\u7b54\u65b9\u5f0f\uff1a\u805a\u7126\u5355\u573a\u4f1a\u8bae\uff0c\u6216\u4ece\u6240\u6709\u5386\u53f2\u4f1a\u8bae\u4e2d\u505a\u8de8\u4f1a\u8bae\u68c0\u7d22\u3002"}
        </div>
      </div>

      <Card className="space-y-4">
        <div className="segmented-toggle">
          <button
            type="button"
            className={mode === "single" ? "segment-active" : "segment-idle"}
            onClick={() => setMode("single")}
          >
            {"\u5355\u573a\u4f1a\u8bae\u95ee\u7b54"}
          </button>
          <button
            type="button"
            className={mode === "cross" ? "segment-active" : "segment-idle"}
            onClick={() => setMode("cross")}
          >
            {"\u8de8\u4f1a\u8bae\u68c0\u7d22"}
          </button>
        </div>

        {IS_DEV ? (
          <div className="dev-cache-panel">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div className="text-[13px] font-semibold text-[var(--text-secondary)]">
                Cache Debug
              </div>
              <div className="flex flex-wrap gap-2">
                <button
                  type="button"
                  className="secondary-button"
                  onClick={() => setDebugEnabled((current) => !current)}
                >
                  {debugEnabled ? "\u5173\u95ed\u65e5\u5fd7" : "\u5f00\u542f\u65e5\u5fd7"}
                </button>
                <button
                  type="button"
                  className="secondary-button"
                  onClick={() => setDebugTick((current) => current + 1)}
                >
                  {"\u5237\u65b0\u72b6\u6001"}
                </button>
              </div>
            </div>
            <div className="mt-3 grid gap-2 text-[12px] text-[var(--text-secondary)] md:grid-cols-5">
              <div>{"\u547d\u4e2d"}: {meetingContextDebug.hits}</div>
              <div>{"\u672a\u547d\u4e2d"}: {meetingContextDebug.misses}</div>
              <div>{"\u8fc7\u671f"}: {meetingContextDebug.expired}</div>
              <div>{"\u6e05\u7a7a"}: {meetingContextDebug.clears}</div>
              <div>{"\u590d\u7528\u4e2d"}: {meetingContextDebug.inflightReused}</div>
            </div>
            <div className="mt-3 rounded-[12px] border border-[var(--border)] bg-[var(--light-fill)] p-3 text-[12px] leading-5 text-[var(--text-secondary)]">
              {debugTick >= 0 && meetingContextDebug.events.length === 0 ? (
                <div>{"\u6682\u65e0\u7f13\u5b58\u4e8b\u4ef6"}</div>
              ) : (
                meetingContextDebug.events.map((event) => <div key={event}>{event}</div>)
              )}
            </div>
          </div>
        ) : null}

        {mode === "single" ? (
          <div className="grid gap-4 md:grid-cols-[2fr_3fr]">
            <div className="space-y-2">
              <div className="text-[13px] font-semibold text-[var(--text-secondary)]">
                {"\u9009\u62e9\u4f1a\u8bae"}
              </div>
              <select
                className="input-shell"
                value={selectedMeetingId ?? ""}
                onChange={(event) => setSelectedMeetingId(Number(event.target.value))}
              >
                {meetings.map((meeting) => (
                  <option key={meeting.id} value={meeting.id}>
                    {meeting.title} {meeting.is_private ? "\uff08\u9690\u79c1\uff09" : ""} {formatMeetingListDate(meeting.created_at)}
                  </option>
                ))}
              </select>
            </div>
            <div className="info-strip">
              <div className="text-[14px] font-semibold text-[var(--dark)]">
                {selectedMeeting?.title ?? "\u672a\u9009\u62e9\u4f1a\u8bae"}
              </div>
              <div className="mt-1 text-[13px] text-[var(--text-secondary)]">
                {selectedMeeting?.short_summary || "\u53ef\u56f4\u7ed5\u5f53\u524d\u4f1a\u8bae\u7eaa\u8981\u3001\u5f85\u529e\u3001\u51b3\u8bae\u548c\u8f6c\u5f55\u5185\u5bb9\u7ee7\u7eed\u8ffd\u95ee\u3002"}
              </div>
              <div className="mt-3 flex flex-wrap gap-2">
                <Pill variant="warning">{selectedMeeting?.action_item_count ?? 0} {"\u5f85\u529e"}</Pill>
                <Pill variant="info">{selectedMeeting?.resolution_count ?? 0} {"\u51b3\u8bae"}</Pill>
                <Pill variant="muted">{selectedMeeting?.duration_label ?? "\u672a\u5206\u7c7b"}</Pill>
              </div>
            </div>
          </div>
        ) : (
          <div className="info-strip space-y-4">
            <div className="text-[14px] font-semibold text-[var(--dark)]">{"\u8de8\u4f1a\u8bae\u68c0\u7d22"}</div>
            <div className="mt-1 text-[13px] text-[var(--text-secondary)]">
              {"\u4ece "}{meetings.length}{" \u573a\u5386\u53f2\u4f1a\u8bae\u77e5\u8bc6\u5e93\u4e2d\u5173\u8054\u68c0\u7d22\uff0c\u56de\u7b54\u65f6\u6807\u6ce8\u5f15\u7528\u6765\u6e90\u4f1a\u8bae\u3002"}
            </div>
            <div className="mt-3 flex flex-wrap gap-2">
              <Pill variant="project">{meetings.length} {"\u573a\u4f1a\u8bae"}</Pill>
              <Pill variant="muted">Top-5 RAG</Pill>
            </div>
            <div className="segmented-toggle" aria-label={"\u68c0\u7d22\u8303\u56f4"}>
              <button
                type="button"
                className={crossPrivacyScope === "public_only" ? "segment-active" : "segment-idle"}
                onClick={() => setCrossPrivacyScope("public_only")}
              >
                {"\u4ec5\u975e\u9690\u79c1\u5185\u5bb9"}
              </button>
              <button
                type="button"
                className={crossPrivacyScope === "all" ? "segment-active" : "segment-idle"}
                onClick={() => setCrossPrivacyScope("all")}
              >
                {"\u6240\u6709\u5185\u5bb9"}
              </button>
            </div>
            <div className="text-[12px] leading-5 text-[var(--muted)]">
              {crossPrivacyScope === "public_only"
                ? "\u5f53\u524d\u53ea\u4f1a\u68c0\u7d22\u975e\u9690\u79c1\u4f1a\u8bae\u3002"
                : crossUnlock
                  ? `\u5df2\u89e3\u9501\u6240\u6709\u5185\u5bb9\uff0c\u6709\u6548\u81f3 ${new Date(crossUnlock.expiresAt).toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" })}\u3002`
                  : "\u67e5\u8be2\u6240\u6709\u5185\u5bb9\u9700\u8981\u518d\u6b21\u9a8c\u8bc1\u767b\u5f55\u5bc6\u7801\u3002"}
            </div>
          </div>
        )}
      </Card>

      <Card>
        {mode === "single" && selectedMeetingNeedsUnlock && selectedMeeting ? (
          <PrivacyUnlockForm
            scope="meeting"
            meetingId={selectedMeeting.id}
            title={"\u89e3\u9501\u8be5\u9690\u79c1\u4f1a\u8bae"}
            description={"\u9a8c\u8bc1\u540e\u53ea\u4f1a\u5f00\u653e\u5f53\u524d\u9009\u4e2d\u4f1a\u8bae\u7684\u95ee\u7b54\u6743\u9650\u3002"}
            onUnlocked={rememberMeetingUnlock}
          />
        ) : crossNeedsUnlock ? (
          <PrivacyUnlockForm
            scope="cross_chat_all"
            title={"\u89e3\u9501\u6240\u6709\u4f1a\u8bae\u5185\u5bb9"}
            description={"\u89e3\u9501\u6743\u9650\u6709\u6548\u671f\u4e3a 1 \u5c0f\u65f6\uff0c\u79bb\u5f00\u672c\u9875\u540e\u4f1a\u7acb\u5373\u6e05\u9664\u3002"}
            onUnlocked={rememberCrossUnlock}
          />
        ) : (
          <ChatSessionPanel
            key={mode === "cross" ? `cross-${crossPrivacyScope}` : `single-${selectedMeeting?.id ?? "none"}`}
            mode={mode}
            meeting={mode === "single" ? selectedMeeting : null}
            totalMeetings={meetings.length}
            privacyScope={crossPrivacyScope}
            unlockToken={mode === "cross" ? crossUnlock?.token ?? null : selectedMeetingUnlock?.token ?? null}
            onUnlockRejected={mode === "cross" ? () => setCrossUnlock(null) : clearSelectedMeetingUnlock}
          />
        )}
      </Card>
    </div>
  );
}

type ChatSessionPanelProps = {
  mode: ChatMode;
  meeting: MeetingSummary | null;
  totalMeetings: number;
  privacyScope: CrossPrivacyScope;
  unlockToken: string | null;
  onUnlockRejected: () => void;
};

function ChatSessionPanel({ mode, meeting, totalMeetings, privacyScope, unlockToken, onUnlockRejected }: ChatSessionPanelProps) {
  const { user } = useAuth();
  const initialAssistantMessage =
    mode === "cross"
      ? `您好，我可以从 ${totalMeetings} 场历史会议中检索相关信息来回答您的问题，回答时会注明内容来自哪场会议。`
      : `您好，我已阅读《${meeting?.title ?? "当前会议"}》的会议内容，请随时提问。`;

  const {
    sessionId,
    messages,
    input,
    setInput,
    loading,
    error,
    memory,
    submitMessage,
    resetSession: resetChatSession,
    maxInputLength,
  } = useChatSession({
    mode,
    meetingId: mode === "single" ? meeting?.id ?? null : null,
    userId: user?.id,
    privacyScope,
    unlockToken,
    persistSession: !(mode === "cross" && privacyScope === "all"),
    enabled: mode === "cross" || Boolean(meeting),
    initialAssistantMessage,
    onBeforeBootstrap: clearMeetingContextCache,
    onBootstrapError: (_message, bootstrapError) => {
      if (unlockToken && bootstrapError instanceof ApiError && bootstrapError.status === 403) {
        onUnlockRejected();
      }
    },
  });

  function resetSession() {
    clearMeetingContextCache();
    resetChatSession();
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-4">
        <div className="section-card-title !mb-0">
          {mode === "cross" ? "跨会议问答" : "单场会议问答"}
        </div>
        <div className="flex items-center gap-3">
          {memory ? (
            <div className="text-[13px] text-[var(--text-secondary)]">
              {"第"} {memory.round_count}/{memory.max_rounds} {"轮"}
              {memory.is_full ? " / 已到上限" : ""}
            </div>
          ) : null}
          <button type="button" className="secondary-button" onClick={resetSession}>
            {"清空对话"}
          </button>
        </div>
      </div>

      {memory?.trimmed ? (
        <div className="text-[13px] text-[var(--muted)]">
          {"对话已超过 10 轮上限，系统已自动裁剪最早的历史对话。"}
        </div>
      ) : null}

      <div className="flex flex-wrap gap-2">
        {SUGGESTIONS.map((item, index) => (
          <button
            key={`${index}-${item}`}
            className="suggestion-pill-button"
            type="button"
            onClick={() => void submitMessage(item)}
            disabled={!sessionId || loading}
          >
            {item}
          </button>
        ))}
      </div>

      <div className="space-y-3">
        {messages.map((message, index) => (
          <div key={`${message.role}-${index}`}>
            <div
              className={
                message.role === "assistant"
                  ? "chat-bubble-assistant"
                  : "chat-bubble-user"
              }
            >
              <strong>{message.role === "assistant" ? "助手" : "你"}</strong>
              <br />
              {message.content}
            </div>
            {message.rag_results && message.rag_results.length > 0 ? (
              <RagResults results={message.rag_results} crossMode={mode === "cross"} />
            ) : null}
          </div>
        ))}
      </div>

      <div className="space-y-3">
        <textarea
          className="input-shell min-h-[84px]"
          value={input}
          onChange={(event) => setInput(event.target.value)}
          placeholder={`输入问题...（最多 ${maxInputLength} 字）`}
        />
        <div className="flex items-center justify-between gap-4">
          <div className="text-[12px] text-[var(--muted)]">{input.length}/{maxInputLength}</div>
          <button
            className="primary-button"
            type="button"
            disabled={!sessionId || loading}
            onClick={() => void submitMessage(input)}
          >
            {loading ? "思考中..." : "发送"}
          </button>
        </div>
      </div>

      {error ? <div className="error-inline">{error}</div> : null}
    </div>
  );
}

type RagResultsProps = {
  results: RagResultItem[];
  crossMode: boolean;
};

function RagResults({ results, crossMode }: RagResultsProps) {
  const resetKey = `${crossMode ? "cross" : "single"}-${results.length}-${results
    .map(
      (item) =>
        `${item.meeting_id ?? "x"}:${item.chunk_type ?? "x"}:${item.text.slice(0, 24)}`,
    )
    .join("|")}`;

  return <RagResultsInner key={resetKey} results={results} crossMode={crossMode} />;
}

function RagResultsInner({ results, crossMode }: RagResultsProps) {
  const meetingCount = new Set(
    results
      .map((item) => item.meeting_title)
      .filter((value): value is string => Boolean(value)),
  ).size;
  const [previews, setPreviews] = useState<Record<string, string>>({});

  useEffect(() => {
    if (!crossMode) {
      return;
    }

    const uniqueMeetingIds = Array.from(
      new Set(
        results
          .map((item) => item.meeting_id)
          .filter((value): value is number => typeof value === "number"),
      ),
    );

    if (uniqueMeetingIds.length === 0) {
      return;
    }

    let active = true;

    async function loadPreviews() {
      const needTranscript = results.some((item) => item.chunk_type === "transcript");
      const meetingEntries = await Promise.all(
        uniqueMeetingIds.map(async (meetingId) =>
          [meetingId, await loadMeetingContext(meetingId, needTranscript)] as const,
        ),
      );

      if (!active) {
        return;
      }

      const meetingMap = new Map<number, CachedMeetingContext>(meetingEntries);
      const nextPreviews: Record<string, string> = {};

      results.forEach((item, index) => {
        if (!item.meeting_id || !item.chunk_type) {
          return;
        }

        const matched = meetingMap.get(item.meeting_id);
        const preview = resolveSourcePreview({
          sourceType: item.chunk_type as MeetingSourceType,
          snippet: item.text,
          meeting: matched?.meeting,
          transcript: matched?.transcript,
        });

        if (preview) {
          nextPreviews[String(index)] = preview;
        }
      });

      setPreviews(nextPreviews);
    }

    void loadPreviews();

    return () => {
      active = false;
    };
  }, [crossMode, results]);

  return (
    <details className="rag-panel">
      <summary className="expander-summary">
        {"\u6765\u6e90\u53c2\u8003\uff08"}{results.length}{" \u6761"}
        {crossMode && meetingCount > 0 ? ` / \u6765\u81ea ${meetingCount} \u573a\u4f1a\u8bae` : ""}{"\uff09"}
      </summary>
      <div className="mt-3 space-y-3">
        {results.map((item, index) => (
          <div key={`${index}-${item.text.slice(0, 20)}`} className="rag-result-item">
            <div className="text-[12px] text-[#6B7280]">
              <strong>#{index + 1}</strong>{" "}
              {crossMode && item.meeting_id ? (
                <Link
                  href={{
                    pathname: `/meetings/${item.meeting_id}`,
                    query: {
                      ...(item.chunk_type
                        ? { source: item.chunk_type as MeetingSourceType }
                        : {}),
                      ...(item.text && item.chunk_type
                        ? {
                            snippet: buildSourceLocatorSnippet(
                              item.chunk_type as MeetingSourceType,
                              item.text,
                            ) ?? undefined,
                          }
                        : {}),
                    },
                  }}
                  className="rag-source-link"
                >
                  {"\u300a"}{item.meeting_title ?? `\u4f1a\u8bae #${item.meeting_id}`}{"\u300b"}
                </Link>
              ) : (
                <>{"\u300a"}{item.meeting_title ?? "\u672a\u77e5\u4f1a\u8bae"}{"\u300b"}</>
              )}
              {" / "}
              {item.chunk_type_label ?? "\u672a\u5206\u7c7b"}
              {" / \u76f8\u4f3c\u5ea6 "}
              <strong>{(item.score * 100).toFixed(1)}%</strong>
            </div>
            {crossMode && item.meeting_summary ? (
              <div className="mt-1 text-[12px] leading-5 text-[var(--muted)]">
                {"\u6458\u8981\uff1a"}{item.meeting_summary.slice(0, 80)}
              </div>
            ) : null}
            {crossMode && previews[String(index)] ? (
              <div className="mt-1 text-[12px] font-semibold text-[var(--accent-hover)]">
                {"\u5c06\u8df3\u5230\uff1a"}{previews[String(index)]}
              </div>
            ) : null}
            <div className="mt-1 text-[13px] leading-6 text-[var(--text-secondary)]">
              {item.text.slice(0, 200)}
            </div>
          </div>
        ))}
      </div>
    </details>
  );
}
