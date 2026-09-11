import { expect, test, type Page } from "@playwright/test";
import { installLifeosApiMock } from "../support/mockApi";
import { expectNoFrontendCrash, expectNoHorizontalOverflow } from "../support/assertions";

async function intelligenceMock(page: Page) {
  await installLifeosApiMock(page);
  const calls: { path: string; body: any }[] = [];
  let rejectAsk = false;
  const day = "2026-08-25";
  const plan = { title: "A focused day", mode: "day", start_date: day, end_date: day, summary: "One realistic block with room for other work.", working_start: "09:00", working_end: "17:00", break_minutes: 15, available_minutes: 480, scheduled_minutes: 60, overload_minutes: 0, days: [{ date: day, label: "Today", scheduled_minutes: 60, available_minutes: 480, commitments: [], blocks: [{ task_id: 11, title: "Add frontend regression coverage", date: day, start_time: "09:00", end_time: "10:00", minutes: 60, block_type: "task", project_id: 1, project_title: "LifeOS", importance: "High", rationale: "Protect the core workflows.", locked: false, sort_order: 0 }] }], unscheduled: [], read_only: true, confirmation_required: true, verified_from_state: true };
  await page.route("**/api/v1/**", async route => {
    const path = new URL(route.request().url()).pathname;
    const json = (body: unknown, status = 200) => route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
    if (path === "/api/v1/intelligence/context-options") return json({ contexts: { groups: { projects: [{ type: "project", id: 1, label: "LifeOS" }] }, counts: { projects: 1 }, selection_mode: "single", verified_ownership: true } });
    if (path === "/api/v1/planner") return json({ planner: { today: day, open_task_count: 4, projects: [{ id: 1, title: "LifeOS" }], active_plan: null, commitments: [], defaults: { mode: "day", working_start: "09:00", working_end: "17:00", break_minutes: 15, horizon_days: 7 }, verified_from_state: true } });
    if (route.request().method() === "POST" && ["/api/v1/intelligence/ask", "/api/v1/planner/preview", "/api/v1/planner/proposals", "/api/v1/intelligence/action-proposals/77/confirm", "/api/v1/intelligence/action-proposals/77/dismiss"].includes(path)) {
      calls.push({ path, body: route.request().postDataJSON() });
      if (path.endsWith("/ask")) return rejectAsk ? json({ message: "Temporary service interruption. Please retry." }, 503) : json({ status: "answered", answer: "Start with one clear goal and verify your progress.", route: { intent: "general", scope: { label: "LifeOS" } }, response_mode: "general_ai_verified", verification: { status: "verified" }, read_only: true });
      if (path.endsWith("/preview")) return json({ preview: plan });
      return json({ proposal: { id: 77, status: path.endsWith("/confirm") ? "confirmed" : "pending", reason: "Save this proposed schedule only after your confirmation." }, changed: path.endsWith("/confirm") });
    }
    return route.fallback();
  });
  return { calls, reject: () => { rejectAsk = true; } };
}

test("workspace search restores focus and opens the selected task drawer", async ({ page }) => {
  await installLifeosApiMock(page);
  await page.goto("/tasks");
  const searchButton = page.getByRole("button", { name: "Search workspace Ctrl K" });
  await searchButton.focus();
  await page.keyboard.press("Control+k");
  const search = page.getByRole("combobox", { name: "Search workspace" });
  await expect(search).toBeFocused();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await expect(searchButton).toBeFocused();
  await searchButton.click();
  await search.fill("Add frontend regression");
  await expect(page.getByRole("dialog").getByRole("option")).toHaveCount(1);
  await search.press("Enter");
  await expect(page).toHaveURL(/tasks\?task=11/);
  await expect(page.getByRole("dialog", { name: "Edit Task" })).toBeVisible();
  await expect(page.getByLabel("Task title", { exact: true })).toHaveValue("Add frontend regression coverage");
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).toHaveCount(0);
});

test("project views, quick creation, theme and sidebar remain usable", async ({ page }, testInfo) => {
  await installLifeosApiMock(page);
  await page.goto("/projects");
  await expect(page.locator(".project-studio-card")).toHaveCount(2);
  await page.getByRole("button", { name: "List view", exact: true }).click();
  await expect(page.locator(".vs-project-list")).toBeVisible();
  await page.getByRole("button", { name: "Grid view", exact: true }).click();
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({ path: testInfo.outputPath("projects.png"), fullPage: true, animations: "disabled" });
  await page.getByRole("button", { name: "Create", exact: true }).click();
  await page.getByRole("option", { name: /Create task/ }).click();
  await expect(page.getByRole("dialog", { name: "New Task" })).toBeVisible();
  await page.keyboard.press("Escape");
  await page.getByRole("button", { name: "Toggle theme" }).click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({ path: testInfo.outputPath("tasks-light.png"), fullPage: true, animations: "disabled" });
  await page.getByRole("button", { name: "Collapse sidebar" }).click();
  await expect.poll(() => page.locator(".app-sidebar").evaluate(e => Math.round(e.getBoundingClientRect().width))).toBe(72);
  await page.setViewportSize({ width: 390, height: 844 });
  const menu = page.getByRole("button", { name: "Open navigation" });
  await menu.click();
  await expect(page.getByRole("link", { name: "Dashboard", exact: true })).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(menu).toBeFocused();
  await expectNoHorizontalOverflow(page);
});

test("Ask prefill waits for submission, preserves owned context and restores failed input", async ({ page }, testInfo) => {
  const mock = await intelligenceMock(page);
  await page.goto("/ask?q=What%20next%3F&context_type=project&context_id=1");
  const input = page.getByRole("textbox", { name: "Ask V-SPACE", exact: true });
  await expect(input).toHaveValue("What next?");
  await expect(page.locator(".ask-lifeos-context-trigger")).toContainText("LifeOS");
  expect(mock.calls).toHaveLength(0);
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({ path: testInfo.outputPath("ask.png"), fullPage: true, animations: "disabled" });
  await page.getByRole("button", { name: "Send to V-SPACE" }).click();
  await expect(page.getByText("Start with one clear goal and verify your progress.", { exact: true })).toBeVisible();
  expect(mock.calls[0].body.selected_context).toMatchObject({ type: "project", id: 1 });
  expect(mock.calls[0].body.query).toBe("What next?");
  mock.reject();
  await input.fill("Keep this question");
  await input.press("Enter");
  await expect(page.getByText("Temporary service interruption. Please retry.")).toBeVisible();
  await expect(input).toHaveValue("Keep this question");
  await expectNoFrontendCrash(page);
});

test("Tutor uses the existing Ask service and fits mobile", async ({ page }, testInfo) => {
  const mock = await intelligenceMock(page);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/tutor");
  await page.getByRole("button", { name: "Quiz me", exact: true }).click();
  await page.getByRole("textbox", { name: "Ask V-SPACE", exact: true }).fill("Vector spaces");
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({ path: testInfo.outputPath("tutor-mobile.png"), fullPage: true, animations: "disabled" });
  await expectNoHorizontalOverflow(page);
  await page.getByRole("button", { name: "Send to V-SPACE" }).click();
  await expect(page.getByText("Start with one clear goal and verify your progress.", { exact: true })).toBeVisible();
  expect(mock.calls).toHaveLength(1);
  expect(mock.calls[0].body.query).toContain("self-check quiz");
  expect(mock.calls[0].body.query).toContain("Vector spaces");
  await expectNoFrontendCrash(page);
});

for (const decision of ["Accept plan", "Dismiss"]) test(`planner requires explicit ${decision}`, async ({ page }, testInfo) => {
  const mock = await intelligenceMock(page);
  await page.goto("/planner");
  await page.getByRole("button", { name: /^Build plan/ }).click();
  await expect(page.getByRole("heading", { name: "A focused day" })).toBeVisible();
  expect(mock.calls.map(c => c.path)).toEqual(["/api/v1/planner/preview"]);
  await expect(page.getByRole("button", { name: "Accept plan", exact: true })).toHaveCount(0);
  await page.getByRole("button", { name: "Prepare to accept", exact: true }).click();
  await expect(page.getByText("Confirmation required", { exact: true })).toBeVisible();
  expect(mock.calls.map(c => c.path)).toEqual(["/api/v1/planner/preview", "/api/v1/planner/proposals"]);
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({ path: testInfo.outputPath("planner-confirmation.png"), fullPage: true, animations: "disabled" });
  await page.getByRole("button", { name: decision, exact: true }).click();
  await expect(page.getByRole("status")).toContainText(decision === "Dismiss" ? "Nothing changed" : "Plan accepted");
  expect(mock.calls[2].path).toBe(`/api/v1/intelligence/action-proposals/77/${decision === "Dismiss" ? "dismiss" : "confirm"}`);
  expect(mock.calls).toHaveLength(3);
  await page.setViewportSize({ width: 390, height: 844 });
  await expectNoHorizontalOverflow(page);
  await expectNoFrontendCrash(page);
});
