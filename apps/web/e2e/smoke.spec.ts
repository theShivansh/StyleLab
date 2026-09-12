import { test, expect } from "@playwright/test";

test("@critical the app boots and renders its heading", async ({ page }) => {
  const consoleErrors: string[] = [];
  page.on("console", (message) => {
    if (message.type() === "error") consoleErrors.push(message.text());
  });

  await page.goto("/");
  await expect(page.getByRole("heading", { name: "STYLELAB", level: 1 })).toBeVisible();

  // QA-RELEASE: "no console errors" is a gate, so assert it rather than trusting it.
  expect(consoleErrors).toEqual([]);
});

test("@critical page does not scroll horizontally at 390px", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");

  const overflows = await page.evaluate(
    () => document.documentElement.scrollWidth > document.documentElement.clientWidth,
  );
  expect(overflows).toBe(false);
});
