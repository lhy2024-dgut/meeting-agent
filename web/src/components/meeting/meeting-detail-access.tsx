"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { MeetingDetailPage } from "@/components/meeting/meeting-detail-page";
import { useAuth } from "@/components/providers/auth-provider";
import { PrivacyUnlockForm } from "@/components/privacy/privacy-unlock-form";
import { Card } from "@/components/ui/cards";
import { ApiError, getMeeting, getTranscript } from "@/lib/api";
import { MeetingDetail, MeetingSourceType, PrivacyUnlockResponse, TranscriptResponse } from "@/types/api";

type MeetingDetailAccessProps = {
  meetingId: number;
  initialMeeting: MeetingDetail | null;
  initialTranscript: TranscriptResponse | null;
  highlightedSource?: MeetingSourceType | null;
  highlightedSnippet?: string | null;
};

type StoredMeetingUnlock = {
  unlockToken: string;
  expiresAt: string;
};

export function MeetingDetailAccess({
  meetingId,
  initialMeeting,
  initialTranscript,
  highlightedSource = null,
  highlightedSnippet = null,
}: MeetingDetailAccessProps) {
  const { user, loading: authLoading } = useAuth();
  const [meeting, setMeeting] = useState(initialMeeting);
  const [transcript, setTranscript] = useState(initialTranscript);
  const [unlockToken, setUnlockToken] = useState<string | null>(null);
  const [checkingStoredUnlock, setCheckingStoredUnlock] = useState(!initialMeeting);
  const [loadError, setLoadError] = useState("");
  const storageKey = `meeting-agent-unlock:${user?.id ?? "anonymous"}:${meetingId}`;

  async function loadPrivateMeeting(token: string) {
    const options = { headers: { "X-Meeting-Unlock-Token": token } };
    const [nextMeeting, nextTranscript] = await Promise.all([
      getMeeting(meetingId, options),
      getTranscript(meetingId, options),
    ]);
    setMeeting(nextMeeting);
    setTranscript(nextTranscript);
    setUnlockToken(token);
    setLoadError("");
  }

  useEffect(() => {
    if (initialMeeting || authLoading || !user) return;

    let active = true;
    const timer = window.setTimeout(() => {
      const raw = window.sessionStorage.getItem(storageKey);
      if (!raw) {
        setCheckingStoredUnlock(false);
        return;
      }

      try {
        const stored = JSON.parse(raw) as StoredMeetingUnlock;
        if (!stored.unlockToken || Date.parse(stored.expiresAt) <= Date.now()) {
          window.sessionStorage.removeItem(storageKey);
          setCheckingStoredUnlock(false);
          return;
        }
        void loadPrivateMeeting(stored.unlockToken)
          .catch((error) => {
            if (!active) return;
            window.sessionStorage.removeItem(storageKey);
            if (!(error instanceof ApiError && error.status === 403)) {
              setLoadError(error instanceof Error ? error.message : "\u52a0\u8f7d\u4f1a\u8bae\u5931\u8d25\u3002");
            }
          })
          .finally(() => {
            if (active) setCheckingStoredUnlock(false);
          });
      } catch {
        window.sessionStorage.removeItem(storageKey);
        setCheckingStoredUnlock(false);
      }
    }, 0);

    return () => {
      active = false;
      window.clearTimeout(timer);
    };
    // loadPrivateMeeting is intentionally scoped to this meeting id.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [authLoading, initialMeeting, storageKey, user]);

  async function handleUnlocked(result: PrivacyUnlockResponse) {
    await loadPrivateMeeting(result.unlock_token);
    window.sessionStorage.setItem(
      storageKey,
      JSON.stringify({ unlockToken: result.unlock_token, expiresAt: result.expires_at }),
    );
  }

  if (meeting && transcript) {
    return (
      <MeetingDetailPage
        meeting={meeting}
        transcript={transcript}
        unlockToken={unlockToken}
        highlightedSource={highlightedSource}
        highlightedSnippet={highlightedSnippet}
      />
    );
  }

  if (checkingStoredUnlock || authLoading) {
    return <Card className="text-[14px] text-[var(--text-secondary)]">{"\u6b63\u5728\u9a8c\u8bc1\u4f1a\u8bae\u8bbf\u95ee\u6743\u9650..."}</Card>;
  }

  return (
    <div className="mx-auto max-w-xl space-y-4">
      <Card>
        <PrivacyUnlockForm
          scope="meeting"
          meetingId={meetingId}
          title={"\u89e3\u9501\u9690\u79c1\u4f1a\u8bae"}
          description={"\u8be5\u4f1a\u8bae\u5185\u5bb9\u53d7\u4fdd\u62a4\u3002\u9a8c\u8bc1\u5f53\u524d\u8d26\u53f7\u5bc6\u7801\u540e\uff0c\u53ef\u5728\u672c\u9875\u8bbf\u95ee\u8be6\u60c5\u3001\u5bfc\u51fa\u548c\u4f1a\u8bae\u95ee\u7b54\u3002"}
          onUnlocked={handleUnlocked}
        />
      </Card>
      {loadError ? <div className="error-inline" role="alert">{loadError}</div> : null}
      <Link className="secondary-link" href="/meetings">{"\u8fd4\u56de\u4f1a\u8bae\u5217\u8868"}</Link>
    </div>
  );
}
