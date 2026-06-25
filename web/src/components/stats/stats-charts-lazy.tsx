"use client";

import dynamic from "next/dynamic";

import { Card } from "@/components/ui/cards";
import { StatsOverviewResponse } from "@/types/api";

type StatsChartsLazyProps = {
  stats: StatsOverviewResponse;
};

const StatsCharts = dynamic(
  () => import("@/components/stats/stats-charts").then((mod) => mod.StatsCharts),
  {
    loading: () => <StatsChartsFallback />,
  },
);

export function StatsChartsLazy({ stats }: StatsChartsLazyProps) {
  return <StatsCharts stats={stats} />;
}

function StatsChartsFallback() {
  return (
    <div className="space-y-6">
      <div className="grid gap-6 md:grid-cols-2">
        <Card>
          <div className="chart-title">\u52A0\u8F7D\u65F6\u957F\u5206\u5E03\u4E2D...</div>
          <div className="chart-box rounded-[20px] bg-[var(--light-fill)]" />
        </Card>
        <Card>
          <div className="chart-title">\u52A0\u8F7D\u73AF\u5883\u5206\u5E03\u4E2D...</div>
          <div className="chart-box rounded-[20px] bg-[var(--light-fill)]" />
        </Card>
      </div>
      <Card>
        <div className="chart-title">\u52A0\u8F7D\u8D8B\u52BF\u56FE\u4E2D...</div>
        <div className="chart-box rounded-[20px] bg-[var(--light-fill)]" />
      </Card>
    </div>
  );
}
