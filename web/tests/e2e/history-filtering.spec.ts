import { expect, test } from "@playwright/test";

import { waitForApiJson, waitForAppReady } from "./helpers";

type MeetingSummary = {
  id: number;
  title: string;
  duration_category: string;
  environment: string;
};

type MeetingListResponse = {
  items: MeetingSummary[];
  total: number;
};

test("历史页搜索与筛选联动可点击", async ({ page, request }) => {
  const initial = await waitForApiJson<MeetingListResponse>(
    request,
    "/api/meetings?page=0&page_size=20",
  );
  expect(initial.items.length).toBeGreaterThan(0);

  const target = initial.items[0];
  await waitForAppReady(page, "/meetings");
  await expect(page.getByText(target.title, { exact: true })).toBeVisible();

  await waitForAppReady(
    page,
    `/meetings?search=${encodeURIComponent(target.title)}`,
  );
  await expect(page.getByText(target.title, { exact: true })).toBeVisible({
    timeout: 30_000,
  });

  if (target.duration_category) {
    await waitForAppReady(
      page,
      `/meetings?search=${encodeURIComponent(target.title)}&duration=${encodeURIComponent(
        target.duration_category,
      )}`,
    );
    await expect(page.getByText(target.title, { exact: true })).toBeVisible({
      timeout: 30_000,
    });
  }

  await expect(page.getByText("共")).toBeVisible();

  const filterCandidates = [
    { duration: "short", environment: "" },
    { duration: "medium", environment: "" },
    { duration: "long", environment: "" },
    { duration: target.duration_category || "", environment: "quiet" },
    { duration: target.duration_category || "", environment: "noisy" },
    { duration: target.duration_category || "", environment: "multi_speaker" },
  ].filter(
    (candidate) =>
      candidate.duration !== target.duration_category ||
      candidate.environment !== target.environment,
  );

  let zeroResultFilter:
    | {
        duration: string;
        environment: string;
      }
    | undefined;

  for (const candidate of filterCandidates) {
    const searchParams = new URLSearchParams({
      page: "0",
      page_size: "20",
      search: target.title,
    });
    if (candidate.duration) {
      searchParams.set("duration", candidate.duration);
    }
    if (candidate.environment) {
      searchParams.set("environment", candidate.environment);
    }

    const response = await waitForApiJson<MeetingListResponse>(
      request,
      `/api/meetings?${searchParams.toString()}`,
    );
    if (response.total === 0) {
      zeroResultFilter = candidate;
      break;
    }
  }

  test.skip(!zeroResultFilter, "当前测试数据无法构造稳定的零结果筛选组合");

  const searchParams = new URLSearchParams({
    search: target.title,
  });
  if (zeroResultFilter!.duration) {
    searchParams.set("duration", zeroResultFilter!.duration);
  }
  if (zeroResultFilter!.environment) {
    searchParams.set("environment", zeroResultFilter!.environment);
  }
  await waitForAppReady(page, `/meetings?${searchParams.toString()}`);
  await expect(page.getByText(target.title, { exact: true })).not.toBeVisible();
});
