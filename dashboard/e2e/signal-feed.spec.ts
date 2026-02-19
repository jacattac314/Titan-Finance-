/**
 * E2E – Signal Feed & Trade Log
 *
 * Tests:
 *   • Signal Feed populates when "signal" socket events arrive
 *   • Trade Log populates when "trade_update" events arrive
 *   • Trade Log "Analyze" (Insight) button opens the explanation modal
 *   • Modal can be dismissed
 */

import { test, expect } from "@playwright/test";
import { gotoAndWait, mockSocketIO } from "./helpers";

// ── Fixtures ─────────────────────────────────────────────────────────────────

const BUY_SIGNAL = {
  symbol: "AAPL",
  signal: "BUY",
  confidence: 0.87,
  price: 150.5,
  timestamp: new Date("2024-06-01T14:00:00Z").getTime(),
  model_id: "lgb_001",
  model_name: "LGB Model",
  explanation: [
    { feature: "momentum", impact: 0.52 },
    { feature: "volume_spike", impact: 0.31 },
  ],
};

const SELL_SIGNAL = {
  symbol: "TSLA",
  signal: "SELL",
  confidence: 0.72,
  price: 210.0,
  timestamp: new Date("2024-06-01T14:01:00Z").getTime(),
  model_id: "sma_001",
  model_name: "SMA Model",
  explanation: [{ feature: "mean_reversion", impact: -0.41 }],
};

const FILLED_TRADE = {
  id: "trade-abc-123",
  symbol: "AAPL",
  side: "BUY",
  qty: 10,
  price: 150.5,
  status: "FILLED",
  timestamp: new Date("2024-06-01T14:00:05Z").getTime(),
  model_id: "lgb_001",
  model_name: "LGB Model",
  realized_pnl: 0,
  explanation: ["Strong upward momentum detected", "Volume 2× average"],
};

// ── Signal Feed ───────────────────────────────────────────────────────────────

test.describe("Signal Feed", () => {
  test("shows empty-state text before any signals arrive", async ({ page }) => {
    await mockSocketIO(page);
    await gotoAndWait(page);
    await expect(page.getByText("Waiting for signals...")).toBeVisible();
  });

  test("renders a BUY signal card when a signal event is received", async ({ page }) => {
    await mockSocketIO(page, [{ name: "signal", data: BUY_SIGNAL }]);
    await gotoAndWait(page);

    // Wait for the signal card to appear
    await expect(page.getByText("AAPL")).toBeVisible({ timeout: 10_000 });
    await expect(page.getByText("BUY")).toBeVisible();
  });

  test("renders a SELL signal card", async ({ page }) => {
    await mockSocketIO(page, [{ name: "signal", data: SELL_SIGNAL }]);
    await gotoAndWait(page);

    await expect(page.getByText("TSLA")).toBeVisible({ timeout: 10_000 });
    await expect(page.getByText("SELL")).toBeVisible();
  });

  test("shows confidence percentage on signal card", async ({ page }) => {
    await mockSocketIO(page, [{ name: "signal", data: BUY_SIGNAL }]);
    await gotoAndWait(page);

    // 0.87 confidence → "87% Conf"
    await expect(page.getByText(/87%\s*Conf/)).toBeVisible({ timeout: 10_000 });
  });

  test("shows model name on signal card", async ({ page }) => {
    await mockSocketIO(page, [{ name: "signal", data: BUY_SIGNAL }]);
    await gotoAndWait(page);

    await expect(page.getByText("LGB Model")).toBeVisible({ timeout: 10_000 });
  });

  test("shows price on signal card", async ({ page }) => {
    await mockSocketIO(page, [{ name: "signal", data: BUY_SIGNAL }]);
    await gotoAndWait(page);

    await expect(page.getByText(/\$150\.50/)).toBeVisible({ timeout: 10_000 });
  });

  test("renders multiple signal cards", async ({ page }) => {
    await mockSocketIO(page, [
      { name: "signal", data: BUY_SIGNAL },
      { name: "signal", data: SELL_SIGNAL },
    ]);
    await gotoAndWait(page);

    await expect(page.getByText("AAPL")).toBeVisible({ timeout: 10_000 });
    await expect(page.getByText("TSLA")).toBeVisible({ timeout: 10_000 });
  });
});

// ── Trade Log ─────────────────────────────────────────────────────────────────

test.describe("Trade Log", () => {
  test.beforeEach(async ({ page }) => {
    await mockSocketIO(page, [{ name: "trade_update", data: FILLED_TRADE }]);
    await gotoAndWait(page);
    // Wait for the trade row to appear in the table
    await expect(page.getByRole("cell", { name: "AAPL" })).toBeVisible({ timeout: 10_000 });
  });

  test("displays the trade symbol", async ({ page }) => {
    await expect(page.getByRole("cell", { name: "AAPL" })).toBeVisible();
  });

  test("displays BUY side with correct text", async ({ page }) => {
    await expect(page.getByRole("cell", { name: "BUY" }).first()).toBeVisible();
  });

  test("displays trade quantity", async ({ page }) => {
    await expect(page.getByRole("cell", { name: "10" })).toBeVisible();
  });

  test("displays trade price", async ({ page }) => {
    await expect(page.getByRole("cell", { name: /150\.50/ }).first()).toBeVisible();
  });

  test("shows FILLED status badge", async ({ page }) => {
    await expect(page.getByText("FILLED")).toBeVisible();
  });

  test("Analyze button opens the explanation modal", async ({ page }) => {
    const analyzeBtn = page.getByRole("button", { name: /analyze/i });
    await expect(analyzeBtn).toBeVisible();
    await analyzeBtn.click();

    // Modal heading
    await expect(page.getByRole("heading", { name: "Trade Logic" })).toBeVisible();
  });

  test("explanation modal contains trade explanation lines", async ({ page }) => {
    await page.getByRole("button", { name: /analyze/i }).click();
    await expect(page.getByText("Strong upward momentum detected")).toBeVisible();
    await expect(page.getByText("Volume 2× average")).toBeVisible();
  });

  test("'Close Analysis' button closes the modal", async ({ page }) => {
    await page.getByRole("button", { name: /analyze/i }).click();
    await expect(page.getByRole("heading", { name: "Trade Logic" })).toBeVisible();

    await page.getByRole("button", { name: "Close Analysis" }).click();
    await expect(page.getByRole("heading", { name: "Trade Logic" })).not.toBeVisible();
  });

  test("clicking outside the modal closes it", async ({ page }) => {
    await page.getByRole("button", { name: /analyze/i }).click();
    await expect(page.getByRole("heading", { name: "Trade Logic" })).toBeVisible();

    // Click the backdrop (outside modal box)
    await page.locator(".fixed.inset-0").click({ position: { x: 10, y: 10 } });
    await expect(page.getByRole("heading", { name: "Trade Logic" })).not.toBeVisible();
  });
});
