export const dynamic = "force-dynamic";

import { notFound } from "next/navigation";

import { MeetingDetailPage } from "@/components/meeting/meeting-detail-page";
import { getMeeting, getTranscript } from "@/lib/api";
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

export default async function MeetingPage({
  params,
  searchParams,
}: MeetingPageProps) {
  const { id } = await params;
  const { source, snippet } = await searchParams;

  const [meeting, transcript] = await Promise.all([
    getMeeting(id).catch(() => null),
    getTranscript(id).catch(() => null),
  ]);

  if (!meeting || !transcript) {
    notFound();
  }

  const sourceType = VALID_SOURCE_TYPES.includes(source as MeetingSourceType)
    ? (source as MeetingSourceType)
    : null;

  return (
    <MeetingDetailPage
      meeting={meeting}
      transcript={transcript}
      highlightedSource={sourceType}
      highlightedSnippet={snippet ?? null}
    />
  );
}
