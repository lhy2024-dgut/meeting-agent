"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { getMeetingTerms, regenerateMeeting } from "@/lib/api";
import { useJobPolling } from "@/hooks/use-job-polling";

type MeetingRegeneratePanelProps = { meetingId: number; };

export function MeetingRegeneratePanel({ meetingId }: MeetingRegeneratePanelProps) {
  const router = useRouter();
  const [termsText, setTermsText] = useState("");
  const [loadingTerms, setLoadingTerms] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [savedNotice, setSavedNotice] = useState("");

  const { job, startPolling, resetJob } = useJobPolling({
    onSucceeded: () => {
      setSubmitting(false);
      router.refresh();
      setSavedNotice("重新生成完成，详情已刷新。");
    },
    onFailed: (nextJob) => {
      setSubmitting(false);
      setError(nextJob.error || "重新生成失败");
    },
    onPollError: (pollError) => {
      setSubmitting(false);
      setError(pollError.message || "查询任务状态失败");
    },
  });

  useEffect(() => {
    let ignore = false;
    async function loadTerms() {
      try {
        setLoadingTerms(true);
        const response = await getMeetingTerms(meetingId);
        if (!ignore) setTermsText(response.terms.join("\n"));
      } catch (loadError) {
        if (!ignore) setError(loadError instanceof Error ? loadError.message : "加载术语词表失败");
      } finally {
        if (!ignore) setLoadingTerms(false);
      }
    }
    void loadTerms();
    return () => { ignore = true; };
  }, [meetingId]);

  async function handleRegenerate() {
    const terms = termsText.split("\n").map((item) => item.trim()).filter(Boolean);
    setSubmitting(true);
    setError("");
    setSavedNotice("");
    resetJob();
    try {
      const created = await regenerateMeeting(meetingId, { terms });
      const initialJob = await startPolling(created.job_id);
      if (initialJob.status === "failed") {
        setSubmitting(false);
        setError(initialJob.error || "重新生成失败");
      }
      if (initialJob.status === "succeeded") {
        setSubmitting(false);
        router.refresh();
        setSavedNotice("重新生成完成，详情已刷新。");
      }
    } catch (submitError) {
      setSubmitting(false);
      setError(submitError instanceof Error ? submitError.message : "重新生成失败");
    }
  }

  return (
    <div className="space-y-4">
      <div>
        <div className="section-card-title !mb-1">{"术语词表"}</div>
        <div className="text-[13px] text-[var(--text-secondary)]">{"编辑后可重新转写并生成新的纪要、待办和决议。"}</div>
      </div>

      <textarea className="input-shell min-h-[120px]" disabled={loadingTerms || submitting} placeholder={"每行一个词条，例如：\n分布式系统实验室\nProject-X\n张伟"} value={termsText} onChange={(event) => setTermsText(event.target.value)} />

      <div className="flex flex-wrap items-center gap-3">
        <button className="primary-button" disabled={loadingTerms || submitting} type="button" onClick={() => void handleRegenerate()}>
          {submitting ? "重新生成中..." : "保存并重新生成纪要"}
        </button>
        {savedNotice ? <span className="text-[13px] text-[#059669]">{savedNotice}</span> : null}
      </div>

      {job ? (
        <div className="info-strip space-y-3">
          <div className="flex items-center justify-between gap-3">
            <div className="text-[14px] font-semibold text-[var(--dark)]">{"重新生成进度"}</div>
            <div className="text-[13px] text-[var(--primary)]">{job.progress_pct}%</div>
          </div>
          <div className="progress-track"><div className="progress-bar" style={{ width: `${job.progress_pct}%` }} /></div>
          <div className="text-[13px] text-[var(--text-secondary)]">{job.message}</div>
        </div>
      ) : null}

      {error ? <div className="error-inline">{error}</div> : null}
    </div>
  );
}