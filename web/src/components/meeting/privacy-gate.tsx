"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { MeetingDetailPage } from "@/components/meeting/meeting-detail-page";
import { Card } from "@/components/ui/cards";
import { getMeeting, getTranscript, verifyPassword } from "@/lib/api";
import { consumeMeetingFresh } from "@/lib/privacy";
import { MeetingDetail, MeetingSourceType, TranscriptResponse } from "@/types/api";

type PrivacyGateProps = {
  meetingId: number;
  title: string;
  dateText: string;
  highlightedSource?: MeetingSourceType | null;
  highlightedSnippet?: string | null;
};

export function PrivacyGate({
  meetingId,
  title,
  dateText,
  highlightedSource = null,
  highlightedSnippet = null,
}: PrivacyGateProps) {
  const [unlocked, setUnlocked] = useState(false);
  const [password, setPassword] = useState("");
  const [verifying, setVerifying] = useState(false);
  const [error, setError] = useState("");
  const [meeting, setMeeting] = useState<MeetingDetail | null>(null);
  const [transcript, setTranscript] = useState<TranscriptResponse | null>(null);
  const [loading, setLoading] = useState(false);

  // 生成后首次查看免密：读取并消费一次性放行标记
  useEffect(() => {
    if (consumeMeetingFresh(meetingId)) {
      setUnlocked(true);
    }
  }, [meetingId]);

  // 解锁后再拉取正文（未解锁前正文不下发到客户端）
  useEffect(() => {
    if (!unlocked || meeting) return;
    let cancelled = false;
    setLoading(true);
    Promise.all([getMeeting(meetingId), getTranscript(meetingId)])
      .then(([detail, transcriptData]) => {
        if (cancelled) return;
        setMeeting(detail);
        setTranscript(transcriptData);
      })
      .catch((fetchError) => {
        if (cancelled) return;
        setError(fetchError instanceof Error ? fetchError.message : "加载会议内容失败");
        setUnlocked(false);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [unlocked, meeting, meetingId]);

  async function handleUnlock(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!password.trim()) {
      setError("请输入密码");
      return;
    }
    setVerifying(true);
    setError("");
    try {
      const result = await verifyPassword(password);
      if (result.valid) {
        setPassword("");
        setUnlocked(true);
      } else {
        setError("密码不正确");
      }
    } catch (verifyError) {
      setError(verifyError instanceof Error ? verifyError.message : "验证失败");
    } finally {
      setVerifying(false);
    }
  }

  if (unlocked && meeting && transcript) {
    return (
      <MeetingDetailPage
        meeting={meeting}
        transcript={transcript}
        highlightedSource={highlightedSource}
        highlightedSnippet={highlightedSnippet}
      />
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <div className="text-[18px] font-bold text-[var(--dark)]">{title}</div>
          <div className="mt-1 text-[13px] text-[var(--muted)]">{dateText}</div>
        </div>
        <Link className="secondary-link" href="/meetings">{"返回"}</Link>
      </div>

      <Card className="privacy-lock-card">
        <div className="privacy-lock-icon">{"🔒"}</div>
        <div className="privacy-lock-title">{"该会议已标记为隐私内容"}</div>
        <div className="privacy-lock-desc">{"请输入你的登录密码以查看会议纪要。"}</div>
        <form className="privacy-lock-form" onSubmit={handleUnlock}>
          <input
            className="input-shell"
            type="password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            placeholder="登录密码"
            autoFocus
            disabled={loading}
          />
          <button className="primary-button" type="submit" disabled={verifying || loading}>
            {verifying ? "验证中..." : loading ? "加载中..." : "查看"}
          </button>
        </form>
        {error ? <div className="error-inline">{error}</div> : null}
      </Card>
    </div>
  );
}
