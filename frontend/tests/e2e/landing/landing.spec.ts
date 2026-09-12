import { expect, test } from "@playwright/test";
import { installLifeosApiMock } from "../support/mockApi";
import { expectNoHorizontalOverflow } from "../support/assertions";

for (const width of [1440, 768, 390]) test(`landing preview and navigation at ${width}px`, async ({ page }, testInfo) => {
  const errors: string[] = [], mutations: string[] = [];
  page.on("pageerror", e => errors.push(e.message));
  page.on("request", req => { if (req.url().includes("/api/") && req.method() !== "GET") mutations.push(req.url()); });
  await page.route("**/api/v1/session", route => route.fulfill({ json: { authenticated: false, user: null } }));
  await page.setViewportSize({ width, height: 900 });
  await page.goto("/");
  await expect(page.getByRole("heading", { level:1 })).toContainText("Make space for");
  await expectNoHorizontalOverflow(page);
  await page.screenshot({ path:testInfo.outputPath(`landing-${width}.png`),fullPage:true,animations:"disabled" });
  await page.getByRole("tab", { name:"My day",exact:true }).focus();
  await page.keyboard.press("ArrowRight");
  await expect(page.getByRole("tab", { name:"Knowledge",exact:true })).toBeFocused();
  await expect(page.getByRole("tabpanel")).toContainText("Everything you’re learning");
  await expectNoHorizontalOverflow(page);
  await page.keyboard.press("ArrowRight");
  await page.getByRole("button", { name:"Show example answer" }).click();
  await expect(page.getByRole("tabpanel")).toContainText("Example response");
  await expectNoHorizontalOverflow(page);
  await page.getByRole("tab", { name:"My day",exact:true }).click();
  const task=page.getByRole("button", {name:/Bring the first idea to life/});
  await task.click();
  await expect(task).toHaveAttribute("aria-pressed","true");
  await expect(page.getByRole("tabpanel")).toContainText("1 of 2 complete");
  const card=page.getByRole("button",{name:/Try a sample flashcard/});
  await card.click();
  await expect(card).toContainText("Recall an idea from memory");
  await page.locator("summary").filter({hasText:"Does AI make changes without asking me?"}).click();
  await expect(page.locator("details[open]")).toContainText("review and confirmation");
  if(width<600){
    await page.getByRole("button",{name:"Open navigation"}).click();
    await expect(page.getByRole("navigation",{name:"Website navigation"})).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(page.getByRole("button",{name:"Open navigation"})).toBeFocused();
  }
  for(const link of await page.locator('a[href^="#"]').all()) {
    const target=await link.getAttribute("href");
    expect(await page.locator(target!).count()).toBe(1);
  }
  await expect(page.getByRole("link",{name:"Create your workspace"}).first()).toHaveAttribute("href","/register");
  expect(mutations).toEqual([]);
  expect(errors).toEqual([]);
});

test("signed-in visitors still go to their dashboard",async({page})=>{
  await installLifeosApiMock(page);
  await page.goto("/");
  await expect(page).toHaveURL(/\/dashboard$/);
  await expect(page.locator(".dashboard-hero")).toBeVisible();
});

test("existing login and registration pages stay available",async({page})=>{
  await page.route("**/api/v1/session",route=>route.fulfill({json:{authenticated:false,user:null}}));
  for(const path of ["/login","/register"]){
    await page.goto(path);
    await expect(page.locator("form")).toBeVisible();
    await expect(page.locator(".vsl-landing")).toHaveCount(0);
    await expectNoHorizontalOverflow(page);
  }
});
