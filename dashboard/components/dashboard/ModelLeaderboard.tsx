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
    "text-left text-[10px] uppercase font-bold tracking-wider text-slate-400 hover:text-white transition-colors group flex items-center gap-1";

  return (
    <div className="glass-card p-4 relative overflow-hidden group/card shadow-xl border border-white/5 bg-slate-900/30 backdrop-blur-sm">
      <div className="absolute inset-0 bg-gradient-to-br from-white/5 to-transparent pointer-events-none"></div>
      <div className="flex items-center justify-between mb-4 relative z-10">
        <h2 className="text-lg font-semibold">Model Leaderboard</h2>
        <span className="text-xs text-muted-foreground">{rows.length} contenders</span>
      </div>
      <div className="overflow-x-auto relative z-10">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-white/10 bg-black/40">
              <th className="py-3 px-4">
                <button type="button" className={headerButtonClass} onClick={() => requestSort("model_name")}>
                  Model
                </button>
              </th>
              <th className="py-3 px-4 text-right">
                <button type="button" className={headerButtonClass} onClick={() => requestSort("pnl")}>
                  PnL
                </button>
              </th>
              <th className="py-3 px-4 text-right">
                <button type="button" className={headerButtonClass} onClick={() => requestSort("pnl_pct")}>
                  PnL %
                </button>
              </th>
              <th className="py-3 px-4 text-right">
                <button type="button" className={headerButtonClass} onClick={() => requestSort("win_rate")}>
                  Win Rate
                </button>
              </th>
              <th className="py-3 px-4 text-right">
                <button type="button" className={headerButtonClass} onClick={() => requestSort("max_drawdown_pct")}>
                  Max DD
                </button>
              </th>
              <th className="py-3 px-4 text-right">
                <button type="button" className={headerButtonClass} onClick={() => requestSort("trades")}>
                  Trades
                </button>
              </th>
              <th className="py-3 pl-4 text-right">
                <button type="button" className={headerButtonClass} onClick={() => requestSort("open_positions")}>
                  Open Pos
                </button>
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-white/5">
            {sortedRows.length === 0 && (
              <tr>
                <td colSpan={7} className="py-12 text-center text-slate-400">
                  <div className="flex flex-col items-center justify-center gap-3 animate-pulse">
                    <div className="w-6 h-6 rounded-full border-2 border-cyan-500/30 border-t-cyan-400 animate-spin"></div>
                    Waiting for paper portfolio data...
                  </div>
                </td>
              </tr>
            )}
            {sortedRows.map((row) => (
              <tr key={row.model_id} className="hover:bg-cyan-950/20 transition-all duration-200 group relative">
                <td className="py-3 px-4 font-bold text-white tracking-wide">
                  <div className="absolute left-0 top-0 bottom-0 w-0.5 bg-cyan-500 opacity-0 group-hover:opacity-100 transition-opacity"></div>
                  {row.model_name}
                </td>
                <td className={`py-4 px-4 text-right font-mono font-bold tracking-wider ${safeNumber(row.pnl) >= 0 ? "text-emerald-400 drop-shadow-[0_0_8px_rgba(52,211,153,0.3)]" : "text-rose-400 drop-shadow-[0_0_8px_rgba(244,63,94,0.3)]"}`}>
                  {safeNumber(row.pnl) >= 0 ? "+" : "-"}${Math.abs(safeNumber(row.pnl)).toFixed(2)}
                </td>
                <td className={`py-4 px-4 text-right font-mono font-semibold ${safeNumber(row.pnl_pct) >= 0 ? "text-emerald-400" : "text-rose-400"}`}>
                  <span className="bg-white/5 px-2 py-0.5 rounded-md border border-white/5">{formatSignedPercent(safeNumber(row.pnl_pct))}</span>
                </td>
                <td className="py-4 px-4 text-right font-mono text-cyan-300 font-semibold">{safeNumber(row.win_rate).toFixed(1)}%</td>
                <td className="py-4 px-4 text-right font-mono text-amber-400 font-semibold drop-shadow-[0_0_8px_rgba(251,191,36,0.3)]">
                  {safeNumber(row.max_drawdown_pct).toFixed(2)}%
                </td>
                <td className="py-4 px-4 text-right font-mono text-slate-300 group-hover:text-white transition-colors">{safeNumber(row.trades)}</td>
                <td className="py-4 pl-4 text-right font-mono text-slate-300 group-hover:text-white transition-colors">{safeNumber(row.open_positions)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
