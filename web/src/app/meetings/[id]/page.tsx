export const dynamic = "force-dynamic";

import { notFound } from "next/navigation";

import { MeetingDetailPage } from "@/components/meeting/meeting-detail-page";
import { PrivacyGate } from "@/components/meeting/privacy-gate";
import { getMeeting, getMeetingMeta, getTranscript } from "@/lib/api";
import { MeetingSourceType } from "@/types/api";

type MeetingPageProps = {
  params: Promise<{
    id: string;
  }>;
  searchParams: Promise<{
    source?: string;
    snippet?: string;
  }>;
};

const VALID_SOURCE_TYPES: MeetingSourceType[] = [
  "transcript",
  "minutes",
  "action_item",
  "resolution",
];

const SOURCE_ALIASES: Record<string, MeetingSourceType> = {
  transcript: "transcript",
  transcripts: "transcript",
  minute: "minutes",
  minutes: "minutes",
  action_item: "action_item",
  action_items: "action_item",
  actionitem: "action_item",
  resolution: "resolution",
  resolutions: "resolution",
};

export default async function MeetingPage({
  params,
  searchParams,
}: MeetingPageProps) {
  const { id } = await params;
  const { source, snippet } = await searchParams;

  // 先取轻量元信息：私密会议在解锁前不把正文下发到 HTML
  const meta = await getMeetingMeta(id).catch(() => null);
  if (!meta) {
    notFound();
  }

  const normalizedSource = typeof source === "string" ? source.trim().toLowerCase() : "";
  const sourceType = VALID_SOURCE_TYPES.includes(normalizedSource as MeetingSourceType)
    ? (normalizedSource as MeetingSourceType)
    : SOURCE_ALIASES[normalizedSource] ?? null;

  if (meta.is_private) {
    return (
      <PrivacyGate
        meetingId={meta.id}
        title={meta.title}
        dateText={meta.date_text}
        highlightedSource={sourceType}
        highlightedSnippet={snippet ?? null}
      />
    );
  }

  const [meeting, transcript] = await Promise.all([
    getMeeting(id).catch(() => null),
    getTranscript(id).catch(() => null),
  ]);

  if (!meeting || !transcript) {
    notFound();
  }

  return (
    <MeetingDetailPage
      meeting={meeting}
      transcript={transcript}
      highlightedSource={sourceType}
      highlightedSnippet={snippet ?? null}
    />
  );
}
