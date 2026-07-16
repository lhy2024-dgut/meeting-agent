"use client";

import { useChatSession } from "@/hooks/use-chat-session";
import { useAuth } from "@/components/providers/auth-provider";

const SUGGESTIONS = [
  "\u4e3b\u8981\u8bae\u9898\u662f\u4ec0\u4e48\uff1f",
  "\u6709\u54ea\u4e9b\u5f85\u529e\u4e8b\u9879\uff1f",
  "\u8c01\u8d1f\u8d23\u54ea\u4e9b\u4efb\u52a1\uff1f",
];

type MeetingChatProps = { meetingId: number; };

export function MeetingChat({ meetingId }: MeetingChatProps) {
  const { user } = useAuth();
  const {
    sessionId,
    messages,
    input,
    setInput,
    loading,
    error,
    memory,
    submitMessage,
    maxInputLength,
  } = useChatSession({
    mode: "single",
    meetingId,
    userId: user?.id,
  });

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-4">
        <div className="section-card-title !mb-0">{"\u4f1a\u8bae\u95ee\u7b54"}</div>
        {memory ? <div className="text-[13px] text-[var(--text-secondary)]">{"\u7b2c"} {memory.round_count}/{memory.max_rounds} {"\u8f6e"}{memory.is_full ? " / \u5df2\u6ee1" : ""}</div> : null}
      </div>

      {memory?.trimmed ? <div className="text-[13px] text-[var(--muted)]">{"\u5bf9\u8bdd\u5df2\u8d85\u8fc7 10 \u8f6e\u4e0a\u9650\uff0c\u5df2\u81ea\u52a8\u88c1\u526a\u6700\u65e9\u5bf9\u8bdd"}</div> : null}

      <div className="flex flex-wrap gap-2">
        {SUGGESTIONS.map((item) => (
          <button key={item} className="suggestion-pill-button" type="button" onClick={() => void submitMessage(item)} disabled={!sessionId || loading}>{item}</button>
        ))}
      </div>

      <div className="space-y-3">
        {messages.map((message, index) => (
          <div key={`${message.role}-${index}`}>
            <div className={message.role === "assistant" ? "chat-bubble-assistant" : "chat-bubble-user"}>
              <strong>{message.role === "assistant" ? "\u52a9\u624b" : "\u4f60"}</strong>
              <br />
              {message.content}
            </div>
            {message.rag_results && message.rag_results.length > 0 ? (
              <details className="rag-panel">
                <summary className="expander-summary">{"RAG \u53ec\u56de\u53c2\u8003\uff08"}{message.rag_results.length}{" \u6761\uff09"}</summary>
                <div className="mt-3 space-y-3">
                  {message.rag_results.map((item, ragIndex) => (
                    <div key={`${ragIndex}-${item.text.slice(0, 20)}`}>
                      <div className="text-[12px] text-[#6B7280]">
                        <strong>#{ragIndex + 1}</strong> [{item.meeting_title ?? "-"} / {item.chunk_type_label ?? "-"}] {"\u76f8\u4f3c\u5ea6 "}<strong>{(item.score * 100).toFixed(1)}%</strong>
                      </div>
                      <div className="mt-1 text-[13px] text-[var(--text-secondary)]">{item.text.slice(0, 200)}</div>
                    </div>
                  ))}
                </div>
              </details>
            ) : null}
          </div>
        ))}
      </div>

      <div className="space-y-3">
        <textarea className="input-shell min-h-[84px]" value={input} onChange={(event) => setInput(event.target.value)} placeholder={`\u57fa\u4e8e\u4f1a\u8bae\u5185\u5bb9\u63d0\u95ee...\uff08\u6700\u591a ${maxInputLength} \u5b57\uff09`} />
        <div className="flex items-center justify-between gap-4">
          <div className="text-[12px] text-[var(--muted)]">{input.length}/{maxInputLength}</div>
          <button className="primary-button" type="button" disabled={!sessionId || loading} onClick={() => void submitMessage(input)}>{loading ? "\u601d\u8003\u4e2d..." : "\u53d1\u9001"}</button>
        </div>
      </div>

      {error ? <div className="error-inline">{error}</div> : null}
    </div>
  );
}
