import Link from "next/link";

import { formatMeetingCardDate } from "@/lib/format";
import { MeetingSummary, StatsOverviewResponse } from "@/types/api";
import { Card, EmptyState } from "@/components/ui/cards";
import { Pill } from "@/components/ui/pills";

type HomePageProps = {
  meetings: MeetingSummary[];
  stats: StatsOverviewResponse;
};

export function HomePage({ meetings, stats }: HomePageProps) {
  const recentMeetings = meetings.slice(0, 3);
  const todoCount = meetings.reduce((sum, meeting) => sum + meeting.action_item_count, 0);

  return (
    <div className="space-y-6">
      <section className="px-0 py-10">
        <div className="hero-title"><span>{"\u667a\u80fd"}</span>{"\u4f1a\u8bae\u7eaa\u8981\u52a9\u624b"}</div>
        <div className="hero-subtitle">{"\u4e0a\u4f20\u4f1a\u8bae\u5f55\u97f3\u6216\u89c6\u9891\uff0cAI \u81ea\u52a8\u751f\u6210\u7eaa\u8981\u3001\u5f85\u529e\u4e8b\u9879\u4e0e\u4f1a\u8bae\u51b3\u8bae"}</div>
        <div className="mx-auto grid max-w-[960px] grid-cols-1 gap-4 md:grid-cols-3">
          <Link href="/meetings/new" className="cta-card-link">
            <Card className="cta-card">
              <div className="cta-icon">+</div>
              <div className="cta-title">{"\u4e0a\u4f20\u4f1a\u8bae"}</div>
              <div className="cta-desc">{"\u4e0a\u4f20\u97f3\u9891\u6216\u89c6\u9891\uff0cAI \u81ea\u52a8\u5904\u7406"}</div>
            </Card>
          </Link>
          <Link href="/realtime" className="cta-card-link">
            <Card className="cta-card">
              <div className="cta-icon">*</div>
              <div className="cta-title">{"\u5b9e\u65f6\u8f6c\u5199"}</div>
              <div className="cta-desc">{"\u76f4\u63a5\u5f55\u97f3\uff0c\u8fb9\u5f55\u8fb9\u770b\u8f6c\u5199\u7ed3\u679c"}</div>
            </Card>
          </Link>
          <Link href="/meetings" className="cta-card-link">
            <Card className="cta-card">
              <div className="cta-icon">=</div>
              <div className="cta-title">{"\u6d4f\u89c8\u5386\u53f2"}</div>
              <div className="cta-desc">{"\u67e5\u770b\u8fc7\u5f80\u4f1a\u8bae\u7eaa\u8981\u4e0e\u7edf\u8ba1\u7ed3\u679c"}</div>
            </Card>
          </Link>
        </div>
      </section>

      {meetings.length > 0 ? (
        <>
          <Card className="grid gap-4 md:grid-cols-3">
            <div className="metric-center"><div className="metric-native">{stats.total_meetings} {"\u573a"}</div><div className="metric-caption">{"\u5df2\u5904\u7406\u4f1a\u8bae"}</div></div>
            <div className="metric-center"><div className="metric-native">{todoCount} {"\u6761"}</div><div className="metric-caption">{"\u5f85\u529e\u4e8b\u9879"}</div></div>
            <div className="metric-center"><div className="metric-native">~4 {"\u5206\u949f"}</div><div className="metric-caption">{"\u5e73\u5747\u5904\u7406"}</div></div>
          </Card>

          <section className="space-y-4">
            <h2 className="section-title">{"\u6700\u8fd1\u4f1a\u8bae"}</h2>
            <div className="grid gap-4 md:grid-cols-3">
              {recentMeetings.map((meeting) => (
                <Card key={meeting.id}>
                  <div className="space-y-3">
                    <div className="text-[15px] font-bold text-[var(--dark)]">{meeting.title || "\u672a\u547d\u540d\u4f1a\u8bae"}</div>
                    <div className="text-[12px] text-[var(--muted)]">{formatMeetingCardDate(meeting.created_at)}</div>
                    <div className="flex gap-2">
                      <Pill variant="warning">{meeting.action_item_count} {"\u5f85\u529e"}</Pill>
                      <Pill variant="info">{meeting.resolution_count} {"\u51b3\u8bae"}</Pill>
                    </div>
                    <Link href={`/meetings/${meeting.id}`} className="tertiary-link">{"\u67e5\u770b \u2192"}</Link>
                  </div>
                </Card>
              ))}
            </div>
          </section>
        </>
      ) : (
        <EmptyState icon="*" title={"\u6b22\u8fce\u4f7f\u7528 Meeting Agent"} description={"\u4e0a\u4f20\u4f60\u7684\u7b2c\u4e00\u573a\u4f1a\u8bae\u5f55\u97f3\uff0c\u5f00\u59cb\u4f53\u9a8c AI \u7eaa\u8981\u751f\u6210"} />
      )}
    </div>
  );
}
