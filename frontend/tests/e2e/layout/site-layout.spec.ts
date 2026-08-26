import { expect, test } from "@playwright/test";
import { installLifeosApiMock } from "../support/mockApi";
import { expectDesktopShell, expectMobileShell, expectNoFrontendCrash, expectNoHorizontalOverflow } from "../support/assertions";

const routes = [
  ["Dashboard", "/dashboard", ".dashboard-hero"],
  ["Projects", "/projects", ".project-studio-index"],
  ["Tasks", "/tasks", ".task-center-page"],
  ["Notes", "/notes", ".notes-studio-page"],
  ["Analytics", "/analytics", ".analytics-page"],
  ["Notifications", "/notifications/settings", ".workspace-page"],
  ["Document Brain", "/documents", ".db-library"],
] as const;

test.describe("desktop layout contract", () => {
  for (const [label, path, root] of routes) {
    test(`${label} fills the separated React canvas`, async ({ page }) => {
      await installLifeosApiMock(page);
      await page.setViewportSize({ width: 1440, height: 900 });
      await page.goto(path);
      await expect(page.locator(root)).toBeVisible();
      await expectNoFrontendCrash(page);
      await expectDesktopShell(page);
      await expectNoHorizontalOverflow(page);

      const rootWidth = await page.locator(root).evaluate((element) => element.getBoundingClientRect().width);
      expect(rootWidth).toBeGreaterThan(760);
    });
  }

  test("dashboard keeps the intended desktop grid proportions", async ({ page }) => {
    await installLifeosApiMock(page);
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto("/dashboard");

    const statCards = page.locator(".dashboard-stat-grid > .dashboard-stat-card");
    await expect(statCards).toHaveCount(4);
    const boxes = await statCards.evaluateAll((nodes) => nodes.map((node) => {
      const r = node.getBoundingClientRect();
      return { x: Math.round(r.x), y: Math.round(r.y), width: Math.round(r.width) };
    }));
    expect(new Set(boxes.map((box) => box.y)).size).toBe(1);
    expect(Math.min(...boxes.map((box) => box.width))).toBeGreaterThan(180);

    const mainPanels = await page.locator(".dashboard-main-grid > .dashboard-panel").evaluateAll((nodes) => nodes.map((node) => node.getBoundingClientRect().width));
    expect(mainPanels).toHaveLength(2);
    expect(Math.min(...mainPanels)).toBeGreaterThan(300);
  });

  test("Document Brain cannot regress to a blank blue workspace", async ({ page }) => {
    await installLifeosApiMock(page);
    await page.goto("/documents");
    await expect(page.getByRole("heading", { name: "Turn every PDF into a searchable, actionable workspace." })).toBeVisible();
    await expect(page.locator(".db-document-card")).toHaveCount(2);
    await expectNoFrontendCrash(page);
  });
});

test.describe("responsive layout contract", () => {
  for (const width of [1024, 390]) {
    test(`core pages do not overflow at ${width}px`, async ({ page }) => {
      await installLifeosApiMock(page);
      await page.setViewportSize({ width, height: width < 500 ? 844 : 768 });

      for (const [, path, root] of routes) {
        await page.goto(path);
        await expect(page.locator(root)).toBeVisible();
        await expectNoFrontendCrash(page);
        await expectNoHorizontalOverflow(page, 3);
        if (width < 980) await expectMobileShell(page);
      }
    });
  }
});
