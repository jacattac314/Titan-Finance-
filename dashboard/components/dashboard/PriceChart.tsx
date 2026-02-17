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
      <div className="w-full h-full min-h-[340px] flex items-center justify-center rounded-lg border border-white/10 bg-white/5 text-sm text-muted-foreground">
        Waiting for live {symbol} market data...
      </div>
    );
  }

  return (
    <div className="w-full h-full min-h-[340px]">
      <div className="flex items-center justify-between mb-3 text-xs text-muted-foreground">
        <span>{symbol} price stream</span>
        <span>{markers.length} decision markers</span>
      </div>
      <ResponsiveContainer width="100%" height="100%" minWidth={0} minHeight={300}>
        <ComposedChart data={chartData}>
          <defs>
            <linearGradient id="colorValue" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor="#3b82f6" stopOpacity={0.3} />
              <stop offset="95%" stopColor="#3b82f6" stopOpacity={0} />
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
            contentStyle={{ backgroundColor: "#0f172a", border: "1px solid #1e293b", borderRadius: "8px" }}
            labelStyle={{ color: "#94a3b8" }}
            labelFormatter={(value) => formatTime(Number(value))}
            formatter={(value, name, entry) => {
              if (name === "value" && entry.payload.signal) {
                const confidence = Number(entry.payload.confidence || 0) * 100;
                return [
                  `${entry.payload.signal} ${Number(value).toFixed(2)} (${confidence.toFixed(0)}%) via ${entry.payload.modelName}`,
                  "Decision",
                ];
              }
              return [Number(value).toFixed(2), "Price"];
            }}
          />

          <Area
            type="monotone"
            dataKey="value"
            stroke="#3b82f6"
            strokeWidth={2}
            fillOpacity={1}
            fill="url(#colorValue)"
            isAnimationActive={false}
          />

          <Scatter data={buyMarkers} dataKey="value" fill="#34d399" />
          <Scatter data={sellMarkers} dataKey="value" fill="#fb7185" />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}
