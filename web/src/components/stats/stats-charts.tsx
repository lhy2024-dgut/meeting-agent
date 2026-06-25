"use client";

import {
  Bar,
  BarChart,
  CartesianGrid,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { Card } from "@/components/ui/cards";
import { StatsOverviewResponse } from "@/types/api";

type StatsChartsProps = {
  stats: StatsOverviewResponse;
};

export function StatsCharts({ stats }: StatsChartsProps) {
  return (
    <>
      <div className="grid gap-6 md:grid-cols-2">
        <Card>
          <div className="chart-title">\u4F1A\u8BAE\u65F6\u957F\u5206\u5E03</div>
          <div className="chart-box">
            <ResponsiveContainer width="100%" height={320}>
              <BarChart data={stats.duration_distribution}>
                <CartesianGrid strokeDasharray="3 3" stroke="#E2E8F0" />
                <XAxis dataKey="label" stroke="#64748B" />
                <YAxis stroke="#64748B" />
                <Tooltip />
                <Bar dataKey="count" fill="#5B5EA6" radius={[8, 8, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Card>

        <Card>
          <div className="chart-title">\u4F1A\u8BAE\u73AF\u5883\u5206\u5E03</div>
          <div className="chart-box">
            <ResponsiveContainer width="100%" height={320}>
              <PieChart>
                <Pie
                  data={stats.environment_distribution}
                  dataKey="count"
                  nameKey="label"
                  outerRadius={108}
                  fill="#5B5EA6"
                />
                <Tooltip />
              </PieChart>
            </ResponsiveContainer>
          </div>
        </Card>
      </div>

      {stats.monthly_trend.length >= 2 ? (
        <Card>
          <div className="chart-title">\u4F1A\u8BAE\u6570\u91CF\u8D8B\u52BF</div>
          <div className="chart-box">
            <ResponsiveContainer width="100%" height={280}>
              <LineChart data={stats.monthly_trend}>
                <CartesianGrid strokeDasharray="3 3" stroke="#E2E8F0" />
                <XAxis dataKey="month" stroke="#64748B" />
                <YAxis stroke="#64748B" />
                <Tooltip />
                <Line
                  type="monotone"
                  dataKey="count"
                  stroke="#5B5EA6"
                  strokeWidth={3}
                  dot={{ fill: "#5B5EA6", r: 4 }}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </Card>
      ) : null}
    </>
  );
}
