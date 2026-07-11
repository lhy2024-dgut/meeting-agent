import { expect, test } from "@playwright/test";

import { waitForAppReady } from "./helpers";

test("首页 dashboard 可通过页面点击浏览核心入口", async ({ page }) => {
  await waitForAppReady(page, "/");

  await expect(page.getByText("智能", { exact: false })).toBeVisible();
  await expect(page.getByRole("link", { name: /上传会议/ })).toBeVisible();
  await expect(page.getByRole("link", { name: /浏览历史/ })).toBeVisible();

  await expect(page.getByText("已处理会议", { exact: true })).toBeVisible();
  await expect(page.getByText("待办事项", { exact: true })).toBeVisible();
  await expect(page.getByText("平均处理", { exact: true })).toBeVisible();

  await expect(page.getByText("最近会议", { exact: true })).toBeVisible();
  const recentMeetingLink = page.getByRole("link", { name: /查看 →/ }).first();
  await expect(recentMeetingLink).toBeVisible();
  const href = await recentMeetingLink.getAttribute("href");
  expect(href).toMatch(/^\/meetings\/\d+$/);
  await waitForAppReady(page, href!);

  await expect(page.getByRole("heading", { name: "会议纪要", exact: true })).toBeVisible({
    timeout: 30_000,
  });
});
