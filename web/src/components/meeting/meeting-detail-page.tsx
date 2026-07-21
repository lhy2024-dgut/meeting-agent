"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";

import { MeetingActions } from "@/components/meeting/meeting-actions";
import { MeetingChat } from "@/components/meeting/meeting-chat";
import { MeetingEmailPanel } from "@/components/meeting/meeting-email-panel";
import { HtmlSummaryPanel } from "@/components/meeting/html-summary-panel";
import { MeetingRegeneratePanel } from "@/components/meeting/meeting-regenerate-panel";
import { TodoWorkspace } from "@/components/todos/todo-workspace";
import { Card } from "@/components/ui/cards";
import { MinutesPaper, ResolutionSection } from "@/components/ui/meeting-sections";
import { TranscriptPlayer } from "@/components/ui/transcript-player";
import { matchSnippetScore, normalizeText } from "@/lib/source-target";
import { MeetingDetail, MeetingSourceType, TranscriptResponse } from "@/types/api";

type MeetingDetailPageProps = {
  meeting: MeetingDetail;
  transcript: TranscriptResponse;
  unlockToken?: string | null;
  highlightedSource?: MeetingSourceType | null;
  highlightedSnippet?: string | null;
};

const SOURCE_LABELS: Record<MeetingSourceType, string> = {
  transcript: "转录",
  minutes: "纪要",
  action_item: "待办",
  resolution: "决议",
};

export function MeetingDetailPage({
  meeting,
  transcript,
  unlockToken = null,
  highlightedSource = null,
  highlightedSnippet = null,
}: MeetingDetailPageProps) {
  const todoRef = useRef<HTMLDivElement | null>(null);
  const resolutionRef = useRef<HTMLDivElement | null>(null);
  const minutesRef = useRef<HTMLDivElement | null>(null);
  const transcriptRef = useRef<HTMLDivElement | null>(null);
  const fallbackValueRef = useRef(false);
  const [snippetFallback, setSnippetFallback] = useState(false);
  const highlightTodo = highlightedSource === "action_item";
  const highlightResolution = highlightedSource === "resolution";
  const highlightMinutes = highlightedSource === "minutes";
  const highlightTranscript = highlightedSource === "transcript";

  useEffect(() => {
    if (!highlightedSource) {
      fallbackValueRef.current = false;
      queueMicrotask(() => setSnippetFallback(false));
      return;
    }

    const blockTarget = highlightedSource === "action_item" ? todoRef.current : highlightedSource === "resolution" ? resolutionRef.current : highlightedSource === "minutes" ? minutesRef.current : transcriptRef.current;
    if (!blockTarget) return;

    const flashTarget = blockTarget.querySelector<HTMLElement>(".panel-card") ?? blockTarget;
    const snippetTarget = findBestSnippetTarget(blockTarget, highlightedSource, highlightedSnippet);
    const shouldFallback = Boolean(highlightedSnippet) && !snippetTarget;
    fallbackValueRef.current = shouldFallback;
    queueMicrotask(() => { if (fallbackValueRef.current === shouldFallback) setSnippetFallback(shouldFallback); });
    const scrollTarget = snippetTarget ?? flashTarget;

    const frameId = window.requestAnimationFrame(() => {
      scrollTarget.scrollIntoView({ behavior: "smooth", block: "start" });
      flashTarget.classList.remove("source-flash-active");
      snippetTarget?.classList.remove("source-snippet-active");
      void flashTarget.offsetWidth;
      flashTarget.classList.add("source-flash-active");
      if (snippetTarget) {
        void snippetTarget.offsetWidth;
        snippetTarget.classList.add("source-snippet-active");
      }
    });

    const timeoutId = window.setTimeout(() => {
      flashTarget.classList.remove("source-flash-active");
    }, 1800);

    return () => {
      window.cancelAnimationFrame(frameId);
      window.clearTimeout(timeoutId);
      flashTarget.classList.remove("source-flash-active");
      snippetTarget?.classList.remove("source-snippet-active");
    };
  }, [highlightedSnippet, highlightedSource]);

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <div className="text-[18px] font-bold text-[var(--dark)]">{meeting.title}</div>
          <div className="mt-1 text-[13px] text-[var(--muted)]">{meeting.date_text}</div>
        </div>
        <Link className="secondary-link" href="/meetings">{"返回"}</Link>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-4">
        <div className="source-focus-strip">
          <div className="flex flex-wrap items-center gap-2">
            {highlightedSource ? <span className="source-focus-badge">{"来源定位："}{SOURCE_LABELS[highlightedSource]}</span> : null}
            {snippetFallback ? <span className="source-fallback-badge">{"未找到精确片段，已退回到对应区块"}</span> : null}
          </div>
        </div>
        <MeetingActions meetingId={meeting.id} unlockToken={unlockToken} />
      </div>

      <div className="grid gap-4 md:grid-cols-5">
        <Card className="metric-box"><div className="metric-emoji">{meeting.duration_display}</div><div className="metric-caption">{"时长"}</div></Card>
        <Card className="metric-box"><div className="metric-emoji">{meeting.environment_label}</div><div className="metric-caption">{"会议类型"}</div></Card>
        <Card className="metric-box"><div className="metric-emoji">{meeting.duration_label}</div><div className="metric-caption">{"时长分类"}</div></Card>
        <Card className="metric-box"><div className="metric-emoji accent-number">{meeting.action_item_count}</div><div className="metric-caption">{"待办事项"}</div></Card>
        <Card className="metric-box"><div className="metric-emoji blue-number">{meeting.transcript_count}</div><div className="metric-caption">{"转录片段"}</div></Card>
      </div>

      <Card><MeetingRegeneratePanel meetingId={meeting.id} unlockToken={unlockToken} /></Card>

      <div className="grid gap-6 md:grid-cols-2">
        <div ref={todoRef}>
          <Card className={highlightTodo ? "source-highlight source-highlight-action" : ""}>
            <TodoWorkspace
              initialTodos={meeting.todos}
              meetingId={meeting.id}
              compact
              title="待办事项"
            />
          </Card>
        </div>
        <div ref={resolutionRef}><Card className={highlightResolution ? "source-highlight source-highlight-resolution" : ""}><h2 className="section-card-title">{"会议决议"}</h2><ResolutionSection text={meeting.resolutions_text} /></Card></div>
      </div>

      <div ref={minutesRef}><Card className={highlightMinutes ? "source-highlight source-highlight-minutes" : ""}><h2 className="section-card-title">{"会议纪要"}</h2><MinutesPaper text={meeting.minutes_text} /></Card></div>

      <div ref={transcriptRef}><Card className={highlightTranscript ? "source-highlight source-highlight-transcript" : ""}><details open={highlightTranscript}><summary className="expander-summary">{"查看原始转录文本"}</summary><div className="mt-4"><TranscriptPlayer meetingId={meeting.id} segments={transcript.segments} highlighted={highlightTranscript} unlockToken={unlockToken} /></div></details></Card></div>

      <HtmlSummaryPanel meetingId={meeting.id} unlockToken={unlockToken} />

      <MeetingEmailPanel
        meetingId={meeting.id}
        meetingTitle={meeting.title}
        dateText={meeting.date_text}
        unlockToken={unlockToken}
      />

      <Card><MeetingChat meetingId={meeting.id} unlockToken={unlockToken} /></Card>
    </div>
  );
}

const CANDIDATE_SELECTORS: Record<MeetingSourceType, string> = {
  action_item: ".todo-item",
  resolution: ".decision-item",
  transcript: ".transcript-line",
  minutes: ".minutes-paper p, .minutes-paper li, .minutes-paper h1, .minutes-paper h2, .minutes-paper h3, .minutes-paper h4",
};

function findBestSnippetTarget(root: HTMLDivElement, sourceType: MeetingSourceType, snippet: string | null): HTMLElement | null {
  const normalizedSnippet = normalizeText(snippet);
  if (!normalizedSnippet) return null;

  const candidates = Array.from(root.querySelectorAll<HTMLElement>(CANDIDATE_SELECTORS[sourceType]));
  if (sourceType === "transcript") {
    return findBestTranscriptSnippetTarget(candidates, normalizedSnippet);
  }

  let best: { element: HTMLElement; score: number } | null = null;
  for (const candidate of candidates) {
    const score = matchSnippetScore(normalizeText(candidate.textContent ?? ""), normalizedSnippet);
    if (score <= 0) continue;
    if (!best || score > best.score) best = { element: candidate, score };
  }
  return best?.element ?? null;
}

function findBestTranscriptSnippetTarget(
  candidates: HTMLElement[],
  normalizedSnippet: string,
): HTMLElement | null {
  let best: { element: HTMLElement; score: number } | null = null;

  for (const candidate of candidates) {
    const score = matchSnippetScore(normalizeText(candidate.textContent ?? ""), normalizedSnippet);
    if (score <= 0) {
      continue;
    }
    if (!best || score > best.score) {
      best = { element: candidate, score };
    }
  }

  const windowSizes = [4, 3, 2];
  for (const windowSize of windowSizes) {
    for (let start = 0; start < candidates.length; start += 1) {
      const group = candidates.slice(start, start + windowSize);
      if (group.length < 2) {
        continue;
      }
      const combined = normalizeText(group.map((item) => item.textContent ?? "").join(" "));
      const score = matchSnippetScore(combined, normalizedSnippet);
      if (score <= 0) {
        continue;
      }
      const representative = pickBestRepresentative(group, normalizedSnippet);
      const adjustedScore = score + windowSize * 5;
      if (!best || adjustedScore > best.score) {
        best = { element: representative, score: adjustedScore };
      }
    }
  }

  return best?.element ?? null;
}

function pickBestRepresentative(group: HTMLElement[], normalizedSnippet: string): HTMLElement {
  let best = group[0];
  let bestScore = -1;
  for (const candidate of group) {
    const score = matchSnippetScore(normalizeText(candidate.textContent ?? ""), normalizedSnippet);
    if (score > bestScore) {
      best = candidate;
      bestScore = score;
    }
  }
  return best;
}
