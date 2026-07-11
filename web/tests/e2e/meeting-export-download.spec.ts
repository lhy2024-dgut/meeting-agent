import { expect, test } from "@playwright/test";

import { getAuthHeaders, waitForAppReady } from "./helpers";

const MEETING_ID = Number(process.env.PLAYWRIGHT_EXPORT_MEETING_ID || "51");

test("会议详情页导出下载链路可点击", async ({ page, request }) => {
  await waitForAppReady(page, `/meetings/${MEETING_ID}`);

  const formatSelect = page.locator("select.input-shell").first();
  await expect(formatSelect).toBeVisible();
  const downloadLink = page.locator("a.success-link");
  await expect(downloadLink).toBeVisible();

  await formatSelect.selectOption("pdf");
  await expect
    .poll(async () => await downloadLink.getAttribute("href"), {
      timeout: 30_000,
    })
    .toContain("format=pdf");
  const pdfHref = await downloadLink.getAttribute("href");
  expect(pdfHref).toContain("format=pdf");
  const pdfResponse = await request.get(pdfHref!, {
    headers: await getAuthHeaders(),
  });
  expect(pdfResponse.ok()).toBeTruthy();

  await formatSelect.selectOption("docx");
  await expect
    .poll(async () => await downloadLink.getAttribute("href"), {
      timeout: 30_000,
    })
    .toContain("format=docx");
  const docxHref = await downloadLink.getAttribute("href");
  expect(docxHref).toContain("format=docx");
  const docxResponse = await request.get(docxHref!, {
    headers: await getAuthHeaders(),
  });
  expect(docxResponse.ok()).toBeTruthy();
});
