import { test, expect, type Page } from "@playwright/test";

/**
 * The result screen and the swap — the signature product moment, in a browser.
 *
 * The HTTP layer is stubbed by route interception, as in `wardrobe.spec.ts`. The payloads
 * below are copied from the API's own serialisers (`apps/api/app/routers/serialization.py`)
 * and `apps/api/tests/test_outfit_routes.py` asserts the same key set against the real thing,
 * so these stay a contract check rather than drifting into fiction.
 *
 * What these tests are actually for: the two acceptance criteria a unit test cannot reach —
 * **no full-page navigation for a swap**, and **the unchanged items stay put**.
 */

function itemPayload(id: string, over: Record<string, unknown> = {}) {
  return {
    item_id: id,
    status: "ready",
    category: "top",
    subcategory: "oxford shirt",
    color_primary: "navy",
    color_secondary: null,
    pattern: "solid",
    material_guess: "cotton",
    fit: "regular",
    formality: "smart-casual",
    season_tags: [],
    occasion_tags: [],
    style_tags: [],
    field_confidence: { category: 0.95, color_primary: 0.9, material_guess: 0.3 },
    corrected_fields: [],
    quality_warnings: [],
    image_url: "",
    ...over,
  };
}

function outfitPayload(over: Record<string, unknown> = {}) {
  return {
    outfit_id: "outfit_1",
    name: "Quiet Navy",
    occasion: "everyday",
    match_score: 84,
    status: "ready",
    degradation_level: 1,
    rationale: ["The palette holds together.", "The volumes balance top to bottom."],
    saved: false,
    missing_roles: [],
    slots: [
      { role: "top", item_id: "item_top", item: itemPayload("item_top") },
      {
        role: "bottom",
        item_id: "item_bottom",
        item: itemPayload("item_bottom", { category: "bottom", subcategory: "chino", color_primary: "stone" }),
      },
      {
        role: "footwear",
        item_id: "item_shoe",
        item: itemPayload("item_shoe", { category: "footwear", subcategory: "sneaker", color_primary: "white" }),
      },
    ],
    confidence: 0.84,
    pro_tips: [{ tip: "Half-tuck the shirt to shorten the torso line.", type: "proportion" }],
    budget_tricks: [],
    wardrobe_gaps: [],
    trend_notes: [],
    ...over,
  };
}

async function stubSession(page: Page) {
  await page.route("**/api/v1/session", (route) =>
    route.fulfill({
      status: 201,
      json: { user_id: "user_e2e", token: "e2e-token", expires_in: 2_592_000 },
    }),
  );
}

async function stubOutfit(page: Page, outfit: Record<string, unknown> = outfitPayload()) {
  await page.route("**/api/v1/outfits/outfit_1", async (route) => {
    if (route.request().method() !== "GET") return route.fallback();
    await route.fulfill({ json: outfit });
  });
}

test.beforeEach(async ({ page }) => {
  await stubSession(page);
});

test("@critical the look renders from the user's own garments, with no price anywhere", async ({
  page,
}) => {
  await stubOutfit(page);
  await page.goto("/outfit/outfit_1");

  await expect(page.getByRole("heading", { name: "Quiet Navy" })).toBeVisible();
  await expect(page.getByTestId("slot-top")).toBeVisible();
  await expect(page.getByTestId("slot-bottom")).toBeVisible();
  await expect(page.getByTestId("slot-footwear")).toBeVisible();

  // Style Match is labelled as a heuristic, never presented as a measurement of the person.
  await expect(page.getByTestId("style-match-score")).toHaveText("84");
  await expect(page.getByText("a styling heuristic")).toBeVisible();

  // The product sells nothing. No total, no price, no shop action anywhere on the screen.
  const body = (await page.locator("body").innerText()).toLowerCase();
  for (const banned of ["$", "£", "add to bag", "buy", "shop now", "total"]) {
    expect(body).not.toContain(banned);
  }
});

test("@critical swapping one slot changes that slot and leaves the others alone", async ({
  page,
}) => {
  await stubOutfit(page);

  await page.route("**/api/v1/outfits/outfit_1/alternatives**", (route) =>
    route.fulfill({
      json: {
        role: "footwear",
        current_item_id: "item_shoe",
        alternatives: [
          {
            item: itemPayload("item_boot", {
              category: "footwear",
              subcategory: "chelsea boot",
              color_primary: "brown",
            }),
            match_score: 88,
            delta: 4,
          },
        ],
        gap: null,
      },
    }),
  );

  await page.route("**/api/v1/outfits/outfit_1/swap", (route) =>
    route.fulfill({
      json: outfitPayload({
        match_score: 88,
        rationale: ["The palette holds together.", "Recomputed after your swap."],
        pro_tips: [],
        slots: [
          { role: "top", item_id: "item_top", item: itemPayload("item_top") },
          {
            role: "bottom",
            item_id: "item_bottom",
            item: itemPayload("item_bottom", { category: "bottom", subcategory: "chino", color_primary: "stone" }),
          },
          {
            role: "footwear",
            item_id: "item_boot",
            item: itemPayload("item_boot", {
              category: "footwear",
              subcategory: "chelsea boot",
              color_primary: "brown",
            }),
          },
        ],
      }),
    }),
  );

  await page.goto("/outfit/outfit_1");
  const url = page.url();
  await expect(page.getByTestId("slot-footwear")).toContainText("white solid sneaker");

  await page.getByRole("button", { name: "Swap the footwear" }).click();
  const sheet = page.getByRole("dialog", { name: "Another footwear?" });
  await expect(sheet).toBeVisible();
  await expect(sheet.getByText("+4 to the look")).toBeVisible();

  await sheet.getByRole("button", { name: /chelsea boot/ }).click();

  // One slot changed…
  await expect(page.getByTestId("slot-footwear")).toContainText("brown solid chelsea boot");
  // Scoped to the score itself. A bare `getByText("88")` matched anything on the page that
  // happened to contain those digits, and flaked once in a full parallel run.
  await expect(page.getByTestId("style-match-score")).toHaveText("88");
  // …and the other two did not.
  await expect(page.getByTestId("slot-top")).toContainText("navy solid oxford shirt");
  await expect(page.getByTestId("slot-bottom")).toContainText("stone solid chino");
  // No page navigation for a swap. The URL is the one we arrived on.
  expect(page.url()).toBe(url);
  await expect(sheet).toBeHidden();
});

test("@critical a slot with nothing to swap names the gap and offers to add one", async ({
  page,
}) => {
  await stubOutfit(page);
  await page.route("**/api/v1/outfits/outfit_1/alternatives**", (route) =>
    route.fulfill({
      json: {
        role: "footwear",
        current_item_id: "item_shoe",
        alternatives: [],
        gap: {
          category: "footwear",
          generic_description: "a clean low-profile shoe in a neutral colour",
        },
      },
    }),
  );

  await page.goto("/outfit/outfit_1");
  await page.getByRole("button", { name: "Swap the footwear" }).click();

  const sheet = page.getByRole("dialog", { name: "Another footwear?" });
  await expect(sheet.getByText(/only footwear in your wardrobe/)).toBeVisible();
  await expect(sheet.getByText(/a clean low-profile shoe/)).toBeVisible();
  await expect(sheet.getByRole("link", { name: "Add a footwear" })).toBeVisible();
});

test("@critical a deleted garment leaves a named hole, not a broken image", async ({ page }) => {
  await stubOutfit(
    page,
    outfitPayload({
      status: "incomplete",
      missing_roles: ["bottom"],
      slots: [
        { role: "top", item_id: "item_top", item: itemPayload("item_top") },
        { role: "bottom", item_id: "item_bottom", item: null },
        {
          role: "footwear",
          item_id: "item_shoe",
          item: itemPayload("item_shoe", { category: "footwear", subcategory: "sneaker" }),
        },
      ],
    }),
  );

  await page.goto("/outfit/outfit_1");

  await expect(page.getByRole("heading", { name: /missing its bottom/ })).toBeVisible();
  await expect(page.getByTestId("slot-bottom")).toContainText(/removed from your wardrobe/);
  // The repair is offered on the empty slot itself.
  await expect(page.getByRole("button", { name: "Swap the bottom" })).toBeVisible();
  await expect(page.getByTestId("slot-bottom").locator("img")).toHaveCount(0);

  // And nothing on the screen describes the look as though it were still whole: no score,
  // and no styling note about the garment that is gone.
  await expect(page.getByTestId("style-match-score")).toHaveCount(0);
  await expect(page.getByText(/Held back until the look is whole/)).toBeVisible();
  await expect(page.getByText(/Half-tuck the shirt/)).toHaveCount(0);
});

test("saving a look reports itself and does not offer to save twice", async ({ page }) => {
  await stubOutfit(page);
  await page.route("**/api/v1/outfits/outfit_1/save", (route) =>
    route.fulfill({ json: { outfit_id: "outfit_1", saved: true } }),
  );

  await page.goto("/outfit/outfit_1");
  await page.getByRole("button", { name: "Save this look" }).click();

  await expect(page.getByRole("button", { name: "Saved" })).toBeDisabled();
});

test("a degraded look says so rather than passing itself off as a full one", async ({ page }) => {
  await stubOutfit(page, outfitPayload({ degradation_level: 4 }));
  await page.goto("/outfit/outfit_1");

  // AI-EVAL-CASES Case 23. The disclosure is on the screen, not in a log.
  await expect(page.getByText(/ranker rather than the advisory crew/)).toBeVisible();
});

test("composing shows the server's named stages, never a bare spinner", async ({ page }) => {
  await page.route("**/api/v1/wardrobe/items", async (route) => {
    if (route.request().method() !== "GET") return route.fallback();
    await route.fulfill({
      json: {
        items: [
          itemPayload("item_top"),
          itemPayload("item_bottom", { category: "bottom" }),
          itemPayload("item_shoe", { category: "footwear" }),
        ],
      },
    });
  });

  await page.route("**/api/v1/outfits/compose", (route) =>
    route.fulfill({
      status: 202,
      json: {
        job_id: "job_c1",
        type: "compose_outfit",
        status: "queued",
        stage: null,
        progress: null,
        result_id: null,
      },
    }),
  );

  let polls = 0;
  await page.route("**/api/v1/jobs/job_c1", (route) => {
    polls += 1;
    if (polls < 2) {
      return route.fulfill({
        json: {
          job_id: "job_c1",
          type: "compose_outfit",
          status: "processing",
          stage: "matching silhouettes",
          progress: 0.4,
          result_id: null,
        },
      });
    }
    return route.fulfill({
      json: {
        job_id: "job_c1",
        type: "compose_outfit",
        status: "completed",
        stage: "ready",
        progress: 1,
        result_id: "outfit_1",
      },
    });
  });

  await stubOutfit(page);
  // The compose screen reads the wardrobe from the client store, which the wardrobe screen
  // fills from the API. Navigating before those cards exist tests an empty wardrobe.
  await page.goto("/wardrobe");
  await expect(page.locator('section[aria-label="Wardrobe"] li')).toHaveCount(3);
  await page.goto("/compose");

  await page.getByRole("button", { name: "Compose outfit" }).click();
  await expect(page.getByText(/matching silhouettes/)).toBeVisible();

  // And it lands on the result rather than leaving the user on the button.
  await expect(page.getByRole("heading", { name: "Quiet Navy" })).toBeVisible({ timeout: 15_000 });
});

test("an insufficient wardrobe is named, not reported as a failure", async ({ page }) => {
  await page.route("**/api/v1/wardrobe/items", async (route) => {
    if (route.request().method() !== "GET") return route.fallback();
    await route.fulfill({
      json: {
        items: [
          itemPayload("item_top"),
          itemPayload("item_top2"),
          itemPayload("item_top3"),
        ],
      },
    });
  });

  await page.goto("/wardrobe");
  await expect(page.locator('section[aria-label="Wardrobe"] li')).toHaveCount(3);
  await page.goto("/compose");

  // Three tops and nothing else: the screen says which roles are empty before spending a
  // request, and offers the way to fix it.
  await expect(page.getByRole("heading", { name: /You have no bottom or footwear yet/ })).toBeVisible();
  await expect(page.getByRole("link", { name: /Add bottom or footwear/ })).toBeVisible();
});
