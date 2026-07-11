import { expect, test } from "@playwright/test";

import { waitForAppReady, waitForEnabledTextarea } from "./helpers";

test("聊天页单场问答可通过页面点击完成", async ({ page }) => {
  await waitForAppReady(page, "/chat");

  await expect(page.getByRole("button", { name: "单场会议问答" })).toBeVisible();

  const meetingSelect = page.locator("select.input-shell").first();
  await expect(meetingSelect).toBeVisible();
  const selectedText = await meetingSelect.locator("option:checked").textContent();
  expect((selectedText ?? "").trim().length).toBeGreaterThan(0);

  const suggestions = page.locator("button.suggestion-pill-button");
  await expect(suggestions.first()).toBeVisible();
  await expect(suggestions.first()).toBeEnabled({ timeout: 30_000 });

  const assistantBubbles = page.locator(".chat-bubble-assistant");
  const assistantCountBeforeSuggestion = await assistantBubbles.count();
  await suggestions.first().click();

  await expect(page.locator(".chat-bubble-user").last()).toBeVisible({
    timeout: 30_000,
  });
  await expect(assistantBubbles).toHaveCount(assistantCountBeforeSuggestion + 1, {
    timeout: 60_000,
  });

  const textarea = await waitForEnabledTextarea(page, "输入问题...（最多 500 字）");
  const assistantCountBeforeQuestion = await assistantBubbles.count();
  await textarea.fill("请总结这场会议的待办事项");
  await page.getByRole("button", { name: "发送" }).click();

  await expect(assistantBubbles).toHaveCount(assistantCountBeforeQuestion + 1, {
    timeout: 60_000,
  });
  await expect(page.getByText(/第\s*\d+\/\d+\s*轮/).first()).toBeVisible({
    timeout: 60_000,
  });
});
