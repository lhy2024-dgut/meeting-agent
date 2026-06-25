import { expect, test } from "@playwright/test";

import { waitForApiMeeting, waitForAppReady, waitForEnabledTextarea } from "./helpers";

const MEETING_ID = Number(process.env.PLAYWRIGHT_MEETING_ID || "51");

test("\u4f1a\u8bae\u8be6\u60c5\u9875\u53ef\u901a\u8fc7\u9875\u9762\u70b9\u51fb\u5b8c\u6210\u91cd\u65b0\u751f\u6210", async ({ page, request }) => {
  const beforeMeeting = await waitForApiMeeting(request, MEETING_ID);

  await waitForAppReady(page, `/meetings/${MEETING_ID}`);

  await expect(page.getByText("\u672f\u8bed\u8bcd\u8868")).toBeVisible();
  const textarea = await waitForEnabledTextarea(
    page,
    "\u6bcf\u884c\u4e00\u4e2a\u8bcd\u6761\uff0c\u4f8b\u5982\uff1a\n\u5206\u5e03\u5f0f\u7cfb\u7edf\u5b9e\u9a8c\u5ba4\nProject-X\n\u5f20\u4f1f",
  );
  await expect(page.getByRole("button", { name: "\u4fdd\u5b58\u5e76\u91cd\u65b0\u751f\u6210\u7eaa\u8981" })).toBeVisible();

  const originalTerms = await textarea.inputValue();
  expect(originalTerms.trim().length).toBeGreaterThan(0);

  await page.getByRole("button", { name: "\u4fdd\u5b58\u5e76\u91cd\u65b0\u751f\u6210\u7eaa\u8981" }).click();

  await expect(page.getByRole("button", { name: "\u91cd\u65b0\u751f\u6210\u4e2d..." })).toBeVisible();
  await page.getByText("\u91cd\u65b0\u751f\u6210\u8fdb\u5ea6").waitFor({ state: "visible", timeout: 5_000 }).catch(() => undefined);
  await expect(page.getByText("\u91cd\u65b0\u751f\u6210\u5b8c\u6210\uff0c\u8be6\u60c5\u5df2\u5237\u65b0\u3002")).toBeVisible({ timeout: 180_000 });

  await page.reload({ waitUntil: "domcontentloaded" });
  const sectionTitles = page.locator(".section-card-title");
  await expect(sectionTitles.filter({ hasText: "\u4f1a\u8bae\u7eaa\u8981" })).toBeVisible();
  await expect(sectionTitles.filter({ hasText: "\u5f85\u529e\u4e8b\u9879" })).toBeVisible();
  await expect(sectionTitles.filter({ hasText: "\u4f1a\u8bae\u51b3\u8bae" })).toBeVisible();

  const afterMeeting = await waitForApiMeeting(request, MEETING_ID);
  expect(Date.parse(afterMeeting.updated_at)).toBeGreaterThanOrEqual(Date.parse(beforeMeeting.updated_at));
});
