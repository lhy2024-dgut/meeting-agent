import { expect, test } from "@playwright/test";

import { waitForAppReady } from "./helpers";

test("\u4e0a\u4f20\u9875\u6a21\u677f\u5217\u8868\u4e0e\u9884\u89c8\u53ef\u70b9\u51fb", async ({ page }) => {
  await waitForAppReady(page, "/meetings/new");

  await expect(page.getByText("\u5bfc\u51fa\u6a21\u677f")).toBeVisible();
  await expect(page.getByRole("button", { name: "\u9ed8\u8ba4\u6a21\u677f", exact: true })).toBeVisible();

  const templateCards = page.locator("button.template-card");
  await expect(templateCards.first()).toBeVisible();
  expect(await templateCards.count()).toBeGreaterThan(0);

  const previewImages = page.locator("button.template-card img.template-card-image");
  if (await previewImages.count()) {
    await expect(previewImages.first()).toBeVisible();
  }

  await templateCards.first().click();
  await expect(templateCards.first().locator(".template-card-badge")).toContainText("\u5df2\u9009\u62e9");
});
