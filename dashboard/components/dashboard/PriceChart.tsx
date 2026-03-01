"use client";

import {
  Area,
  CartesianGrid,
  ComposedChart,
  ResponsiveContainer,
  Scatter,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { MarkerRecord, PriceRecord } from "@/components/dashboard/types";

interface PriceChartProps {
  symbol: string;
  points: PriceRecord[];
  markers: MarkerRecord[];
}

function formatTime(value: number): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "--:--:--";
  }
  // Use ISO string for deterministic server/client rendering to avoid hydration errors
  return date.toISOString().substring(11, 19);
}

export default function PriceChart({ symbol, points, markers }: PriceChartProps) {
  const chartData = points.map((point) => ({
    timestamp: point.timestamp,
    value: point.price,
  }));

  const buyMarkers = markers
    .filter((marker) => marker.signal === "BUY")
    .map((marker) => ({
      timestamp: marker.timestamp,
      value: marker.price,
      modelName: marker.modelName,
      confidence: marker.confidence,
      signal: marker.signal,
    }));

  const sellMarkers = markers
    .filter((marker) => marker.signal === "SELL")
    .map((marker) => ({
      timestamp: marker.timestamp,
      value: marker.price,
      modelName: marker.modelName,
      confidence: marker.confidence,
      signal: marker.signal,
    }));

  if (chartData.length === 0) {
    return (
      <div className="w-full h-full min-h-[340px] flex items-center justify-center rounded-xl border border-white/5 bg-white/5 backdrop-blur-sm text-sm text-slate-400 shadow-inner">
        <div className="flex flex-col items-center gap-3 animate-pulse">
          <div className="w-8 h-8 rounded-full border-2 border-cyan-500/30 border-t-cyan-400 animate-spin"></div>
          Waiting for live <span className="text-cyan-400 font-bold">{symbol}</span> market data...
        </div>
      </div>
    );
  }

  return (
    <div className="w-full h-full min-h-[340px]">
      <div className="flex items-center justify-between mb-4 px-2 text-xs tracking-wider text-slate-400 font-medium uppercase">
        <span className="flex items-center gap-2"><span className="w-2 h-2 rounded-full bg-cyan-500 animate-pulse"></span> {symbol} price stream</span>
        <span className="bg-white/5 px-2 py-1 rounded-md border border-white/10">{markers.length} decision markers</span>
      </div>
      <ResponsiveContainer width="100%" height="100%" minWidth={0} minHeight={300}>
        <ComposedChart data={chartData} margin={{ top: 10, right: 0, left: -20, bottom: 0 }}>
          <defs>
            <linearGradient id="colorValue" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor="#06b6d4" stopOpacity={0.4} />
              <stop offset="95%" stopColor="#06b6d4" stopOpacity={0} />
            </linearGradient>
          </defs>

          <CartesianGrid strokeDasharray="3 3" opacity={0.1} vertical={false} />
          <XAxis
            dataKey="timestamp"
            type="number"
            domain={["dataMin", "dataMax"]}
            tick={{ fontSize: 12, fill: "#64748b" }}
            tickFormatter={formatTime}
            axisLine={false}
            tickLine={false}
          />
          <YAxis
            domain={["auto", "auto"]}
            orientation="right"
            tick={{ fontSize: 12, fill: "#64748b" }}
            axisLine={false}
            tickLine={false}
            width={60}
          />
          <Tooltip
            contentStyle={{ backgroundColor: "rgba(15, 23, 42, 0.85)", backdropFilter: "blur(12px)", border: "1px solid rgba(255,255,255,0.1)", borderRadius: "12px", boxShadow: "0 8px 32px rgba(0,0,0,0.4)" }}
            itemStyle={{ color: "#e2e8f0", fontWeight: 600 }}
            labelStyle={{ color: "#94a3b8", marginBottom: "4px", fontSize: "12px", textTransform: "uppercase", letterSpacing: "0.05em" }}
            labelFormatter={(value) => formatTime(Number(value))}
            formatter={(value, name, entry) => {
              if (name === "value" && entry.payload.signal) {
                const confidence = Number(entry.payload.confidence || 0) * 100;
                return [
                  <span key="1" className={entry.payload.signal === 'BUY' ? 'text-emerald-400 font-bold' : 'text-rose-400 font-bold'}>
                    {entry.payload.signal} ${Number(value).toFixed(2)} (<span className="text-cyan-400">{confidence.toFixed(0)}%</span> via {entry.payload.modelName})
                  </span>,
                  <span key="2" className="text-slate-400 text-xs">Decision</span>,
                ];
              }
              return [<span key="1" className="text-white font-mono font-bold">${Number(value).toFixed(2)}</span>, <span key="2" className="text-slate-400 text-xs text-cyan-500">Price</span>];
            }}
          />

          <Area
            type="monotone"
            dataKey="value"
            stroke="#06b6d4"
            strokeWidth={3}
            fillOpacity={1}
            fill="url(#colorValue)"
            isAnimationActive={false}
            style={{ filter: 'drop-shadow(0 0 8px rgba(6,182,212,0.4))' }}
          />

          <Scatter data={buyMarkers} dataKey="value" fill="#10b981" />
          <Scatter data={sellMarkers} dataKey="value" fill="#f43f5e" />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}
