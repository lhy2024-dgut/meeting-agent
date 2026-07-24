"use client";

import { useCallback, useEffect, useEffectEvent, useRef, useState } from "react";

import { ApiError, sendChatMessage } from "@/lib/api";
import { requestBrowserJson } from "@/lib/browser-api";
import { ChatMemoryStats, ChatSessionCreateResponse, RagResultItem } from "@/types/api";

export type ChatMode = "single" | "cross";

export type ChatMessage = {
  role: "user" | "assistant";
  content: string;
  rag_results?: RagResultItem[];
};

type UseChatSessionOptions = {
  mode: ChatMode;
  meetingId?: number | null;
  userId?: number | null;
  privacyScope?: "public_only" | "all";
  unlockToken?: string | null;
  persistSession?: boolean;
  enabled?: boolean;
  initialAssistantMessage?: string;
  onBeforeBootstrap?: () => void;
  onBootstrapError?: (message: string, error: unknown) => void;
  maxInputLength?: number;
};

const DEFAULT_MAX_INPUT_LENGTH = 500;

type PersistedChatSession = {
  sessionId: string;
  messages: ChatMessage[];
  memory: ChatMemoryStats | null;
};

function readPersistedSession(key: string): PersistedChatSession | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.sessionStorage.getItem(key);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as PersistedChatSession;
    if (!parsed.sessionId || !Array.isArray(parsed.messages)) return null;
    return parsed;
  } catch {
    return null;
  }
}

export function useChatSession({
  mode,
  meetingId,
  userId,
  privacyScope = "public_only",
  unlockToken = null,
  persistSession = true,
  enabled = true,
  initialAssistantMessage,
  onBeforeBootstrap,
  onBootstrapError,
  maxInputLength = DEFAULT_MAX_INPUT_LENGTH,
}: UseChatSessionOptions) {
  const [sessionId, setSessionId] = useState("");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [memory, setMemory] = useState<ChatMemoryStats | null>(null);
  const [refreshToken, setRefreshToken] = useState(0);
  const bootstrapRef = useRef(0);
  const restoredKeyRef = useRef<string | null>(null);
  const activeStorageKeyRef = useRef<string | null>(null);
  const storageKey = `meeting-agent-chat:${userId ?? "anonymous"}:${mode}:${meetingId ?? "all"}:${mode === "cross" ? privacyScope : unlockToken ? "private" : "public"}`;
  const callBeforeBootstrap = useEffectEvent(() => onBeforeBootstrap?.());
  const callBootstrapError = useEffectEvent((message: string, error: unknown) => {
    onBootstrapError?.(message, error);
  });

  useEffect(() => {
    if (!enabled) {
      return;
    }
    if (mode === "single" && !meetingId) {
      return;
    }
    if (!userId) {
      return;
    }

    const currentBootstrap = bootstrapRef.current + 1;
    bootstrapRef.current = currentBootstrap;
    let active = true;

    if (restoredKeyRef.current !== storageKey) {
      restoredKeyRef.current = storageKey;
      activeStorageKeyRef.current = null;
      const persisted = persistSession ? readPersistedSession(storageKey) : null;
      if (persisted) {
        activeStorageKeyRef.current = storageKey;
        const timer = window.setTimeout(() => {
          if (!active) return;
          setSessionId(persisted.sessionId);
          setMessages(persisted.messages);
          setMemory(persisted.memory);
          setInput("");
          setError("");
        }, 0);
        return () => {
          active = false;
          window.clearTimeout(timer);
        };
      }
    }

    async function bootstrap() {
      callBeforeBootstrap();
      setSessionId("");
      setMessages([]);
      setMemory(null);
      setInput("");
      setError("");
      try {
        // 使用 requestBrowserJson 代替 createChatSession（api.ts / requestJson），
        // 避免 401 时 handleUnauthorized 清除 token 并触发跳转登录。
        // 聊天会话初始化失败只需显示错误消息，不应让整个页面的认证状态失效。
        const session = await requestBrowserJson<ChatSessionCreateResponse>(
          "/chat/sessions",
          {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              mode,
              meeting_id: mode === "single" ? meetingId ?? undefined : undefined,
              privacy_scope: mode === "cross" ? privacyScope : undefined,
              unlock_token: unlockToken ?? undefined,
            }),
          },
        );
        if (!active || bootstrapRef.current !== currentBootstrap) {
          return;
        }
        setSessionId(session.session_id);
        activeStorageKeyRef.current = storageKey;
        if (initialAssistantMessage) {
          setMessages([{ role: "assistant", content: initialAssistantMessage }]);
        }
      } catch (bootstrapError) {
        if (!active || bootstrapRef.current !== currentBootstrap) {
          return;
        }
        const message =
          bootstrapError instanceof Error
            ? bootstrapError.message
            : "初始化聊天会话失败";
        setSessionId("");
        setMessages([]);
        setError(message);
        callBootstrapError(message, bootstrapError);
      }
    }

    void bootstrap();

    return () => {
      active = false;
    };
  }, [enabled, initialAssistantMessage, meetingId, mode, persistSession, privacyScope, refreshToken, storageKey, unlockToken, userId]);

  useEffect(() => {
    if (
      typeof window === "undefined" ||
      !persistSession ||
      !sessionId ||
      activeStorageKeyRef.current !== storageKey
    ) {
      return;
    }
    const payload: PersistedChatSession = { sessionId, messages, memory };
    window.sessionStorage.setItem(storageKey, JSON.stringify(payload));
  }, [memory, messages, persistSession, sessionId, storageKey]);

  const submitMessage = useCallback(
    async (message: string) => {
      const trimmed = message.trim();
      if (!trimmed || !sessionId || loading) {
        return false;
      }
      if (trimmed.length > maxInputLength) {
        setError(`问题过长，请控制在 ${maxInputLength} 字以内`);
        return false;
      }

      setLoading(true);
      setError("");
      setMessages((current) => [...current, { role: "user", content: trimmed }]);
      setInput("");

      try {
        const response = await sendChatMessage(sessionId, trimmed);
        setMessages((current) => [
          ...current,
          {
            role: "assistant",
            content: response.assistant_message,
            rag_results: response.rag_results,
          },
        ]);
        setMemory(response.memory);
        return true;
      } catch (submitError) {
        if (submitError instanceof ApiError && submitError.status === 404) {
          if (persistSession && typeof window !== "undefined") {
            window.sessionStorage.removeItem(storageKey);
          }
          restoredKeyRef.current = null;
          activeStorageKeyRef.current = null;
          setSessionId("");
          setMessages([]);
          setMemory(null);
          setError("会话已过期，已为你创建新的问答会话，请重新提问。");
          setRefreshToken((current) => current + 1);
          return false;
        }
        setError(submitError instanceof Error ? submitError.message : "聊天请求失败");
        return false;
      } finally {
        setLoading(false);
      }
    },
    [loading, maxInputLength, persistSession, sessionId, storageKey],
  );

  const resetSession = useCallback(() => {
    if (persistSession && typeof window !== "undefined") {
      window.sessionStorage.removeItem(storageKey);
    }
    restoredKeyRef.current = null;
    activeStorageKeyRef.current = null;
    setSessionId("");
    setMessages([]);
    setMemory(null);
    setInput("");
    setError("");
    setLoading(false);
    setRefreshToken((current) => current + 1);
  }, [persistSession, storageKey]);

  return {
    sessionId,
    messages,
    setMessages,
    input,
    setInput,
    loading,
    error,
    setError,
    memory,
    submitMessage,
    resetSession,
    maxInputLength,
  };
}
