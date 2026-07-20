"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { ApiError, createChatSession, sendChatMessage } from "@/lib/api";
import { ChatMemoryStats, RagResultItem } from "@/types/api";

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
  enabled?: boolean;
  initialAssistantMessage?: string;
  onBeforeBootstrap?: () => void;
  onBootstrapError?: (message: string) => void;
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
  const storageKey = `meeting-agent-chat:${userId ?? "anonymous"}:${mode}:${meetingId ?? "all"}`;

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
      const persisted = readPersistedSession(storageKey);
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
      onBeforeBootstrap?.();
      setSessionId("");
      setMessages([]);
      setMemory(null);
      setInput("");
      setError("");
      try {
        const session = await createChatSession({
          mode,
          meeting_id: mode === "single" ? meetingId ?? undefined : undefined,
        });
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
        onBootstrapError?.(message);
      }
    }

    void bootstrap();

    return () => {
      active = false;
    };
  }, [enabled, initialAssistantMessage, meetingId, mode, onBeforeBootstrap, onBootstrapError, refreshToken, storageKey, userId]);

  useEffect(() => {
    if (
      typeof window === "undefined" ||
      !sessionId ||
      activeStorageKeyRef.current !== storageKey
    ) {
      return;
    }
    const payload: PersistedChatSession = { sessionId, messages, memory };
    window.sessionStorage.setItem(storageKey, JSON.stringify(payload));
  }, [memory, messages, sessionId, storageKey]);

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
          if (typeof window !== "undefined") {
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
    [loading, maxInputLength, sessionId, storageKey],
  );

  const resetSession = useCallback(() => {
    if (typeof window !== "undefined") {
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
  }, [storageKey]);

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
