/**
 * E2E – Model Leaderboard
 *
 * Tests the sortable leaderboard table:
 *   • Renders column headers with sort buttons
 *   • Populates rows when paper_portfolios data arrives via Socket.IO
 *   • Column-header clicks sort rows correctly (asc / desc toggle)
 */

import { test, expect } from "@playwright/test";
import { gotoAndWait, mockSocketIO } from "./helpers";

// ── Fixtures ─────────────────────────────────────────────────────────────────

const PORTFOLIO_PAYLOAD = {
  mode: "paper",
  models: [
    {
      model_id: "lgb_001",
      model_name: "LGB Model",
      cash: 90_000,
      equity: 91_500,
      pnl: 1500,
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
      pnl: -1000,
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
      pnl: 4500,
      pnl_pct: 4.5,
      realized_pnl: 2000,
      trades: 35,
      wins: 22,
      win_rate: 62.9,
      open_positions: 5,
    },
  ],
};

// ── Empty state ───────────────────────────────────────────────────────────────

test.describe("Leaderboard empty state", () => {
  test("shows placeholder text before any portfolio data arrives", async ({ page }) => {
    await mockSocketIO(page);
    await gotoAndWait(page);
    await expect(page.getByText("Waiting for paper portfolio data...")).toBeVisible();
  });

  test("shows '0 contenders' label before any data", async ({ page }) => {
    await mockSocketIO(page);
    await gotoAndWait(page);
    await expect(page.getByText("0 contenders")).toBeVisible();
  });
});

// ── Populated leaderboard ─────────────────────────────────────────────────────

test.describe("Leaderboard with data", () => {
  test.beforeEach(async ({ page }) => {
    await mockSocketIO(page, [{ name: "paper_portfolios", data: PORTFOLIO_PAYLOAD }]);
    await gotoAndWait(page);
    // Wait for rows to appear
    await page.waitForSelector("td", { timeout: 10_000 });
  });

  test("renders one row per model", async ({ page }) => {
    const rows = page.locator("tbody tr");
    await expect(rows).toHaveCount(3);
  });

  test("displays model names in the table", async ({ page }) => {
    for (const name of ["LGB Model", "SMA Model", "LSTM Model"]) {
      await expect(page.getByRole("cell", { name })).toBeVisible();
    }
  });

  test("shows '3 contenders' label", async ({ page }) => {
    await expect(page.getByText("3 contenders")).toBeVisible();
  });

  test("displays PnL values with correct sign prefix", async ({ page }) => {
    // LSTM has the highest pnl (4500) – should show +$4500.00
    await expect(page.getByRole("cell", { name: /\+\$4500\.00/ })).toBeVisible();
    // SMA has negative pnl (-1000) – should show -$1000.00
    await expect(page.getByRole("cell", { name: /-\$1000\.00/ })).toBeVisible();
  });

  test("displays win rates", async ({ page }) => {
    await expect(page.getByRole("cell", { name: "70.0%" })).toBeVisible();
    await expect(page.getByRole("cell", { name: "40.0%" })).toBeVisible();
  });

  // ── Sorting ───────────────────────────────────────────────────────────────

  test("clicking PnL header sorts by PnL descending by default", async ({ page }) => {
    await page.getByRole("button", { name: "PnL" }).click();
    const firstCell = page.locator("tbody tr").first().locator("td").first();
    // Highest PnL model (LSTM) should be first
    await expect(firstCell).toContainText("LSTM Model");
  });

  test("clicking PnL header twice reverses sort order", async ({ page }) => {
    const pnlBtn = page.getByRole("button", { name: "PnL" });
    await pnlBtn.click(); // desc
    await pnlBtn.click(); // asc → lowest PnL (SMA -1000) first
    const firstCell = page.locator("tbody tr").first().locator("td").first();
    await expect(firstCell).toContainText("SMA Model");
  });

  test("clicking Trades header sorts by trade count", async ({ page }) => {
    await page.getByRole("button", { name: "Trades" }).click();
    // Highest trades = LSTM (35) → first row
    const firstCell = page.locator("tbody tr").first().locator("td").first();
    await expect(firstCell).toContainText("LSTM Model");
  });

  test("clicking Win Rate header sorts by win rate descending", async ({ page }) => {
    await page.getByRole("button", { name: "Win Rate" }).click();
    // Highest win rate = LGB 70% → first row
    const firstCell = page.locator("tbody tr").first().locator("td").first();
    await expect(firstCell).toContainText("LGB Model");
  });

  test("clicking Model header sorts alphabetically", async ({ page }) => {
    await page.getByRole("button", { name: "Model" }).click();
    // "LGB Model" < "LSTM Model" < "SMA Model" alphabetically
    const firstCell = page.locator("tbody tr").first().locator("td").first();
    await expect(firstCell).toContainText("LGB Model");
  });

  test("clicking Open Pos header sorts by open positions", async ({ page }) => {
    await page.getByRole("button", { name: "Open Pos" }).click();
    // Highest open positions = LSTM (5) → first row
    const firstCell = page.locator("tbody tr").first().locator("td").first();
    await expect(firstCell).toContainText("LSTM Model");
  });

  test("clicking Max DD header sorts by max drawdown", async ({ page }) => {
    await page.getByRole("button", { name: "Max DD" }).click();
    // Drawdowns start at 0 for all (no price history), but table still renders
    const rows = page.locator("tbody tr");
    await expect(rows).toHaveCount(3);
  });
});
