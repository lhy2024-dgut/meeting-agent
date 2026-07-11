export const dynamic = "force-dynamic";

import { StatsPage } from "@/components/stats/stats-page";
import { getStatsOverview } from "@/lib/api";

export default async function Page() {
  const stats = await getStatsOverview();
  return <StatsPage stats={stats} />;
}

