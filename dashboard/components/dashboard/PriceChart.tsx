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
  "TFT_Transformer_v1": "#a78bfa",
  "LightGBM_v1": "#fb923c",
  "SMA_Crossover_v1": "#38bdf8",
  "Momentum Falcon": "#f472b6",
  "Mean Revert Atlas": "#34d399",
  "Macro Pulse": "#fbbf24",
  "Volatility Weaver": "#818cf8",
  "RandomForestPulse_v1": "#4ade80",
  "LogisticRegime_v1": "#f9a8d4",
  "LSTM_Attention_v1": "#c084fc",
  "Ensemble": "#facc15",
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
  if (Number.isNaN(date.getTime())) return "--:--:--";
  return date.toISOString().substring(11, 19);
}

// Custom dot rendered at the forecast endpoint showing the predicted price
function ForecastEndpointDot(props: {
  cx?: number;
  cy?: number;
  payload?: { timestamp: number; [key: string]: unknown };
  dataKey?: string | number | ((obj: unknown) => unknown);
  color: string;
  forecastPrice: number;
  signal: "BUY" | "SELL";
  isForecastPoint: boolean;
}) {
  const { cx, cy, color, forecastPrice, signal, isForecastPoint } = props;
  if (!isForecastPoint || cx == null || cy == null) return null;

  const isUp = signal === "BUY";
  const labelBg = isUp ? "#064e3b" : "#4c0519";
  const labelBorder = isUp ? "#10b981" : "#f43f5e";
  const labelText = isUp ? "#34d399" : "#fb7185";
  const priceStr = `$${forecastPrice.toFixed(2)}`;
  const labelW = priceStr.length * 7 + 16;
  const labelH = 20;
  const labelX = cx - labelW / 2;
  const labelY = cy - labelH - 10;

  return (
    <g>
      {/* Glow ring */}
      <circle cx={cx} cy={cy} r={10} fill={color} opacity={0.2} />
      {/* Outer ring */}
      <circle cx={cx} cy={cy} r={6} fill="#0f172a" stroke={color} strokeWidth={2} />
      {/* Inner dot */}
      <circle cx={cx} cy={cy} r={3} fill={color} />

      {/* Price bubble */}
      <rect
        x={labelX}
        y={labelY}
        width={labelW}
        height={labelH}
        rx={4}
        fill={labelBg}
        stroke={labelBorder}
        strokeWidth={1}
        opacity={0.95}
      />
      <text
        x={cx}
        y={labelY + labelH / 2 + 4}
        textAnchor="middle"
        fill={labelText}
        fontSize={10}
        fontWeight="bold"
        fontFamily="monospace"
      >
        {priceStr}
      </text>

      {/* Arrow connector from bubble to dot */}
      <line
        x1={cx}
        y1={labelY + labelH}
        x2={cx}
        y2={cy - 6}
        stroke={color}
        strokeWidth={1}
        opacity={0.6}
      />
    </g>
  );
}

export default function PriceChart({ symbol, points, markers, forecasts = [] }: PriceChartProps) {
  const chartData = points.map((point) => ({
    timestamp: point.timestamp,
    value: point.price,
  }));

  const buyMarkers = markers
    .filter((m) => m.signal === "BUY")
    .map((m) => ({ timestamp: m.timestamp, value: m.price, modelName: m.modelName, confidence: m.confidence, signal: m.signal }));

  const sellMarkers = markers
    .filter((m) => m.signal === "SELL")
    .map((m) => ({ timestamp: m.timestamp, value: m.price, modelName: m.modelName, confidence: m.confidence, signal: m.signal }));

  // Build 2-point line datasets for each forecast
  const forecastLineData = forecasts.map((f) => ({
    modelName: f.modelName,
    signal: f.signal,
    color: getForecastColor(f.modelName),
    forecastPrice: f.forecastPrice,
    data: [
      { timestamp: f.currentTimestamp, value: f.currentPrice, isForecast: false },
      { timestamp: f.forecastTimestamp, value: f.forecastPrice, isForecast: true },
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

  const allTimestamps = [
    ...chartData.map((d) => d.timestamp),
    ...forecasts.map((f) => f.forecastTimestamp),
  ];
  const xMin = Math.min(...allTimestamps);
  // Pad the right edge at least 1 min beyond the last price point so the
  // forecast dot is never clipped at the chart boundary.
  const latestDataTs = chartData[chartData.length - 1].timestamp;
  const xMax = Math.max(...allTimestamps, latestDataTs + 90 * 1000);

  const allPrices = [
    ...chartData.map((d) => d.value).filter(Boolean),
    ...forecasts.map((f) => f.forecastPrice),
    ...forecasts.map((f) => f.currentPrice),
  ];
  const yMin = Math.min(...allPrices) * 0.9985;
  const yMax = Math.max(...allPrices) * 1.0015;

  const nowTs = chartData[chartData.length - 1].timestamp;

  return (
    <div className="w-full h-full min-h-[340px]">
      {/* Legend */}
      <div className="flex items-center justify-between mb-4 px-2 text-xs tracking-wider text-slate-400 font-medium uppercase">
        <span className="flex items-center gap-2">
          <span className="w-2 h-2 rounded-full bg-cyan-500 animate-pulse"></span>
          {symbol} price stream
        </span>
        <div className="flex items-center gap-3 flex-wrap justify-end">
          {forecasts.length > 0 && (
            <span className="flex items-center gap-2 flex-wrap">
              <span className="text-slate-500 mr-1">1-min forecast:</span>
              {forecasts.map((f) => (
                <span key={f.id} className="flex items-center gap-1">
                  <span
                    className="inline-block w-4 border-t-2 border-dashed"
                    style={{ borderColor: getForecastColor(f.modelName) }}
                  />
                  <span className="text-[10px]" style={{ color: getForecastColor(f.modelName) }}>
                    {f.modelName}
                  </span>
                </span>
              ))}
            </span>
          )}
          <span className="bg-white/5 px-2 py-1 rounded-md border border-white/10">
            {markers.length} decision markers
          </span>
        </div>
      </div>

      <ResponsiveContainer width="100%" height="100%" minWidth={0} minHeight={300}>
        <ComposedChart data={chartData} margin={{ top: 30, right: 10, left: -20, bottom: 0 }}>
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
                  <span key="1" className={entry.payload.signal === "BUY" ? "text-emerald-400 font-bold" : "text-rose-400 font-bold"}>
                    {entry.payload.signal} ${Number(value).toFixed(2)} (<span className="text-cyan-400">{confidence.toFixed(0)}%</span> via {entry.payload.modelName})
                  </span>,
                  <span key="2" className="text-slate-400 text-xs">Decision</span>,
                ];
              }
              return [<span key="1" className="text-white font-mono font-bold">${Number(value).toFixed(2)}</span>, <span key="2" className="text-cyan-500 text-xs">Price</span>];
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
            style={{ filter: "drop-shadow(0 0 8px rgba(6,182,212,0.4))" }}
          />

          <Scatter data={buyMarkers} dataKey="value" fill="#10b981" />
          <Scatter data={sellMarkers} dataKey="value" fill="#f43f5e" />

          {/* NOW vertical reference line */}
          {chartData.length > 0 && (
            <ReferenceLine
              x={nowTs}
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

          {/* +1m vertical reference line */}
          {forecasts.length > 0 && (
            <ReferenceLine
              x={nowTs + 60 * 1000}
              stroke="#94a3b8"
              strokeDasharray="2 4"
              strokeOpacity={0.4}
              label={{
                position: "insideTopRight",
                value: "+1m",
                fill: "#94a3b8",
                fontSize: 10,
              }}
            />
          )}

          {/* Forecast dashed lines from signal price → predicted price */}
          {forecastLineData.map((forecast, idx) => {
            const dataKey = `fc_${idx}`;
            const mergedData = [
              ...chartData.map((d) => ({ ...d, [dataKey]: undefined as number | undefined, isForecast: false })),
              ...forecast.data.map((d) => ({
                timestamp: d.timestamp,
                value: undefined as number | undefined,
                [dataKey]: d.value,
                isForecast: d.isForecast,
              })),
            ].sort((a, b) => a.timestamp - b.timestamp);

            return (
              <Line
                key={forecast.modelName + idx}
                data={mergedData}
                dataKey={dataKey}
                stroke={forecast.color}
                strokeWidth={2.5}
                strokeDasharray="6 4"
                connectNulls={true}
                isAnimationActive={false}
                style={{ filter: `drop-shadow(0 0 6px ${forecast.color}88)` }}
                dot={(dotProps) => {
                  const payload = dotProps.payload as { isForecast?: boolean; timestamp: number };
                  return (
                    <ForecastEndpointDot
                      key={`dot-${idx}-${payload.timestamp}`}
                      {...dotProps}
                      color={forecast.color}
                      forecastPrice={forecast.forecastPrice}
                      signal={forecast.signal}
                      isForecastPoint={Boolean(payload.isForecast)}
                    />
                  );
                }}
              />
            );
          })}
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}
