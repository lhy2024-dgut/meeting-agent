export const dynamic = "force-dynamic";

import { HomePage } from "@/components/home/home-page";
import { getMeetings, getStatsOverview } from "@/lib/api";

export default async function Page() {
  const [meetings, stats] = await Promise.all([
    getMeetings({ page: 0, pageSize: 10 }),
    getStatsOverview(),
  ]);

  return <HomePage meetings={meetings.items} stats={stats} />;
}

