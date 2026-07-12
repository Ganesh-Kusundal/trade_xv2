import { expect, test } from "@playwright/test";

/**
 * Real smoke e2e (DR-F4): the app builds and loads. The dev server is started
 * by the `webServer` block in playwright.config.ts, so `npm run test:e2e` is
 * self-contained.
 *
 * It verifies the SPA boots, the default route redirects to the Broker Status
 * page, and the "Broker Status" heading renders — catching frontend build and
 * runtime regressions without needing a live broker backend.
 */
test("web terminal builds and loads (smoke)", async ({ page }) => {
  await page.goto("/");
  await expect(page).toHaveURL(/.*\/broker/);
  await expect(page.getByRole("heading", { name: "Broker Status" })).toBeVisible();
});
