import { expect, test } from "@playwright/test";

test("stale authentication cookie does not block the login page", async ({ page }) => {
  await page.context().addCookies([
    {
      name: "meeting_agent_access_token",
      value: "invalid-token",
      url: "http://127.0.0.1:3000",
      sameSite: "Lax",
    },
  ]);

  await page.goto("/login");

  await expect(page.getByRole("heading", { name: "登录" })).toBeVisible();
  await expect(page).toHaveURL(/\/login/);
});
