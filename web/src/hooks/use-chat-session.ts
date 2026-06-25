"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { createChatSession, sendChatMessage } from "@/lib/api";
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
  enabled?: boolean;
  initialAssistantMessage?: string;
  onBeforeBootstrap?: () => void;
  onBootstrapError?: (message: string) => void;
  maxInputLength?: number;
};

const DEFAULT_MAX_INPUT_LENGTH = 500;

export function useChatSession({
  mode,
  meetingId,
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

  useEffect(() => {
    if (!enabled) {
      return;
    }
    if (mode === "single" && !meetingId) {
      return;
    }

    const currentBootstrap = bootstrapRef.current + 1;
    bootstrapRef.current = currentBootstrap;
    let active = true;

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
  }, [enabled, initialAssistantMessage, meetingId, mode, onBeforeBootstrap, onBootstrapError, refreshToken]);

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
        setError(submitError instanceof Error ? submitError.message : "聊天请求失败");
        return false;
      } finally {
        setLoading(false);
      }
    },
    [loading, maxInputLength, sessionId],
  );

  const resetSession = useCallback(() => {
    setSessionId("");
    setMessages([]);
    setMemory(null);
    setInput("");
    setError("");
    setLoading(false);
    setRefreshToken((current) => current + 1);
  }, []);

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