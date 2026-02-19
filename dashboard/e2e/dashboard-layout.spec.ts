/**
 * E2E – Dashboard Layout
 *
 * Verifies that every major UI region renders correctly on initial page load.
 * These tests do not require a live backend; the Socket.IO endpoint is mocked
 * so the app starts in a clean "connected-but-no-data" state.
 */

import { test, expect } from "@playwright/test";
import { gotoAndWait, mockSocketIO } from "./helpers";

test.describe("Dashboard Layout", () => {
  test.beforeEach(async ({ page }) => {
    await mockSocketIO(page);
    await gotoAndWait(page);
  });

  // ── Header ──────────────────────────────────────────────────────────────

  test("renders the TitanFlow heading", async ({ page }) => {
    await expect(page.getByRole("heading", { level: 1 })).toContainText("TitanFlow");
  });

  test("shows the PAPER MODE label in the header", async ({ page }) => {
    await expect(page.getByText("PAPER MODE")).toBeVisible();
  });

  test("shows the Kill Switch button", async ({ page }) => {
    await expect(page.getByRole("button", { name: /kill switch/i })).toBeVisible();
  });

  // ── Status badges ────────────────────────────────────────────────────────

  test("shows Market Feed status badge", async ({ page }) => {
    await expect(page.getByText("Market Feed")).toBeVisible();
  });

  test("shows Redis status badge", async ({ page }) => {
    await expect(page.getByText("Redis")).toBeVisible();
  });

  test("shows execution Mode badge", async ({ page }) => {
    await expect(page.getByText(/Mode:/)).toBeVisible();
  });

  test("shows Last Update badge", async ({ page }) => {
    await expect(page.getByText(/Last Update:/)).toBeVisible();
  });

  test("shows Latency badge", async ({ page }) => {
    await expect(page.getByText(/Latency:/)).toBeVisible();
  });

  test("shows Socket connection status badge", async ({ page }) => {
    await expect(page.getByText(/Socket:/)).toBeVisible();
  });

  // ── Global Filters ───────────────────────────────────────────────────────

  test("renders the Symbol filter dropdown", async ({ page }) => {
    await expect(page.getByText("Symbol")).toBeVisible();
    await expect(page.locator("select").filter({ hasText: "All Symbols" })).toBeVisible();
  });

  test("renders the Model filter dropdown", async ({ page }) => {
    await expect(page.getByText("Model")).toBeVisible();
    await expect(page.locator("select").filter({ hasText: "All Models" })).toBeVisible();
  });

  test("renders the Signal Type filter dropdown with All / BUY / SELL options", async ({ page }) => {
    await expect(page.getByText("Signal Type")).toBeVisible();
    const signalSelect = page.locator("select").filter({ hasText: "All" }).nth(0);
    await expect(signalSelect.locator("option", { hasText: "BUY" })).toHaveCount(1);
    await expect(signalSelect.locator("option", { hasText: "SELL" })).toHaveCount(1);
  });

  test("renders all four Time Range buttons", async ({ page }) => {
    for (const label of ["15M", "1H", "4H", "1D"]) {
      await expect(page.getByRole("button", { name: label })).toBeVisible();
    }
  });

  // ── Metrics Grid ─────────────────────────────────────────────────────────

  test("renders all four metrics cards", async ({ page }) => {
    for (const label of ["Paper PnL", "Best Model", "Avg Win Rate", "Active Models"]) {
      await expect(page.getByText(label)).toBeVisible();
    }
  });

  // ── Model Leaderboard ────────────────────────────────────────────────────

  test("renders the Model Leaderboard section heading", async ({ page }) => {
    await expect(page.getByText("Model Leaderboard")).toBeVisible();
  });

  test("shows leaderboard table column headers", async ({ page }) => {
    for (const header of ["Model", "PnL", "PnL %", "Win Rate", "Max DD", "Trades", "Open Pos"]) {
      await expect(page.getByRole("button", { name: header })).toBeVisible();
    }
  });

  test("shows empty leaderboard placeholder text when no data", async ({ page }) => {
    await expect(page.getByText("Waiting for paper portfolio data...")).toBeVisible();
  });

  // ── Signal Feed ──────────────────────────────────────────────────────────

  test("shows the Signal Feed empty-state message when no signals", async ({ page }) => {
    await expect(page.getByText("Waiting for signals...")).toBeVisible();
  });

  // ── Trade Log ────────────────────────────────────────────────────────────

  test("renders Trade Log table column headers", async ({ page }) => {
    for (const header of ["Time", "Sym", "Side", "Qty", "Price", "PnL", "Insight", "Status"]) {
      await expect(page.getByRole("columnheader", { name: header })).toBeVisible();
    }
  });

  test("shows Trade Log Strategy / Model header column", async ({ page }) => {
    await expect(page.getByRole("columnheader", { name: /strategy/i })).toBeVisible();
  });
});
