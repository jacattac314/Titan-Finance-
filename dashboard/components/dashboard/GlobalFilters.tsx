"use client";

import { FilterState, ModelOption, TimeRange } from "@/components/dashboard/types";

interface GlobalFiltersProps {
  filters: FilterState;
  symbols: string[];
  models: ModelOption[];
  onChange: (next: FilterState) => void;
}

const timeRanges: TimeRange[] = ["15M", "1H", "4H", "1D"];

export default function GlobalFilters({ filters, symbols, models, onChange }: GlobalFiltersProps) {
  return (
    <div className="glass-card p-4 flex flex-wrap items-end gap-3">
      <div className="min-w-[140px]">
        <label className="block text-xs uppercase tracking-wide text-muted-foreground mb-1">Symbol</label>
        <select
          value={filters.symbol}
          onChange={(event) => onChange({ ...filters, symbol: event.target.value })}
          className="w-full rounded-md bg-white/5 border border-white/10 px-3 py-2 text-sm"
        >
          <option value="ALL">All Symbols</option>
          {symbols.map((symbol) => (
            <option key={symbol} value={symbol}>
              {symbol}
            </option>
          ))}
        </select>
      </div>

      <div className="min-w-[180px]">
        <label className="block text-xs uppercase tracking-wide text-muted-foreground mb-1">Model</label>
        <select
          value={filters.model}
          onChange={(event) => onChange({ ...filters, model: event.target.value })}
          className="w-full rounded-md bg-white/5 border border-white/10 px-3 py-2 text-sm"
        >
          <option value="ALL">All Models</option>
          {models.map((model) => (
            <option key={model.id} value={model.id}>
              {model.name}
            </option>
          ))}
        </select>
      </div>

      <div className="min-w-[140px]">
        <label className="block text-xs uppercase tracking-wide text-muted-foreground mb-1">Signal Type</label>
        <select
          value={filters.signalType}
          onChange={(event) =>
            onChange({ ...filters, signalType: event.target.value as FilterState["signalType"] })
          }
          className="w-full rounded-md bg-white/5 border border-white/10 px-3 py-2 text-sm"
        >
          <option value="ALL">All</option>
          <option value="BUY">BUY</option>
          <option value="SELL">SELL</option>
        </select>
      </div>

      <div className="min-w-[200px] flex-1">
        <label className="block text-xs uppercase tracking-wide text-muted-foreground mb-1">Time Range</label>
        <div className="flex gap-2">
          {timeRanges.map((range) => (
            <button
              key={range}
              type="button"
              onClick={() => onChange({ ...filters, timeRange: range })}
              className={`px-3 py-2 rounded-md text-xs font-semibold border transition ${
                filters.timeRange === range
                  ? "bg-cyan-500/20 text-cyan-300 border-cyan-400/40"
                  : "bg-white/5 text-muted-foreground border-white/10 hover:bg-white/10"
              }`}
            >
              {range}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
