import { test, expect, type Page } from "@playwright/test";

/**
 * Landing gates from docs/QA-RELEASE.md and the S2 exit criteria:
 * coherent at 390/768/1440, visible keyboard focus, working reduced motion,
 * 44px touch targets, no console errors.
 *
 * These assert the gates rather than describing them, because "reduced motion works" is the
 * kind of claim that is easy to make and easy to have quietly broken by a later commit.
 */

const SECTION_HEADINGS = [
  "Change one thing, not everything.",
  "Four steps, and the third one is the point.",
  "A guess is shown as a guess.",
  "Photographs of your home, treated like it.",
  "Start with six photos.",
];

function collectConsoleErrors(page: Page): string[] {
  const errors: string[] = [];
  page.on("console", (message) => {
    if (message.type() === "error") errors.push(message.text());
  });
  page.on("pageerror", (error) => errors.push(error.message));
  return errors;
}

test("@critical renders every landing section with no console errors", async ({ page }) => {
  const errors = collectConsoleErrors(page);
  await page.goto("/");

  await expect(page.getByRole("heading", { level: 1 })).toContainText("Your wardrobe.");
  for (const heading of SECTION_HEADINGS) {
    await expect(page.getByRole("heading", { name: heading })).toBeVisible();
  }

  expect(errors).toEqual([]);
});

for (const [label, width, height] of [
  ["mobile", 390, 844],
  ["tablet", 768, 1024],
  ["desktop", 1440, 900],
] as const) {
  test(`@critical no horizontal overflow at ${label} (${width}px)`, async ({ page }) => {
    await page.setViewportSize({ width, height });
    await page.goto("/");
    // Scroll the whole page so lazily-revealed sections have laid out before measuring.
    await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
    await page.waitForTimeout(400);

    const { scrollWidth, clientWidth } = await page.evaluate(() => ({
      scrollWidth: document.documentElement.scrollWidth,
      clientWidth: document.documentElement.clientWidth,
    }));
    expect(scrollWidth).toBeLessThanOrEqual(clientWidth);
  });
}

test("@critical keyboard reaches the skip link and the primary CTA, with visible focus", async ({
  page,
}) => {
  await page.goto("/");

  await page.keyboard.press("Tab");
  await expect(page.getByRole("link", { name: "Skip to content" })).toBeFocused();

  // Walk forward until the primary CTA takes focus. Bounded so a regression fails rather
  // than hangs.
  let reached = false;
  for (let i = 0; i < 15 && !reached; i += 1) {
    await page.keyboard.press("Tab");
    reached = await page
      .getByRole("link", { name: "Start my wardrobe" })
      .first()
      .evaluate((node) => node === document.activeElement)
      .catch(() => false);
  }
  expect(reached).toBe(true);

  // Focus must be *visible*, not merely present.
  const outlineWidth = await page.evaluate(() => {
    const active = document.activeElement;
    if (!active) return "0px";
    return getComputedStyle(active).outlineWidth;
  });
  expect(parseFloat(outlineWidth)).toBeGreaterThan(0);
});

test("@critical reduced motion renders content visible and unanimated", async ({ browser }) => {
  const context = await browser.newContext({ reducedMotion: "reduce" });
  const page = await context.newPage();
  await page.goto("/");

  const reveals = page.locator("[data-revealed]");
  await expect(reveals.first()).toHaveAttribute("data-revealed", "true");

  // Every reveal is fully opaque immediately — no waiting on an animation that never runs.
  const opacities = await reveals.evaluateAll((nodes) =>
    nodes.map((node) => getComputedStyle(node).opacity),
  );
  expect(opacities.every((value) => value === "1")).toBe(true);

  // No transition at all under reduced motion — not merely a shortened one.
  const transitions = await reveals.evaluateAll((nodes) =>
    nodes.map((node) => getComputedStyle(node).transitionProperty),
  );
  expect(transitions.every((value) => value === "none" || value === "all")).toBe(true);

  const transforms = await reveals.evaluateAll((nodes) =>
    nodes.map((node) => getComputedStyle(node).transform),
  );
  expect(transforms.every((value) => value === "none")).toBe(true);

  await context.close();
});

test("touch targets meet the 44px floor on mobile", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");

  const interactive = page.locator("header a, header button");
  const count = await interactive.count();
  expect(count).toBeGreaterThan(0);

  for (let i = 0; i < count; i += 1) {
    const target = interactive.nth(i);
    if (!(await target.isVisible())) continue;
    const box = await target.boundingBox();
    if (!box) continue;
    expect.soft(box.height, `target ${i} height`).toBeGreaterThanOrEqual(44);
  }
});

test("mobile menu opens as a modal dialog and closes on Escape", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");

  await page.getByRole("button", { name: "Menu" }).click();
  const dialog = page.getByRole("dialog", { name: "Menu" });
  await expect(dialog).toBeVisible();

  await page.keyboard.press("Escape");
  await expect(dialog).not.toBeVisible();
});

test("@critical content is visible even when IntersectionObserver never fires", async ({
  page,
}) => {
  // An occluded or backgrounded browser throttles IntersectionObserver hard enough that a
  // fresh observer never invokes its callback. A page that stays blank in that case is
  // broken, so the reveal has scroll-position and timer fallbacks. This test removes IO
  // entirely to prove they carry the page on their own.
  await page.addInitScript(() => {
    // @ts-expect-error deliberately removing a platform API
    delete window.IntersectionObserver;
  });

  await page.goto("/");
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();

  // Wait past the 2.5s safety net.
  await page.waitForTimeout(3200);

  const hidden = await page
    .locator("[data-revealed]")
    .evaluateAll(
      (nodes) => nodes.filter((node) => node.getAttribute("data-revealed") !== "true").length,
    );
  expect(hidden).toBe(0);

  await expect(page.getByRole("heading", { name: "Start with six photos." })).toBeVisible();
});
