"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import io from "socket.io-client";
import GlobalFilters from "@/components/dashboard/GlobalFilters";
import Header from "@/components/dashboard/Header";
import MetricsGrid from "@/components/dashboard/MetricsGrid";
import ModelLeaderboard from "@/components/dashboard/ModelLeaderboard";
import PriceChart from "@/components/dashboard/PriceChart";
import SignalFeed from "@/components/dashboard/SignalFeed";
import TradeLog from "@/components/dashboard/TradeLog";
import {
  FilterState,
  LeaderboardRow,
  MarkerRecord,
  ModelOption,
  PriceRecord,
  SignalRecord,
  SystemStatus,
  TradeRecord,
} from "@/components/dashboard/types";

const RANGE_MS = {
  "15M": 15 * 60 * 1000,
  "1H": 60 * 60 * 1000,
  "4H": 4 * 60 * 60 * 1000,
  "1D": 24 * 60 * 60 * 1000,
} as const;

const INITIAL_FILTERS: FilterState = {
  symbol: "ALL",
  model: "ALL",
  signalType: "ALL",
  timeRange: "1H",
};

interface SignalEventPayload {
  symbol?: string;
  signal?: string;
  confidence?: number;
  price?: number;
  timestamp?: string | number;
  model_id?: string;
  model_name?: string;
  explanation?: Array<{ feature?: string; impact?: number }>;
}

interface TradeEventPayload {
  id?: string;
  symbol?: string;
  side?: string;
  qty?: number;
  price?: number;
  status?: string;
  timestamp?: string | number;
  model_id?: string;
  model_name?: string;
  realized_pnl?: number;
  explanation?: string[];
}

interface PriceEventPayload {
  symbol?: string;
  price?: number;
  timestamp?: string | number;
}

interface ServerStatusPayload {
  redisConnected?: boolean;
  executionMode?: string;
}

interface PortfolioModelPayload {
  model_id: string;
  model_name: string;
  cash: number;
  equity: number;
  pnl: number;
  pnl_pct: number;
  realized_pnl: number;
  trades: number;
  wins: number;
  win_rate: number;
  open_positions: number;
  /** Populated by the backend once ≥2 equity snapshots exist. */
  max_drawdown_pct?: number;
  /** Populated by the backend once ≥5 equity snapshots exist. null = insufficient data. */
  sortino_ratio?: number | null;
  /** Populated by the backend once ≥2 snapshots exist and drawdown > 0. */
  calmar_ratio?: number | null;
}

interface PortfolioPayload {
  mode?: string;
  models?: PortfolioModelPayload[];
}

interface DrawdownState {
  peak: number;
  maxDrawdownPct: number;
}

interface InternalStatus {
  socketConnected: boolean;
  redisConnected: boolean;
  executionMode: string;
  latencyMs: number | null;
  lastMarketTick: number | null;
  lastSignal: number | null;
  lastTrade: number | null;
}

type TradeSignalRecord = SignalRecord & { signal: "BUY" | "SELL" };

function safeNumber(value: unknown, fallback = 0): number {
  const num = Number(value);
  return Number.isFinite(num) ? num : fallback;
}

function normalizeTimestamp(value: unknown): number {
  if (typeof value === "number") {
    if (value > 1e15) return Math.floor(value / 1e6);
    if (value > 1e12) return Math.floor(value);
    if (value > 1e9) return Math.floor(value * 1000);
  }
  if (typeof value === "string") {
    const parsed = Date.parse(value);
    if (!Number.isNaN(parsed)) return parsed;
  }
  return Date.now();
}

function makeId(prefix: string): string {
  const random = Math.random().toString(36).slice(2, 10);
  return `${prefix}-${Date.now()}-${random}`;
}

function formatSignalExplanation(explanation: SignalEventPayload["explanation"]): string[] {
  if (!explanation || explanation.length === 0) {
    return [];
  }
  return explanation.map((item) => {
    const feature = item.feature ?? "feature";
    const impact = Number(item.impact ?? 0);
    return `${feature} (${impact.toFixed(2)})`;
  });
}

export default function DashboardShell() {
  const [filters, setFilters] = useState<FilterState>(INITIAL_FILTERS);
  const [signals, setSignals] = useState<SignalRecord[]>([]);
  const [trades, setTrades] = useState<TradeRecord[]>([]);
  const [prices, setPrices] = useState<PriceRecord[]>([]);
  const [leaderboardRows, setLeaderboardRows] = useState<LeaderboardRow[]>([]);
  const [status, setStatus] = useState<InternalStatus>({
    socketConnected: false,
    redisConnected: false,
    executionMode: "paper",
    latencyMs: null,
    lastMarketTick: null,
    lastSignal: null,
    lastTrade: null,
  });
  const [clock, setClock] = useState<number>(0);

  const drawdownStateRef = useRef<Record<string, DrawdownState>>({});
  const signalsRef = useRef<SignalRecord[]>([]);

  useEffect(() => {
    signalsRef.current = signals;
  }, [signals]);

  useEffect(() => {
    const socket = io({
      path: "/api/socket/io",
      addTrailingSlash: false,
    });

    socket.on("connect", () => {
      setStatus((previous) => ({ ...previous, socketConnected: true }));
    });

    socket.on("disconnect", () => {
      setStatus((previous) => ({ ...previous, socketConnected: false }));
    });

    socket.on("server_status", (payload: ServerStatusPayload) => {
      setStatus((previous) => ({
        ...previous,
        redisConnected: Boolean(payload.redisConnected),
        executionMode: payload.executionMode || previous.executionMode,
      }));
    });

    socket.on("price_update", (payload: PriceEventPayload) => {
      if (!payload.symbol || typeof payload.price !== "number" || payload.price <= 0) {
        return;
      }
      const timestamp = normalizeTimestamp(payload.timestamp);
      setPrices((previous) =>
        [...previous, { symbol: payload.symbol as string, price: payload.price as number, timestamp }].slice(-4000)
      );
      setStatus((previous) => ({ ...previous, lastMarketTick: timestamp }));
    });

    socket.on("signal", (payload: SignalEventPayload) => {
      if (!payload.symbol || !payload.signal) {
        return;
      }
      const signalValue = String(payload.signal).toUpperCase();
      if (signalValue !== "BUY" && signalValue !== "SELL" && signalValue !== "HOLD") {
        return;
      }

      const timestamp = normalizeTimestamp(payload.timestamp);
      const next: SignalRecord = {
        id: makeId("signal"),
        symbol: payload.symbol,
        signal: signalValue,
        confidence: Number(payload.confidence ?? 0),
        price: Number(payload.price ?? 0),
        timestamp,
        modelId: payload.model_id || "unknown_model",
        modelName: payload.model_name || payload.model_id || "Unknown",
        explanation: formatSignalExplanation(payload.explanation),
      };
      setSignals((previous) => [next, ...previous].slice(0, 400));
      setStatus((previous) => ({ ...previous, lastSignal: timestamp }));
    });

    socket.on("trade_update", (payload: TradeEventPayload) => {
      if (!payload.symbol || !payload.side) {
        return;
      }
      const side = String(payload.side).toUpperCase();
      if (side !== "BUY" && side !== "SELL") {
        return;
      }

      const timestamp = normalizeTimestamp(payload.timestamp);
      const qty = Number(payload.qty ?? 0);
      const price = Number(payload.price ?? 0);
      const realizedPnl = Number(payload.realized_pnl ?? 0);
      const inferredEntryPrice =
        side === "SELL" && qty > 0 ? Number((price - realizedPnl / qty).toFixed(4)) : null;

      const modelId = payload.model_id || "unknown_model";
      const modelName = payload.model_name || modelId;

      const matchedSignal = signalsRef.current.find(
        (signal) =>
          signal.symbol === payload.symbol &&
          signal.modelId === modelId &&
          signal.timestamp <= timestamp
      );
      const explanation =
        payload.explanation && payload.explanation.length > 0
          ? payload.explanation
          : matchedSignal?.explanation ?? [];

      const next: TradeRecord = {
        id: payload.id || makeId("trade"),
        symbol: payload.symbol,
        side,
        qty,
        price,
        timestamp,
        status: payload.status || "FILLED",
        modelId,
        modelName,
        realizedPnl,
        inferredEntryPrice,
        explanation,
      };

      setTrades((previous) => [next, ...previous].slice(0, 400));
      setStatus((previous) => ({ ...previous, lastTrade: timestamp }));
    });

    socket.on("paper_portfolios", (payload: PortfolioPayload) => {
      const models = payload.models || [];
      const rows: LeaderboardRow[] = models.map((model) => {
        const modelId = model?.model_id || "unknown_model";
        const equity = safeNumber(model?.equity);
        const cash = safeNumber(model?.cash);
        const pnl = safeNumber(model?.pnl, equity - cash);
        const pnlPct = safeNumber(model?.pnl_pct);
        const realizedPnl = safeNumber(model?.realized_pnl);
        const trades = safeNumber(model?.trades);
        const wins = safeNumber(model?.wins);
        const winRate = safeNumber(model?.win_rate);
        const openPositions = safeNumber(model?.open_positions);

        const previous = drawdownStateRef.current[modelId] || {
          peak: equity,
          maxDrawdownPct: 0,
        };

        const peak = Math.max(previous.peak, equity);
        const drawdownPct = peak > 0 ? ((equity - peak) / peak) * 100 : 0;
        const clientMaxDrawdownPct = Math.min(previous.maxDrawdownPct, drawdownPct);

        drawdownStateRef.current[modelId] = { peak, maxDrawdownPct: clientMaxDrawdownPct };

        // Prefer the backend's authoritative drawdown (computed from full equity curve);
        // fall back to the client-side running peak tracker for legacy payloads.
        const serverMaxDD = model?.max_drawdown_pct != null ? safeNumber(model.max_drawdown_pct) : null;
        const maxDrawdownPct = serverMaxDD !== null ? serverMaxDD : Math.abs(clientMaxDrawdownPct);

        // Risk-adjusted metrics — null until enough equity snapshots have accumulated.
        const sortinoRatio = model?.sortino_ratio != null ? safeNumber(model.sortino_ratio) : null;
        const calmarRatio = model?.calmar_ratio != null ? safeNumber(model.calmar_ratio) : null;

        return {
          model_id: modelId,
          model_name: model?.model_name || modelId,
          cash,
          equity,
          pnl,
          pnl_pct: pnlPct,
          realized_pnl: realizedPnl,
          trades,
          wins,
          win_rate: winRate,
          open_positions: openPositions,
          max_drawdown_pct: maxDrawdownPct,
          sortino_ratio: sortinoRatio,
          calmar_ratio: calmarRatio,
        };
      });

      setLeaderboardRows(rows);
      const nextMode = payload.mode || "paper";
      setStatus((previous) => ({ ...previous, executionMode: nextMode }));
    });

    const latencyInterval = setInterval(() => {
      if (!socket.connected) {
        return;
      }
      const sentAt = Date.now();
      socket.emit("latency_ping", sentAt, (response: { clientSentAt?: number }) => {
        const base = typeof response?.clientSentAt === "number" ? response.clientSentAt : sentAt;
        setStatus((previous) => ({
          ...previous,
          latencyMs: Math.max(1, Date.now() - base),
        }));
      });
    }, 5000);

    return () => {
      clearInterval(latencyInterval);
      socket.disconnect();
    };
  }, []);

  useEffect(() => {
    const interval = setInterval(() => {
      setClock(Date.now());
    }, 1000);
    return () => clearInterval(interval);
  }, []);

  const availableSymbols = useMemo(() => {
    const set = new Set<string>();
    prices.forEach((item) => set.add(item.symbol));
    signals.forEach((item) => set.add(item.symbol));
    trades.forEach((item) => set.add(item.symbol));
    return [...set].sort();
  }, [prices, signals, trades]);

  const modelOptions = useMemo(() => {
    const map = new Map<string, string>();
    leaderboardRows.forEach((row) => map.set(row.model_id, row.model_name));
    signals.forEach((signal) => map.set(signal.modelId, signal.modelName));
    trades.forEach((trade) => map.set(trade.modelId, trade.modelName));
    const options: ModelOption[] = [...map.entries()].map(([id, name]) => ({ id, name }));
    options.sort((left, right) => left.name.localeCompare(right.name));
    return options;
  }, [leaderboardRows, signals, trades]);

  const rangeCutoff = useMemo(() => clock - RANGE_MS[filters.timeRange], [clock, filters.timeRange]);
  const chartSymbol = filters.symbol === "ALL" ? availableSymbols[0] || "SPY" : filters.symbol;

  const filteredSignals = useMemo(
    () =>
      signals.filter((signal) => {
        if (signal.timestamp < rangeCutoff) return false;
        if (filters.symbol !== "ALL" && signal.symbol !== filters.symbol) return false;
        if (filters.model !== "ALL" && signal.modelId !== filters.model) return false;
        if (filters.signalType !== "ALL" && signal.signal !== filters.signalType) return false;
        return true;
      }),
    [filters.model, filters.signalType, filters.symbol, rangeCutoff, signals]
  );

  const filteredTrades = useMemo(
    () =>
      trades.filter((trade) => {
        if (trade.timestamp < rangeCutoff) return false;
        if (filters.symbol !== "ALL" && trade.symbol !== filters.symbol) return false;
        if (filters.model !== "ALL" && trade.modelId !== filters.model) return false;
        if (filters.signalType !== "ALL" && trade.side !== filters.signalType) return false;
        return true;
      }),
    [filters.model, filters.signalType, filters.symbol, rangeCutoff, trades]
  );

  const chartPoints = useMemo(
    () =>
      prices
        .filter((point) => point.symbol === chartSymbol && point.timestamp >= rangeCutoff)
        .slice(-350),
    [chartSymbol, prices, rangeCutoff]
  );

  const chartMarkers = useMemo(
    () =>
      filteredSignals
        .filter(
          (signal) => (signal.signal === "BUY" || signal.signal === "SELL") && signal.symbol === chartSymbol
        )
        .map((signal) => signal as TradeSignalRecord)
        .map<MarkerRecord>((signal) => ({
          id: signal.id,
          symbol: signal.symbol,
          signal: signal.signal,
          modelName: signal.modelName,
          confidence: signal.confidence,
          price: signal.price,
          timestamp: signal.timestamp,
        }))
        .slice(0, 100),
    [chartSymbol, filteredSignals]
  );

  const visibleLeaderboardRows = useMemo(() => {
    if (filters.model === "ALL") {
      return leaderboardRows;
    }
    return leaderboardRows.filter((row) => row.model_id === filters.model);
  }, [filters.model, leaderboardRows]);

  const systemStatus: SystemStatus = useMemo(() => {
    const lastUpdate = Math.max(
      status.lastMarketTick ?? 0,
      status.lastSignal ?? 0,
      status.lastTrade ?? 0
    );
    const marketFeedConnected =
      status.socketConnected &&
      status.lastMarketTick !== null &&
      clock - status.lastMarketTick < 15000;

    return {
      socketConnected: status.socketConnected,
      redisConnected: status.redisConnected,
      executionMode: status.executionMode,
      marketFeedConnected,
      latencyMs: status.latencyMs,
      lastUpdate: lastUpdate > 0 ? lastUpdate : null,
    };
  }, [clock, status]);

  return (
    <main className="min-h-screen bg-background text-foreground flex flex-col">
      <Header status={systemStatus} />

      <div className="flex-1 p-6 grid grid-cols-12 gap-6 max-w-[1920px] mx-auto w-full">
        <div className="col-span-12">
          <GlobalFilters filters={filters} symbols={availableSymbols} models={modelOptions} onChange={setFilters} />
        </div>

        <div className="col-span-12 lg:col-span-8 flex flex-col gap-6">
          <MetricsGrid rows={visibleLeaderboardRows} />
          <ModelLeaderboard rows={visibleLeaderboardRows} />
          <div className="glass-card flex-1 p-6 min-h-[500px] flex flex-col">
            <h2 className="text-xl font-semibold tracking-tight text-white/90 mb-4">
              Market Overview ({chartSymbol})
            </h2>
            <div className="flex-1 w-full h-full min-h-[380px]">
              <PriceChart symbol={chartSymbol} points={chartPoints} markers={chartMarkers} />
            </div>
          </div>
        </div>

        <div className="col-span-12 lg:col-span-4 flex flex-col gap-6">
          <div className="glass-card flex-1 p-0 flex flex-col max-h-[600px] overflow-hidden">
            <div className="p-4 border-b border-white/5 bg-white/5 backdrop-blur-sm">
              <h2 className="text-lg font-semibold flex items-center gap-2">
                <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse"></span>
                Signal Feed
              </h2>
            </div>
            <SignalFeed signals={filteredSignals.slice(0, 120)} />
          </div>

          <div className="glass-card flex-1 p-4 min-h-[300px]">
            <h2 className="text-lg font-semibold mb-4">Recent Executions</h2>
            <TradeLog trades={filteredTrades.slice(0, 120)} />
          </div>
        </div>
      </div>
    </main>
  );
}
