export const dynamic = "force-dynamic";

import { HistoryPage } from "@/components/history/history-page";
import { getMeetings } from "@/lib/api";

type MeetingsPageProps = {
  searchParams: Promise<{
    page?: string;
    search?: string;
    duration?: string;
    environment?: string;
  }>;
};

export default async function MeetingsPage({ searchParams }: MeetingsPageProps) {
  const params = await searchParams;
  const page = Number(params.page ?? "0");
  const search = params.search?.trim() ?? "";
  const duration = params.duration ?? "";
  const environment = params.environment ?? "";
  const data = await getMeetings({
    page: Number.isFinite(page) ? page : 0,
    pageSize: 10,
    search,
    duration,
    environment,
  });

  return (
    <HistoryPage
      data={data}
      filters={{
        search,
        duration,
        environment,
      }}
    />
  );
}
