import { test, expect, type Page } from "@playwright/test";

/**
 * The cold-start path: upload, progressive cards, correction.
 *
 * The HTTP layer is stubbed via route interception. These are test doubles for an external
 * dependency, exactly as prompts/03-COMPOSER.md specifies — the running app has no offline
 * path and never reaches them. The real endpoints land in S6, at which point these stubs
 * document the contract they must satisfy.
 */

// 1x1 PNG. Small enough to stay inline, real enough to be a valid image file.
const PNG = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8DwHwAFAAH/q842iQAAAABJRU5ErkJggg==",
  "base64",
);

function itemPayload(over: Record<string, unknown> = {}) {
  return {
    item_id: "item_1",
    status: "ready",
    category: "top",
    subcategory: "oxford shirt",
    color_primary: "black",
    color_secondary: null,
    pattern: "solid",
    material_guess: "cotton",
    fit: "regular",
    formality: "smart-casual",
    season_tags: [],
    occasion_tags: [],
    style_tags: [],
    // Below the 0.7 floor, so the UI must hedge it rather than assert it.
    field_confidence: { category: 0.97, color_primary: 0.52, material_guess: 0.4 },
    corrected_fields: [],
    quality_warnings: ["low_light"],
    image_url: "",
    ...over,
  };
}

/** Happy path: two photos accepted, both analysed, both become cards. */
async function stubHappyPath(page: Page, count = 2) {
  await page.route("**/api/v1/wardrobe/items", async (route) => {
    if (route.request().method() !== "POST") return route.fallback();
    await route.fulfill({
      json: {
        items: Array.from({ length: count }, (_, i) => ({
          item_id: `item_${i + 1}`,
          asset_id: `asset_${i + 1}`,
          job_id: `job_${i + 1}`,
          status: "analyzing",
        })),
      },
    });
  });

  await page.route("**/api/v1/jobs/*", (route) =>
    route.fulfill({
      json: { job_id: "job_1", type: "analyze_item", status: "completed", stage: null, progress: 1 },
    }),
  );

  await page.route("**/api/v1/wardrobe/items/*", async (route) => {
    const method = route.request().method();
    if (method === "GET") {
      const id = route.request().url().split("/").pop() ?? "item_1";
      return route.fulfill({ json: itemPayload({ item_id: id }) });
    }
    return route.fallback();
  });
}

async function pick(page: Page, files: Array<{ name: string; mimeType: string; buffer: Buffer }>) {
  await page.locator('input[type="file"]').setInputFiles(files);
}

test("@critical upload resolves each photo into its own card", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));

  await stubHappyPath(page, 2);
  await page.goto("/wardrobe");

  await pick(page, [
    { name: "shirt.png", mimeType: "image/png", buffer: PNG },
    { name: "jeans.png", mimeType: "image/png", buffer: PNG },
  ]);

  // Both photos surface as queue entries, then resolve into garment cards.
  await expect(page.getByText("shirt.png")).toBeVisible();
  await expect(page.getByText("jeans.png")).toBeVisible();

  const cards = page.locator('section[aria-label="Wardrobe"] li');
  await expect(cards).toHaveCount(2, { timeout: 15_000 });
  expect(errors).toEqual([]);
});

test("@critical a refused photo costs one card, not the batch", async ({ page }) => {
  await stubHappyPath(page, 2);
  await page.goto("/wardrobe");

  // The HEIC is refused client-side; the two PNGs must still go through.
  await pick(page, [
    { name: "good-a.png", mimeType: "image/png", buffer: PNG },
    { name: "bad.heic", mimeType: "image/heic", buffer: PNG },
    { name: "good-b.png", mimeType: "image/png", buffer: PNG },
  ]);

  await expect(page.getByText("Not usable")).toBeVisible();
  await expect(page.getByText(/Use a JPEG, PNG, WebP or AVIF photo/)).toBeVisible();

  // USER-FLOWS Flow 1: partial success is success.
  const cards = page.locator('section[aria-label="Wardrobe"] li');
  await expect(cards).toHaveCount(2, { timeout: 15_000 });
});

test("@critical a low-confidence field is hedged, and correcting it settles it", async ({ page }) => {
  await stubHappyPath(page, 1);
  await page.goto("/wardrobe");
  await pick(page, [{ name: "shirt.png", mimeType: "image/png", buffer: PNG }]);

  const card = page.locator('section[aria-label="Wardrobe"] li').first();
  await expect(card).toBeVisible({ timeout: 15_000 });

  // colour confidence is 0.52, below the 0.7 floor — it must read as a guess.
  await expect(card.getByText("best guess").first()).toBeVisible();
  await expect(card.getByText("black")).toBeVisible();

  // Correction is one tap from the card, never buried in settings.
  await card.getByRole("button", { name: "Set it straight" }).click();
  const sheet = page.getByRole("dialog", { name: "Set it straight" });
  await expect(sheet).toBeVisible();

  await sheet.locator("#correction-field").selectOption("color_primary");
  await sheet.locator("#correction-value").fill("navy");
  await sheet.getByRole("button", { name: "Save correction" }).click();

  await expect(card.getByText("navy")).toBeVisible();
  await expect(card.getByText("you set this")).toBeVisible();
  // A settled field is no longer hedged.
  await expect(card.getByText("black")).toHaveCount(0);
});

test("@critical wardrobe survives navigation", async ({ page }) => {
  await stubHappyPath(page, 1);
  await page.goto("/wardrobe");
  await pick(page, [{ name: "shirt.png", mimeType: "image/png", buffer: PNG }]);
  await expect(page.locator('section[aria-label="Wardrobe"] li')).toHaveCount(1, {
    timeout: 15_000,
  });

  await page.getByRole("link", { name: "Compose outfit" }).click();
  await expect(page.getByRole("heading", { name: "Compose an outfit" })).toBeVisible();

  await page.getByRole("link", { name: "← Wardrobe" }).click();
  await expect(page.locator('section[aria-label="Wardrobe"] li')).toHaveCount(1);
});

test("@critical compose names the missing roles instead of inventing them", async ({ page }) => {
  await stubHappyPath(page, 1);
  await page.goto("/wardrobe");
  // One top only — bottom and footwear are absent.
  await pick(page, [{ name: "shirt.png", mimeType: "image/png", buffer: PNG }]);
  await expect(page.locator('section[aria-label="Wardrobe"] li')).toHaveCount(1, {
    timeout: 15_000,
  });

  await page.goto("/compose");
  // Below the three-item threshold, so it asks for more rather than half-styling.
  await expect(page.getByText(/wardrobe needs a little more/i)).toBeVisible();
  await expect(page.getByRole("link", { name: "Add garments" })).toBeVisible();
});

test("preferences are pre-filled and skippable", async ({ page }) => {
  await page.goto("/compose");

  // A user who taps straight through must still have workable answers.
  await expect(page.getByText(/Sensible defaults are already set/)).toBeVisible();
  await expect(page.getByRole("button", { name: "everyday", pressed: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "minimal", pressed: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "regular", pressed: true })).toBeVisible();

  await page.getByRole("button", { name: "evening" }).click();
  await expect(page.getByRole("button", { name: "evening", pressed: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Reset to defaults" })).toBeVisible();
});

test("upload failure is reported per card, not as a page-level dead end", async ({ page }) => {
  await page.route("**/api/v1/wardrobe/items", (route) =>
    route.fulfill({
      status: 503,
      json: {
        error: { code: "AI_UNAVAILABLE", message: "ignored in favour of our own copy", retryable: true },
      },
    }),
  );

  await page.goto("/wardrobe");
  await pick(page, [{ name: "shirt.png", mimeType: "image/png", buffer: PNG }]);

  await expect(page.getByText("Couldn't read it")).toBeVisible();
  // The picker stays usable — never strand the user (USER-FLOWS Flow 6).
  await expect(page.getByRole("button", { name: "Choose photos" })).toBeEnabled();
});

test("no horizontal overflow on the wardrobe screen at 390px", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await stubHappyPath(page, 2);
  await page.goto("/wardrobe");
  await pick(page, [
    { name: "shirt.png", mimeType: "image/png", buffer: PNG },
    { name: "jeans.png", mimeType: "image/png", buffer: PNG },
  ]);
  await expect(page.locator('section[aria-label="Wardrobe"] li').first()).toBeVisible({
    timeout: 15_000,
  });

  const { scrollWidth, clientWidth } = await page.evaluate(() => ({
    scrollWidth: document.documentElement.scrollWidth,
    clientWidth: document.documentElement.clientWidth,
  }));
  expect(scrollWidth).toBeLessThanOrEqual(clientWidth);
});
