import { expect, test } from "@playwright/test";

import { waitForApiJson, waitForAppReady } from "./helpers";

type MeetingListResponse = {
  total_pages: number;
};

test("history pagination follows the live total page count", async ({ page, request }) => {
  const meetings = await waitForApiJson<MeetingListResponse>(
    request,
    "/api/meetings?page=0&page_size=10",
  );
  expect(meetings.total_pages).toBeGreaterThan(1);

  await waitForAppReady(page, "/meetings");

  await expect(
    page.getByText(new RegExp(`^1\\s*/\\s*${meetings.total_pages}$`)),
  ).toBeVisible();
  await expect(page.getByRole("link", { name: "\u4e0b\u4e00\u9875" })).toBeVisible();

  await page.getByRole("link", { name: "\u4e0b\u4e00\u9875" }).click();
  await page.waitForURL(/\/meetings\?page=1/, { timeout: 30_000 });
  await expect(
    page.getByText(new RegExp(`^2\\s*/\\s*${meetings.total_pages}$`)),
  ).toBeVisible({ timeout: 30_000 });
  await expect(page.getByRole("link", { name: "\u4e0a\u4e00\u9875" })).toBeVisible();

  await page.getByRole("link", { name: "\u4e0a\u4e00\u9875" }).click();
  await page.waitForURL((url) => url.pathname === "/meetings" && !url.searchParams.has("page"), {
    timeout: 30_000,
  });
  await expect(
    page.getByText(new RegExp(`^1\\s*/\\s*${meetings.total_pages}$`)),
  ).toBeVisible({ timeout: 30_000 });
});
