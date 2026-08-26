import { expect, type Page } from "@playwright/test";

export async function expectNoFrontendCrash(page: Page) {
  await expect(page.locator(".frontend-error-card")).toHaveCount(0);
  await expect(page.locator("#root")).not.toBeEmpty();
}

export async function expectNoHorizontalOverflow(page: Page, tolerance = 2) {
  const overflow = await page.evaluate(() => ({
    viewport: document.documentElement.clientWidth,
    document: Math.max(document.documentElement.scrollWidth, document.body.scrollWidth),
  }));
  expect(overflow.document, `document scrollWidth ${overflow.document} should fit viewport ${overflow.viewport}`).toBeLessThanOrEqual(overflow.viewport + tolerance);
}

export async function expectDesktopShell(page: Page) {
  const shell = await page.evaluate(() => {
    const sidebar = document.querySelector<HTMLElement>(".app-sidebar");
    const main = document.querySelector<HTMLElement>(".app-main");
    const content = document.querySelector<HTMLElement>(".app-content");
    const s = sidebar?.getBoundingClientRect();
    const m = main?.getBoundingClientRect();
    const c = content?.getBoundingClientRect();
    return {
      viewport: window.innerWidth,
      sidebar: s ? { x: s.x, width: s.width } : null,
      main: m ? { x: m.x, width: m.width } : null,
      content: c ? { x: c.x, width: c.width } : null,
    };
  });

  expect(shell.sidebar).not.toBeNull();
  expect(shell.main).not.toBeNull();
  expect(shell.content).not.toBeNull();
  expect(shell.sidebar!.width).toBeGreaterThanOrEqual(260);
  expect(shell.sidebar!.width).toBeLessThanOrEqual(315);
  expect(shell.main!.x).toBeGreaterThanOrEqual(260);
  expect(shell.main!.width).toBeGreaterThan(shell.viewport * 0.62);
  expect(shell.content!.width).toBeGreaterThan(shell.viewport * 0.58);
}

export async function expectMobileShell(page: Page) {
  const shell = await page.evaluate(() => {
    const main = document.querySelector<HTMLElement>(".app-main")?.getBoundingClientRect();
    const menu = document.querySelector<HTMLElement>(".mobile-menu-button");
    const menuStyle = menu ? getComputedStyle(menu) : null;
    return {
      viewport: window.innerWidth,
      main: main ? { x: main.x, width: main.width } : null,
      menuDisplay: menuStyle?.display ?? "none",
    };
  });
  expect(shell.main).not.toBeNull();
  expect(Math.abs(shell.main!.x)).toBeLessThanOrEqual(2);
  expect(shell.main!.width).toBeGreaterThanOrEqual(shell.viewport - 3);
  expect(shell.menuDisplay).not.toBe("none");
}
