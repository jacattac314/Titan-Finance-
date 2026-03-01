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

const SIMULATED_SYMBOLS = ["SPY", "QQQ", "NVDA", "AAPL"];
const SIMULATED_MODELS = [
  { id: "model-alpha", name: "Momentum Falcon" },
  { id: "model-beta", name: "Mean Revert Atlas" },
  { id: "model-gamma", name: "Macro Pulse" },
  { id: "model-delta", name: "Volatility Weaver" },
];
const STARTING_CASH = 100_000;
const DAY_STEPS = 42;

interface SimulatedPosition {
  symbol: string;
  qty: number;
  entryPrice: number;
}

interface SimulatedModelState {
  model_id: string;
  model_name: string;
  cash: number;
  realized_pnl: number;
  trades: number;
  wins: number;
  open_positions: SimulatedPosition[];
}

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
  if (!explanation || !Array.isArray(explanation) || explanation.length === 0) {
    return [];
  }
  return explanation.map((item: any) => {
    if (typeof item === "string") {
      return item;
    }
    const feature = item?.feature ?? "feature";
    const impact = Number(item?.impact ?? 0);
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
  const receivedLiveDataRef = useRef(false);

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
      receivedLiveDataRef.current = true;
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
      receivedLiveDataRef.current = true;
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
      receivedLiveDataRef.current = true;
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
        const maxDrawdownPct = Math.min(previous.maxDrawdownPct, drawdownPct);

        drawdownStateRef.current[modelId] = { peak, maxDrawdownPct };

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
          max_drawdown_pct: Math.abs(maxDrawdownPct),
        };
      });

      setLeaderboardRows(rows);
      receivedLiveDataRef.current = true;
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
    const simulatedModels: SimulatedModelState[] = SIMULATED_MODELS.map((model) => ({
      model_id: model.id,
      model_name: model.name,
      cash: STARTING_CASH,
      realized_pnl: 0,
      trades: 0,
      wins: 0,
      open_positions: [],
    }));

    const priceBySymbol = Object.fromEntries(
      SIMULATED_SYMBOLS.map((symbol, index) => [symbol, 95 + index * 22])
    ) as Record<string, number>;

    let dayStep = 0;
    let previousTick = Date.now();

    const portfolioRows = (): LeaderboardRow[] =>
      simulatedModels.map((model) => {
        const openValue = model.open_positions.reduce(
          (sum, position) => sum + position.qty * priceBySymbol[position.symbol],
          0
        );
        const equity = model.cash + openValue;
        const pnl = equity - STARTING_CASH;

        const previous = drawdownStateRef.current[model.model_id] || {
          peak: equity,
          maxDrawdownPct: 0,
        };
        const peak = Math.max(previous.peak, equity);
        const drawdownPct = peak > 0 ? ((equity - peak) / peak) * 100 : 0;
        const maxDrawdownPct = Math.min(previous.maxDrawdownPct, drawdownPct);
        drawdownStateRef.current[model.model_id] = { peak, maxDrawdownPct };

        return {
          model_id: model.model_id,
          model_name: model.model_name,
          cash: model.cash,
          equity,
          pnl,
          pnl_pct: (pnl / STARTING_CASH) * 100,
          realized_pnl: model.realized_pnl,
          trades: model.trades,
          wins: model.wins,
          win_rate: model.trades > 0 ? (model.wins / model.trades) * 100 : 0,
          open_positions: model.open_positions.length,
          max_drawdown_pct: Math.abs(maxDrawdownPct),
        };
      });

    const closeAllPositions = (timestamp: number) => {
      simulatedModels.forEach((model) => {
        model.open_positions.forEach((position) => {
          const exitPrice = priceBySymbol[position.symbol];
          const realizedPnl = (exitPrice - position.entryPrice) * position.qty;
          model.cash += position.qty * exitPrice;
          model.realized_pnl += realizedPnl;
          model.trades += 1;
          if (realizedPnl > 0) model.wins += 1;

          const liquidationTrade: TradeRecord = {
            id: makeId('trade'),
            symbol: position.symbol,
            side: 'SELL',
            qty: position.qty,
            price: exitPrice,
            timestamp,
            status: 'EOD_LIQUIDATION',
            modelId: model.model_id,
            modelName: model.model_name,
            realizedPnl,
            inferredEntryPrice: position.entryPrice,
            explanation: ['End-of-day risk reset'],
          };

          setTrades((previous) => [liquidationTrade, ...previous].slice(0, 400));
        });
        model.open_positions = [];
      });
    };

    const interval = setInterval(() => {
      if (receivedLiveDataRef.current) {
        return;
      }

      const timestamp = Date.now();
      const tickLatency = Math.max(1, timestamp - previousTick);
      previousTick = timestamp;
      dayStep += 1;

      SIMULATED_SYMBOLS.forEach((symbol) => {
        const drift = (Math.random() - 0.48) * 0.014;
        priceBySymbol[symbol] = Number((priceBySymbol[symbol] * (1 + drift)).toFixed(2));
      });

      const nextPrices: PriceRecord[] = SIMULATED_SYMBOLS.map((symbol) => ({
        symbol,
        price: priceBySymbol[symbol],
        timestamp,
      }));
      setPrices((previous) => [...previous, ...nextPrices].slice(-4000));

      simulatedModels.forEach((model) => {
        const symbol = SIMULATED_SYMBOLS[Math.floor(Math.random() * SIMULATED_SYMBOLS.length)];
        const price = priceBySymbol[symbol];
        const openPosition = model.open_positions.find((position) => position.symbol === symbol);

        let signal: SignalRecord['signal'] = 'HOLD';
        const confidence = 0.55 + Math.random() * 0.35;
        const momentum = Math.random() - 0.5;

        if (!openPosition && momentum > 0.12 && model.cash > price * 20) {
          signal = 'BUY';
        } else if (openPosition && (momentum < -0.08 || dayStep >= DAY_STEPS - 2)) {
          signal = 'SELL';
        }

        const nextSignal: SignalRecord = {
          id: makeId('signal'),
          symbol,
          signal,
          confidence,
          price,
          timestamp,
          modelId: model.model_id,
          modelName: model.model_name,
          explanation:
            signal === 'BUY'
              ? ['Momentum breakout', 'Risk budget available']
              : signal === 'SELL'
                ? ['Profit/risk take', 'Close before end-of-day']
                : ['No clear edge'],
        };
        setSignals((previous) => [nextSignal, ...previous].slice(0, 400));

        if (signal === 'BUY') {
          const qty = Math.max(1, Math.floor((model.cash * (0.1 + Math.random() * 0.18)) / price));
          model.cash -= qty * price;
          model.open_positions.push({ symbol, qty, entryPrice: price });
          model.trades += 1;

          const buyTrade: TradeRecord = {
            id: makeId('trade'),
            symbol,
            side: 'BUY',
            qty,
            price,
            timestamp,
            status: 'FILLED',
            modelId: model.model_id,
            modelName: model.model_name,
            realizedPnl: 0,
            inferredEntryPrice: null,
            explanation: ['Opened paper position'],
          };
          setTrades((previous) => [buyTrade, ...previous].slice(0, 400));
        }

        if (signal === 'SELL' && openPosition) {
          const realizedPnl = (price - openPosition.entryPrice) * openPosition.qty;
          model.cash += openPosition.qty * price;
          model.realized_pnl += realizedPnl;
          model.trades += 1;
          if (realizedPnl > 0) model.wins += 1;
          model.open_positions = model.open_positions.filter((position) => position !== openPosition);

          const sellTrade: TradeRecord = {
            id: makeId('trade'),
            symbol,
            side: 'SELL',
            qty: openPosition.qty,
            price,
            timestamp,
            status: 'FILLED',
            modelId: model.model_id,
            modelName: model.model_name,
            realizedPnl,
            inferredEntryPrice: openPosition.entryPrice,
            explanation: ['Closed paper position'],
          };
          setTrades((previous) => [sellTrade, ...previous].slice(0, 400));
        }
      });

      if (dayStep >= DAY_STEPS) {
        closeAllPositions(timestamp);
        dayStep = 0;
      }

      setLeaderboardRows(portfolioRows());
      setStatus((previous) => ({
        ...previous,
        executionMode: 'paper',
        lastMarketTick: timestamp,
        lastSignal: timestamp,
        lastTrade: timestamp,
        latencyMs: tickLatency,
      }));
    }, 1200);

    return () => clearInterval(interval);
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
  const defaultSymbol = availableSymbols.includes("SPY") ? "SPY" : (availableSymbols[0] || "SPY");
  const chartSymbol = filters.symbol === "ALL" ? defaultSymbol : filters.symbol;

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
            <h2 className="text-lg font-semibold mb-4 text-white/90">Recent Executions (Max 50)</h2>
            <TradeLog trades={filteredTrades.slice(0, 50)} />
          </div>
        </div>
      </div>
    </main>
  );
}
