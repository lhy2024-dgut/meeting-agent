import { expect, test } from "@playwright/test";

import { waitForApiJson, waitForAppReady } from "./helpers";

type MeetingListResponse = {
  items: Array<{ id: number; title: string }>;
};

test("上传页完整提交流程可点击", async ({ page, request }) => {
  test.setTimeout(420_000);

  await waitForAppReady(page, "/meetings/new");

  const title = `E2E Upload ${Date.now()}`;
  const fileInput = page.locator('input[type="file"]');
  await expect(fileInput).toHaveCount(1);

  await fileInput.setInputFiles("C:/tmp/meeting-agent-fastapi-react/storage/audio/20260612_012259_e13ea540.mp3");
  await page.getByPlaceholder("会议标题").fill(title);

  const templateCards = page.locator("button.template-card");
  if (await templateCards.count()) {
    await templateCards.first().click();
  }

  await page.getByRole("button", { name: "开始生成会议纪要" }).click();

  await expect(page.getByText("处理进度")).toBeVisible({ timeout: 30_000 });
  await expect(page.getByText("状态：")).toBeVisible();

  const detailUrlReached = await page
    .waitForURL(/\/meetings\/\d+/, { timeout: 240_000 })
    .then(() => true)
    .catch(() => false);

  const assertDetailSections = async () => {
    const sectionTitles = page.locator(".section-card-title");
    await expect(sectionTitles.filter({ hasText: "会议纪要" })).toBeVisible({ timeout: 30_000 });
    await expect(sectionTitles.filter({ hasText: "待办事项" })).toBeVisible();
    await expect(sectionTitles.filter({ hasText: "会议决议" })).toBeVisible();
  };

  if (detailUrlReached) {
    await assertDetailSections();
  } else {
    const meeting = await waitForApiJson<MeetingListResponse>(
      request,
      `/api/meetings?page=0&page_size=50&search=${encodeURIComponent(title)}`,
    );
    const created = meeting.items.find((item) => item.title === title);
    expect(created).toBeTruthy();

    await page.goto(`/meetings/${created!.id}`, { waitUntil: "domcontentloaded" });
    await assertDetailSections();
  }
});
