"use client";

import { useMemo, useState } from "react";

import { getApiBaseUrl } from "@/lib/api";

type MeetingActionsProps = {
  meetingId: number;
  unlockToken?: string | null;
};

export function MeetingActions({ meetingId, unlockToken = null }: MeetingActionsProps) {
  const [format, setFormat] = useState("docx");
  const downloadHref = useMemo(() => {
    const params = new URLSearchParams({ format });
    if (unlockToken) params.set("unlock_token", unlockToken);
    return `${getApiBaseUrl()}/meetings/${meetingId}/exports/download?${params.toString()}`;
  }, [format, meetingId, unlockToken]);

  return (
    <div className="flex flex-wrap items-center gap-3">
      <select className="input-shell min-w-[120px]" value={format} onChange={(event) => setFormat(event.target.value)}>
        <option value="docx">docx</option>
        <option value="md">md</option>
        <option value="pdf">pdf</option>
      </select>
      <a className="success-link" href={downloadHref}>
        {`\u4e0b\u8f7d / ${format}`}
      </a>
    </div>
  );
}
