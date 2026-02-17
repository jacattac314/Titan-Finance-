"use client";

import { useMemo, useState } from "react";
import { LeaderboardRow } from "@/components/dashboard/types";

type SortKey =
  | "model_name"
  | "pnl"
  | "pnl_pct"
  | "win_rate"
  | "max_drawdown_pct"
  | "trades"
  | "open_positions";

interface ModelLeaderboardProps {
  rows: LeaderboardRow[];
}

function safeNumber(value: unknown, fallback = 0): number {
  const num = Number(value);
  return Number.isFinite(num) ? num : fallback;
}

function formatSignedPercent(value: number): string {
  return `${value >= 0 ? "+" : ""}${value.toFixed(2)}%`;
}

export default function ModelLeaderboard({ rows }: ModelLeaderboardProps) {
  const [sortKey, setSortKey] = useState<SortKey>("pnl");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");

  const sortedRows = useMemo(() => {
    const copy = [...rows];
    copy.sort((left, right) => {
      const leftValue = left[sortKey];
      const rightValue = right[sortKey];

      if (typeof leftValue === "string" && typeof rightValue === "string") {
        return sortDir === "asc"
          ? leftValue.localeCompare(rightValue)
          : rightValue.localeCompare(leftValue);
      }

      const delta = Number(leftValue) - Number(rightValue);
      return sortDir === "asc" ? delta : -delta;
    });
    return copy;
  }, [rows, sortDir, sortKey]);

  const requestSort = (next: SortKey) => {
    if (next === sortKey) {
      setSortDir((previous) => (previous === "asc" ? "desc" : "asc"));
      return;
    }
    setSortKey(next);
    setSortDir("desc");
  };

  const headerButtonClass =
    "text-left text-xs uppercase tracking-wide text-muted-foreground hover:text-white transition-colors";

  return (
    <div className="glass-card p-4">
      <div className="flex items-center justify-between mb-3">
        <h2 className="text-lg font-semibold">Model Leaderboard</h2>
        <span className="text-xs text-muted-foreground">{rows.length} contenders</span>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-white/10">
              <th className="py-2 pr-3">
                <button type="button" className={headerButtonClass} onClick={() => requestSort("model_name")}>
                  Model
                </button>
              </th>
              <th className="py-2 px-2 text-right">
                <button type="button" className={headerButtonClass} onClick={() => requestSort("pnl")}>
                  PnL
                </button>
              </th>
              <th className="py-2 px-2 text-right">
                <button type="button" className={headerButtonClass} onClick={() => requestSort("pnl_pct")}>
                  PnL %
                </button>
              </th>
              <th className="py-2 px-2 text-right">
                <button type="button" className={headerButtonClass} onClick={() => requestSort("win_rate")}>
                  Win Rate
                </button>
              </th>
              <th className="py-2 px-2 text-right">
                <button type="button" className={headerButtonClass} onClick={() => requestSort("max_drawdown_pct")}>
                  Max DD
                </button>
              </th>
              <th className="py-2 px-2 text-right">
                <button type="button" className={headerButtonClass} onClick={() => requestSort("trades")}>
                  Trades
                </button>
              </th>
              <th className="py-2 pl-2 text-right">
                <button type="button" className={headerButtonClass} onClick={() => requestSort("open_positions")}>
                  Open Pos
                </button>
              </th>
            </tr>
          </thead>
          <tbody>
            {sortedRows.length === 0 && (
              <tr>
                <td colSpan={7} className="py-6 text-center text-muted-foreground">
                  Waiting for paper portfolio data...
                </td>
              </tr>
            )}
            {sortedRows.map((row) => (
              <tr key={row.model_id} className="border-b border-white/5 hover:bg-white/5">
                <td className="py-3 pr-3 font-semibold">{row.model_name}</td>
                <td className={`py-3 px-2 text-right font-mono ${safeNumber(row.pnl) >= 0 ? "text-emerald-400" : "text-rose-400"}`}>
                  {safeNumber(row.pnl) >= 0 ? "+" : "-"}${Math.abs(safeNumber(row.pnl)).toFixed(2)}
                </td>
                <td className={`py-3 px-2 text-right font-mono ${safeNumber(row.pnl_pct) >= 0 ? "text-emerald-400" : "text-rose-400"}`}>
                  {formatSignedPercent(safeNumber(row.pnl_pct))}
                </td>
                <td className="py-3 px-2 text-right font-mono">{safeNumber(row.win_rate).toFixed(1)}%</td>
                <td className="py-3 px-2 text-right font-mono text-amber-300">
                  {safeNumber(row.max_drawdown_pct).toFixed(2)}%
                </td>
                <td className="py-3 px-2 text-right font-mono">{safeNumber(row.trades)}</td>
                <td className="py-3 pl-2 text-right font-mono">{safeNumber(row.open_positions)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
