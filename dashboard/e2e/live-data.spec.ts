/**
 * E2E – Live Data & Metrics Grid
 *
 * Tests that Socket.IO events correctly update the React state and are
 * reflected in the Metrics Grid and status badges.
 *
 * All backend calls are intercepted via the mockSocketIO helper so no
 * real Redis / service infrastructure is required.
 */

import { test, expect } from "@playwright/test";
import { gotoAndWait, mockSocketIO } from "./helpers";

// ── Fixtures ─────────────────────────────────────────────────────────────────

const PORTFOLIO_ONE_MODEL = {
  mode: "paper",
  models: [
    {
      model_id: "lgb_001",
      model_name: "LGB Model",
      cash: 90_000,
      equity: 91_500,
      pnl: 1_500,
      pnl_pct: 1.5,
      realized_pnl: 800,
      trades: 20,
      wins: 14,
      win_rate: 70,
      open_positions: 2,
    },
  ],
};

const PORTFOLIO_THREE_MODELS = {
  mode: "paper",
  models: [
    {
      model_id: "lgb_001",
      model_name: "LGB Model",
      cash: 90_000,
      equity: 91_500,
      pnl: 1_500,
      pnl_pct: 1.5,
      realized_pnl: 800,
      trades: 20,
      wins: 14,
      win_rate: 70,
      open_positions: 2,
    },
    {
      model_id: "sma_001",
      model_name: "SMA Model",
      cash: 95_000,
      equity: 94_000,
      pnl: -1_000,
      pnl_pct: -1.0,
      realized_pnl: -500,
      trades: 10,
      wins: 4,
      win_rate: 40,
      open_positions: 0,
    },
    {
      model_id: "lstm_001",
      model_name: "LSTM Model",
      cash: 88_000,
      equity: 92_500,
      pnl: 4_500,
      pnl_pct: 4.5,
      realized_pnl: 2_000,
      trades: 35,
      wins: 22,
      win_rate: 62.9,
      open_positions: 5,
    },
  ],
};

const PRICE_EVENT = {
  symbol: "AAPL",
  price: 150.5,
  timestamp: Date.now(),
};

// ── Metrics Grid – empty state ────────────────────────────────────────────────

test.describe("Metrics Grid – no data", () => {
  test.beforeEach(async ({ page }) => {
    await mockSocketIO(page);
    await gotoAndWait(page);
  });

  test("Paper PnL shows $0 and 0 models with no data", async ({ page }) => {
    await expect(page.getByText("+$0.00")).toBeVisible();
    await expect(page.getByText("0 models")).toBeVisible();
  });

  test("Best Model shows 'Waiting' placeholder with no data", async ({ page }) => {
    await expect(page.getByText("Waiting")).toBeVisible();
  });

  test("Avg Win Rate shows 0.0% with no data", async ({ page }) => {
    await expect(page.getByText("0.0%")).toBeVisible();
  });

  test("Active Models shows 0 with no data", async ({ page }) => {
    // The Active Models value card should show "0"
    const activeModelsCard = page.locator(".glass-card").filter({ hasText: "Active Models" });
    await expect(activeModelsCard.getByText("0")).toBeVisible();
  });
});

// ── Metrics Grid – single model ───────────────────────────────────────────────

test.describe("Metrics Grid – one model", () => {
  test.beforeEach(async ({ page }) => {
    await mockSocketIO(page, [{ name: "paper_portfolios", data: PORTFOLIO_ONE_MODEL }]);
    await gotoAndWait(page);
    await page.waitForSelector("td", { timeout: 10_000 });
  });

  test("Paper PnL reflects the model's pnl", async ({ page }) => {
    await expect(page.getByText("+$1500.00")).toBeVisible();
  });

  test("shows '1 models' next to Paper PnL", async ({ page }) => {
    await expect(page.getByText("1 models")).toBeVisible();
  });

  test("Best Model shows the single model's name", async ({ page }) => {
    const bestModelCard = page.locator(".glass-card").filter({ hasText: "Best Model" });
    await expect(bestModelCard.getByText("LGB Model")).toBeVisible();
  });

  test("Best Model shows the PnL percentage", async ({ page }) => {
    // 1.5% pnl_pct
    await expect(page.getByText("+1.50%")).toBeVisible();
  });

  test("Active Models count equals 1", async ({ page }) => {
    const activeModelsCard = page.locator(".glass-card").filter({ hasText: "Active Models" });
    await expect(activeModelsCard.getByText("1")).toBeVisible();
  });
});

// ── Metrics Grid – multiple models ────────────────────────────────────────────

test.describe("Metrics Grid – three models", () => {
  test.beforeEach(async ({ page }) => {
    await mockSocketIO(page, [{ name: "paper_portfolios", data: PORTFOLIO_THREE_MODELS }]);
    await gotoAndWait(page);
    await page.waitForSelector("td", { timeout: 10_000 });
  });

  test("Paper PnL is the sum of all model PnLs", async ({ page }) => {
    // 1500 + (-1000) + 4500 = 5000
    await expect(page.getByText("+$5000.00")).toBeVisible();
  });

  test("shows '3 models' label", async ({ page }) => {
    await expect(page.getByText("3 models")).toBeVisible();
  });

  test("Active Models count equals 3", async ({ page }) => {
    const activeModelsCard = page.locator(".glass-card").filter({ hasText: "Active Models" });
    await expect(activeModelsCard.getByText("3")).toBeVisible();
  });

  test("Avg Win Rate shows the average of all models", async ({ page }) => {
    // (70 + 40 + 62.9) / 3 ≈ 57.6%
    const winRateCard = page.locator(".glass-card").filter({ hasText: "Avg Win Rate" });
    await expect(winRateCard.getByText(/57\.\d%/)).toBeVisible();
  });
});

// ── Server status reflection ──────────────────────────────────────────────────

test.describe("System Status badges", () => {
  test("shows execution mode from server_status event", async ({ page }) => {
    await mockSocketIO(page);
    await gotoAndWait(page);
    // The mockSocketIO helper always injects server_status with executionMode: 'paper'
    await expect(page.getByText(/paper/i).first()).toBeVisible({ timeout: 10_000 });
  });
});

// ── Price data ────────────────────────────────────────────────────────────────

test.describe("Price chart area", () => {
  test("renders a chart container even without price data", async ({ page }) => {
    await mockSocketIO(page);
    await gotoAndWait(page);
    // The recharts container has class 'recharts-wrapper'
    await expect(page.locator(".recharts-wrapper").first()).toBeVisible();
  });

  test("renders chart after price_update event", async ({ page }) => {
    await mockSocketIO(page, [{ name: "price_update", data: PRICE_EVENT }]);
    await gotoAndWait(page);
    await expect(page.locator(".recharts-wrapper").first()).toBeVisible({ timeout: 10_000 });
  });
});
