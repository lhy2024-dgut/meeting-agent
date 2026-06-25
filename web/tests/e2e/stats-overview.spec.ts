import { expect, test } from "@playwright/test";

import { waitForAppReady } from "./helpers";

test("统计页可通过页面点击进入并渲染图表", async ({ page }) => {
  await waitForAppReady(page, "/");

  const statsEntry = page.locator('a[href="/stats"]').first();
  await expect(statsEntry).toBeVisible();
  await statsEntry.click();

  await page.waitForURL("**/stats", { timeout: 30_000 });
  await page.waitForLoadState("networkidle").catch(() => undefined);

  const metricCards = page.locator(".metric-box");
  await expect(metricCards).toHaveCount(3);

  const chartCards = page.locator(".chart-box");
  const chartCount = await chartCards.count();
  expect(chartCount).toBeGreaterThanOrEqual(2);

  await expect(chartCards.nth(0).locator("svg").first()).toBeVisible();
  await expect(chartCards.nth(1).locator("svg").first()).toBeVisible();

  const svgCount = await page.locator("svg.recharts-surface").count();
  expect(svgCount).toBeGreaterThanOrEqual(2);
});
