"use client";

import {
  Area,
  CartesianGrid,
  ComposedChart,
  Line,
  ResponsiveContainer,
  Scatter,
  Tooltip,
  XAxis,
  YAxis,
  ReferenceLine,
} from "recharts";
import { ForecastRecord, MarkerRecord, PriceRecord } from "@/components/dashboard/types";

const FORECAST_COLORS: Record<string, string> = {
  "TFT_Transformer_v1": "#a78bfa",    // purple
  "LightGBM_v1": "#fb923c",           // orange
  "SMA_Crossover_v1": "#38bdf8",      // sky blue
  "Momentum Falcon": "#f472b6",       // pink
  "Mean Revert Atlas": "#34d399",     // emerald
  "Macro Pulse": "#fbbf24",           // amber
  "Volatility Weaver": "#818cf8",     // indigo
};

function getForecastColor(modelName: string): string {
  return FORECAST_COLORS[modelName] || "#94a3b8";
}

interface PriceChartProps {
  symbol: string;
  points: PriceRecord[];
  markers: MarkerRecord[];
  forecasts?: ForecastRecord[];
}

function formatTime(value: number): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "--:--:--";
  }
  // Use ISO string for deterministic server/client rendering to avoid hydration errors
  return date.toISOString().substring(11, 19);
}

export default function PriceChart({ symbol, points, markers, forecasts = [] }: PriceChartProps) {
  const chartData = points.map((point) => ({
    timestamp: point.timestamp,
    value: point.price,
  }));

  // Add forecast endpoints to extend the chart domain
  const forecastPoints = forecasts.map((f) => ({
    timestamp: f.forecastTimestamp,
    [`forecast_${f.modelName}`]: f.forecastPrice,
  }));

  // Merge forecast points into chart data so the X domain extends
  const allData = [...chartData];
  forecastPoints.forEach((fp) => {
    allData.push({ timestamp: fp.timestamp, value: undefined as unknown as number });
  });

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

  // Build forecast line datasets: each forecast becomes a 2-point line
  const forecastLineData = forecasts.map((f) => ({
    modelName: f.modelName,
    signal: f.signal,
    color: getForecastColor(f.modelName),
    data: [
      { timestamp: f.currentTimestamp, value: f.currentPrice },
      { timestamp: f.forecastTimestamp, value: f.forecastPrice },
    ],
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

  // Compute X domain to include forecasts
  const allTimestamps = [
    ...chartData.map((d) => d.timestamp),
    ...forecasts.map((f) => f.forecastTimestamp),
  ];
  const xMin = Math.min(...allTimestamps);
  const xMax = Math.max(...allTimestamps);

  // Compute Y domain to include forecast prices
  const allPrices = [
    ...chartData.map((d) => d.value).filter(Boolean),
    ...forecasts.map((f) => f.forecastPrice),
    ...forecasts.map((f) => f.currentPrice),
  ];
  const yMin = Math.min(...allPrices) * 0.999;
  const yMax = Math.max(...allPrices) * 1.001;

  return (
    <div className="w-full h-full min-h-[340px]">
      <div className="flex items-center justify-between mb-4 px-2 text-xs tracking-wider text-slate-400 font-medium uppercase">
        <span className="flex items-center gap-2"><span className="w-2 h-2 rounded-full bg-cyan-500 animate-pulse"></span> {symbol} price stream</span>
        <div className="flex items-center gap-3">
          {forecasts.length > 0 && (
            <span className="flex items-center gap-2">
              {forecasts.map((f) => (
                <span key={f.id} className="flex items-center gap-1">
                  <span className="w-2 h-2 rounded-full" style={{ backgroundColor: getForecastColor(f.modelName) }}></span>
                  <span className="text-[10px]">{f.modelName}</span>
                </span>
              ))}
            </span>
          )}
          <span className="bg-white/5 px-2 py-1 rounded-md border border-white/10">{markers.length} decision markers</span>
        </div>
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
            domain={[xMin, xMax]}
            tick={{ fontSize: 13, fill: "#94a3b8" }}
            tickFormatter={formatTime}
            axisLine={false}
            tickLine={false}
          />
          <YAxis
            domain={[yMin, yMax]}
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

          {chartData.length > 0 && (
            <ReferenceLine
              x={chartData[chartData.length - 1].timestamp}
              stroke="#f59e0b"
              strokeDasharray="3 3"
              label={{
                position: "insideTopLeft",
                value: "NOW",
                fill: "#f59e0b",
                fontSize: 10,
                fontWeight: "bold",
              }}
            />
          )}

          {/* Render forecast lines as dashed Line segments */}
          {forecastLineData.map((forecast, idx) => {
            const dataKey = `forecast_${idx}`;
            // Create a merged dataset with the forecast points
            const mergedData = [
              ...chartData.map((d) => ({ ...d, [dataKey]: undefined })),
              ...forecast.data.map((d) => ({ timestamp: d.timestamp, value: undefined, [dataKey]: d.value })),
            ].sort((a, b) => a.timestamp - b.timestamp);

            return (
              <Line
                key={forecast.modelName + idx}
                data={mergedData}
                dataKey={dataKey}
                stroke={forecast.color}
                strokeWidth={2}
                strokeDasharray="6 4"
                dot={{ r: 4, fill: forecast.color, stroke: "#0f172a", strokeWidth: 2 }}
                connectNulls={true}
                isAnimationActive={false}
                style={{ filter: `drop-shadow(0 0 6px ${forecast.color}66)` }}
              />
            );
          })}
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}
