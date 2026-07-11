import { expect, test } from "@playwright/test";

import { waitForApiDelete, waitForApiJson, waitForAppReady } from "./helpers";

type MeetingSummary = {
  id: number;
  title: string;
  project_name: string;
};

type MeetingListResponse = {
  items: MeetingSummary[];
};

const EDIT_MEETING_ID = Number(process.env.PLAYWRIGHT_EDIT_MEETING_ID || "51");
const DELETE_TITLE_PREFIX = "E2E Upload ";

test("历史页可编辑项目名并删除测试会议", async ({ page, request }) => {
  const beforeList = await waitForApiJson<MeetingListResponse>(
    request,
    "/api/meetings?page=0&page_size=50",
  );
  const editMeeting = beforeList.items.find((item) => item.id === EDIT_MEETING_ID);
  const deleteCandidates = beforeList.items.filter(
    (item) => item.id !== EDIT_MEETING_ID && item.title.startsWith(DELETE_TITLE_PREFIX),
  );
  const deleteMeeting = deleteCandidates.at(-1);

  expect(editMeeting).toBeTruthy();
  expect(deleteMeeting).toBeTruthy();

  const nextProjectName = `E2E-PROJECT-${Date.now()}`;

  await waitForAppReady(page, "/meetings");

  const searchInput = page.getByPlaceholder("搜索标题 / 摘要 / 项目名...");
  await searchInput.fill(editMeeting!.title);
  await page.getByRole("button", { name: "搜索" }).click();

  const editCard = page.locator(".panel-card").filter({ hasText: editMeeting!.title }).first();
  await expect(editCard).toBeVisible({ timeout: 30_000 });
  await editCard.getByRole("button", { name: "编辑" }).click();

  const projectInput = editCard.getByPlaceholder("输入项目名...");
  await expect(projectInput).toBeVisible();
  await projectInput.fill(nextProjectName);
  await editCard.getByRole("button", { name: "保存" }).click();

  await expect(editCard.getByText(nextProjectName)).toBeVisible({ timeout: 30_000 });

  const afterEdit = await waitForApiJson<{ project_name: string }>(
    request,
    `/api/meetings/${EDIT_MEETING_ID}`,
  );
  expect(afterEdit.project_name).toBe(nextProjectName);

  await searchInput.fill(deleteMeeting!.title);
  await page.getByRole("button", { name: "搜索" }).click();

  const deleteCard = page.locator(".panel-card").filter({ hasText: deleteMeeting!.title }).first();
  await expect(deleteCard).toBeVisible({ timeout: 30_000 });
  await deleteCard.getByRole("button", { name: "删除" }).click();
  await expect(deleteCard.getByText("再次点击以确认删除")).toBeVisible();
  await deleteCard.getByRole("button", { name: "确认删除" }).click();

  await expect(deleteCard).toHaveCount(0, { timeout: 30_000 });
  expect(await waitForApiDelete(request, deleteMeeting!.id)).toBeTruthy();
});
