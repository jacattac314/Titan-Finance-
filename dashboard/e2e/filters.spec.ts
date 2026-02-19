/**
 * E2E – Global Filters
 *
 * Tests all interactive filter controls:
 *   • Symbol / Model / Signal Type dropdowns
 *   • Time Range button group
 *
 * Data is injected via the Socket.IO mock so filters can be exercised against
 * real signal and trade records.
 */

import { test, expect } from "@playwright/test";
import { gotoAndWait, mockSocketIO } from "./helpers";

// ── Shared fixtures ──────────────────────────────────────────────────────────

const SIGNAL_AAPL_BUY = {
  symbol: "AAPL",
  signal: "BUY",
  confidence: 0.87,
  price: 150.5,
  timestamp: Date.now(),
  model_id: "lgb_001",
  model_name: "LGB Model",
  explanation: [{ feature: "momentum", impact: 0.5 }],
};

const SIGNAL_TSLA_SELL = {
  symbol: "TSLA",
  signal: "SELL",
  confidence: 0.72,
  price: 210.0,
  timestamp: Date.now() - 1000,
  model_id: "sma_001",
  model_name: "SMA Model",
  explanation: [{ feature: "mean-reversion", impact: -0.4 }],
};

// ── Time Range button group ──────────────────────────────────────────────────

test.describe("Time Range filter", () => {
  test.beforeEach(async ({ page }) => {
    await mockSocketIO(page);
    await gotoAndWait(page);
  });

  test("defaults to 1H selected", async ({ page }) => {
    const btn = page.getByRole("button", { name: "1H" });
    await expect(btn).toHaveClass(/cyan/);
  });

  test("switches selection when another range is clicked", async ({ page }) => {
    const btn4H = page.getByRole("button", { name: "4H" });
    await btn4H.click();
    await expect(btn4H).toHaveClass(/cyan/);
    // Previous selection loses the active style
    await expect(page.getByRole("button", { name: "1H" })).not.toHaveClass(/cyan/);
  });

  test("selects 15M range correctly", async ({ page }) => {
    await page.getByRole("button", { name: "15M" }).click();
    await expect(page.getByRole("button", { name: "15M" })).toHaveClass(/cyan/);
  });

  test("selects 1D range correctly", async ({ page }) => {
    await page.getByRole("button", { name: "1D" }).click();
    await expect(page.getByRole("button", { name: "1D" })).toHaveClass(/cyan/);
  });

  test("only one time range button is active at a time", async ({ page }) => {
    // Click through each range; verify only the last one has the active class
    for (const label of ["15M", "4H", "1D", "1H"]) {
      await page.getByRole("button", { name: label }).click();
    }
    const activeButtons = page.locator("button").filter({ hasText: /^(15M|1H|4H|1D)$/ });
    const count = await activeButtons.count();
    let activeCount = 0;
    for (let i = 0; i < count; i++) {
      const cls = (await activeButtons.nth(i).getAttribute("class")) ?? "";
      if (cls.includes("cyan")) activeCount++;
    }
    expect(activeCount).toBe(1);
  });
});

// ── Signal Type dropdown ─────────────────────────────────────────────────────

test.describe("Signal Type filter", () => {
  test.beforeEach(async ({ page }) => {
    await mockSocketIO(page, [
      { name: "signal", data: SIGNAL_AAPL_BUY },
      { name: "signal", data: SIGNAL_TSLA_SELL },
    ]);
    await gotoAndWait(page);
  });

  test("defaults to 'All' option selected", async ({ page }) => {
    // The Signal Type select contains "All", "BUY", "SELL"
    // Grab the third select (0=symbol, 1=model, 2=signal type)
    const signalTypeSelect = page.locator("select").nth(2);
    await expect(signalTypeSelect).toHaveValue("ALL");
  });

  test("can select BUY from Signal Type dropdown", async ({ page }) => {
    const signalTypeSelect = page.locator("select").nth(2);
    await signalTypeSelect.selectOption("BUY");
    await expect(signalTypeSelect).toHaveValue("BUY");
  });

  test("can select SELL from Signal Type dropdown", async ({ page }) => {
    const signalTypeSelect = page.locator("select").nth(2);
    await signalTypeSelect.selectOption("SELL");
    await expect(signalTypeSelect).toHaveValue("SELL");
  });

  test("can reset Signal Type back to All", async ({ page }) => {
    const signalTypeSelect = page.locator("select").nth(2);
    await signalTypeSelect.selectOption("BUY");
    await signalTypeSelect.selectOption("ALL");
    await expect(signalTypeSelect).toHaveValue("ALL");
  });
});

// ── Symbol dropdown (populated via live data) ────────────────────────────────

test.describe("Symbol filter with live data", () => {
  test.beforeEach(async ({ page }) => {
    await mockSocketIO(page, [
      { name: "signal", data: SIGNAL_AAPL_BUY },
      { name: "signal", data: SIGNAL_TSLA_SELL },
    ]);
    await gotoAndWait(page);
  });

  test("Symbol dropdown starts with 'All Symbols' selected", async ({ page }) => {
    const symbolSelect = page.locator("select").nth(0);
    await expect(symbolSelect).toHaveValue("ALL");
  });

  test("Symbol dropdown contains 'All Symbols' option", async ({ page }) => {
    const allOption = page.locator("select").nth(0).locator("option", { hasText: "All Symbols" });
    await expect(allOption).toHaveCount(1);
  });
});

// ── Model dropdown (populated via live data) ─────────────────────────────────

test.describe("Model filter with live data", () => {
  test.beforeEach(async ({ page }) => {
    await mockSocketIO(page, [
      { name: "signal", data: SIGNAL_AAPL_BUY },
      { name: "signal", data: SIGNAL_TSLA_SELL },
    ]);
    await gotoAndWait(page);
  });

  test("Model dropdown starts with 'All Models' selected", async ({ page }) => {
    const modelSelect = page.locator("select").nth(1);
    await expect(modelSelect).toHaveValue("ALL");
  });

  test("Model dropdown contains 'All Models' option", async ({ page }) => {
    const allOption = page.locator("select").nth(1).locator("option", { hasText: "All Models" });
    await expect(allOption).toHaveCount(1);
  });
});
