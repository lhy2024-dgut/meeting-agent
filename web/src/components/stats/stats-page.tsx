"use client";

import { Card, EmptyState } from "@/components/ui/cards";
import { StatsChartsLazy } from "@/components/stats/stats-charts-lazy";
import { StatsOverviewResponse } from "@/types/api";

type StatsPageProps = {
  stats: StatsOverviewResponse;
};

export function StatsPage({ stats }: StatsPageProps) {
  if (stats.total_meetings === 0) {
    return (
      <EmptyState
        icon="\u{1F4CA}"
        title="\u6682\u65E0\u7EDF\u8BA1\u6570\u636E"
        description="\u4E0A\u4F20\u5E76\u5904\u7406\u4F1A\u8BAE\u540E\uFF0C\u8FD9\u91CC\u4F1A\u5C55\u793A\u7EDF\u8BA1\u56FE\u8868\u3002"
      />
    );
  }

  return (
    <div className="space-y-6">
      <h1 className="page-title">\u6570\u636E\u7EDF\u8BA1</h1>

      <div className="grid gap-4 md:grid-cols-4">
        <Card className="metric-box">
          <div className="metric-native">{stats.total_meetings}</div>
          <div className="metric-caption">\u603B\u4F1A\u8BAE</div>
        </Card>
        <Card className="metric-box">
          <div className="metric-native">{stats.short_meetings}</div>
          <div className="metric-caption">\u77ED\u4F1A\uFF08&lt;5min\uFF09</div>
        </Card>
        <Card className="metric-box">
          <div className="metric-native accent-number">
            {stats.todo_completion_rate}%
          </div>
          <div className="metric-caption">待办完成率</div>
        </Card>
        <Card className="metric-box">
          <div className="metric-native">{stats.overdue_todos}</div>
          <div className="metric-caption">逾期待办</div>
        </Card>
      </div>

      <StatsChartsLazy stats={stats} />
    </div>
  );
}
