import { expect, test } from "@playwright/test";
import { installLifeosApiMock } from "../support/mockApi";
import { expectNoFrontendCrash } from "../support/assertions";

test("Focus Studio keeps start, pause, resume and thought-parking behavior", async ({ page }) => {
  await installLifeosApiMock(page);
  await page.goto("/focus");

  await expect(page.getByRole("heading", { name: "Set up the space, then do the work." })).toBeVisible();
  await page.locator("#focusTaskSelect").selectOption("11");
  await page.getByPlaceholder("Example: Finish and test the reminder scheduler").fill("Finish the browser regression safety net");
  await page.getByRole("button", { name: /Start focus/i }).click();

  await expect(page.locator("#focusSession")).toBeVisible();
  await expect(page.getByRole("button", { name: "Pause" })).toBeVisible();
  await page.getByRole("button", { name: "Pause" }).click();
  await expect(page.getByRole("button", { name: "Resume" })).toBeVisible();
  await page.getByRole("button", { name: "Resume" }).click();
  await expect(page.getByRole("button", { name: "Pause" })).toBeVisible();

  await page.getByRole("button", { name: /Park a thought/i }).click();
  await page.locator("#parkThoughtInput").fill("Remember the deployment checklist");
  await page.getByRole("button", { name: "Park thought", exact: true }).click();
  await expect(page.getByText("Remember the deployment checklist")).toBeVisible();
  await expectNoFrontendCrash(page);
});

test("Document Brain detail keeps detect, verify and grounded Ask AI interactions usable", async ({ page }) => {
  await installLifeosApiMock(page);
  await page.goto("/documents/101");

  await expect(page.getByRole("heading", { name: "LifeOS_Master_Plan.pdf" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Project Plan at a glance", exact: true })).toBeVisible();

  await page.getByRole("button", { name: "Detect type" }).click();
  await expect(page.getByRole("heading", { name: "Project Plan", exact: true })).toBeVisible();
  await expect(page.getByText("high confidence")).toBeVisible();

  await page.getByRole("button", { name: "Ask AI" }).click();
  const question = page.getByPlaceholder("Ask a question grounded in this PDF");
  await question.fill("What should happen next?");
  const askForm = question.locator("xpath=ancestor::form[1]");
  await askForm.getByRole("button", { name: "Ask AI", exact: true }).click();
  const answerCard = page.locator(".qa-card").filter({ hasText: "Finish the frontend reliability gate, then continue the roadmap." }).first();
  await expect(answerCard).toBeVisible();
  await answerCard.getByRole("button", { name: /Verify/i }).first().click();
  await expect(answerCard.getByText(/R0 exit condition/i)).toBeVisible();
  await expectNoFrontendCrash(page);
});

test("Projects, Tasks and Notes core content remains interactive", async ({ page }) => {
  await installLifeosApiMock(page);

  await page.goto("/projects");
  await expect(page.locator(".project-studio-card")).toHaveCount(2);
  await page.getByPlaceholder(/Search projects/i).fill("DSD");
  await expect(page.locator(".project-studio-card")).toHaveCount(1);

  await page.goto("/tasks");
  await expect(page.getByText("Add frontend regression coverage")).toBeVisible();
  await expectNoFrontendCrash(page);

  await page.goto("/notes");
  await expect(page.getByRole("link", { name: "R0 checkpoint", exact: true }).first()).toBeVisible();
  await expectNoFrontendCrash(page);
});
