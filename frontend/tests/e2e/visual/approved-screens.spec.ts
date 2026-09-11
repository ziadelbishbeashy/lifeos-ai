import { expect, test } from "@playwright/test";
import { installLifeosApiMock } from "../support/mockApi";
import { expectNoFrontendCrash, expectNoHorizontalOverflow } from "../support/assertions";

const screens = [
  ["dashboard", "/dashboard"],
  ["projects", "/projects"],
  ["tasks", "/tasks"],
  ["focus", "/focus"],
  ["documents", "/documents"],
  ["document-detail", "/documents/101"],
] as const;

for (const [name, path] of screens) {
  test(`${name} approved desktop visual`, async ({ page }) => {
    await installLifeosApiMock(page);
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto(path);
    await expectNoFrontendCrash(page);
    await expectNoHorizontalOverflow(page);
    await expect(page).toHaveScreenshot(`${name}-1440.png`, { fullPage: true });
  });

  test(`${name} approved mobile visual`, async ({ page }) => {
    await installLifeosApiMock(page);
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto(path);
    await expectNoFrontendCrash(page);
    await expectNoHorizontalOverflow(page, 3);
    await expect(page).toHaveScreenshot(`${name}-390.png`, { fullPage: true });
  });
}

test("focus active session approved desktop visual", async ({ page }) => {
  await installLifeosApiMock(page);
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/focus");
  await page.getByRole("button", { name: /Start focus/i }).click();
  await expect(page.locator("#focusSession")).toBeVisible();
  await expect(page).toHaveScreenshot("focus-active-1440.png", { fullPage: true });
});
