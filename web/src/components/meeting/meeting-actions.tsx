"use client";

import { useState } from "react";

import { requestBrowserBlob } from "@/lib/browser-api";

type MeetingActionsProps = {
  meetingId: number;
  unlockToken?: string | null;
};

export function MeetingActions({ meetingId, unlockToken = null }: MeetingActionsProps) {
  const [format, setFormat] = useState("docx");
  const [downloading, setDownloading] = useState(false);
  const [error, setError] = useState("");

  async function handleDownload() {
    setDownloading(true);
    setError("");
    try {
      const params = new URLSearchParams({ format });
      const blob = await requestBrowserBlob(
        `/meetings/${meetingId}/exports/download?${params.toString()}`,
        {
          headers: unlockToken ? { "X-Meeting-Unlock-Token": unlockToken } : undefined,
        },
      );
      const href = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = href;
      anchor.download = `meeting-${meetingId}.${format}`;
      anchor.click();
      URL.revokeObjectURL(href);
    } catch (downloadError) {
      setError(downloadError instanceof Error ? downloadError.message : "\u4e0b\u8f7d\u5931\u8d25\u3002");
    } finally {
      setDownloading(false);
    }
  }

  return (
    <div className="flex flex-wrap items-center gap-3">
      <select className="input-shell min-w-[120px]" value={format} onChange={(event) => setFormat(event.target.value)}>
        <option value="docx">docx</option>
        <option value="md">md</option>
        <option value="pdf">pdf</option>
      </select>
      <button className="success-link" type="button" onClick={() => void handleDownload()} disabled={downloading}>
        {downloading ? "\u4e0b\u8f7d\u4e2d..." : `\u4e0b\u8f7d / ${format}`}
      </button>
      {error ? <div className="error-inline" role="alert">{error}</div> : null}
    </div>
  );
}
