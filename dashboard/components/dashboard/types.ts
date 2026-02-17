export type SignalSide = "BUY" | "SELL" | "HOLD";
export type TimeRange = "15M" | "1H" | "4H" | "1D";

export interface FilterState {
  symbol: string;
  model: string;
  signalType: "ALL" | "BUY" | "SELL";
  timeRange: TimeRange;
}

export interface ModelOption {
  id: string;
  name: string;
}

export interface SignalRecord {
  id: string;
  symbol: string;
  signal: SignalSide;
  confidence: number;
  price: number;
  timestamp: number;
  modelId: string;
  modelName: string;
  explanation: string[];
}

export interface TradeRecord {
  id: string;
  symbol: string;
  side: "BUY" | "SELL";
  qty: number;
  price: number;
  timestamp: number;
  status: string;
  modelId: string;
  modelName: string;
  realizedPnl: number;
  inferredEntryPrice: number | null;
  explanation: string[];
}

export interface PriceRecord {
  symbol: string;
  price: number;
  timestamp: number;
}

export interface MarkerRecord {
  id: string;
  symbol: string;
  signal: "BUY" | "SELL";
  modelName: string;
  confidence: number;
  price: number;
  timestamp: number;
}

export interface LeaderboardRow {
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
  max_drawdown_pct: number;
}

export interface SystemStatus {
  socketConnected: boolean;
  redisConnected: boolean;
  executionMode: string;
  marketFeedConnected: boolean;
  lastUpdate: number | null;
  latencyMs: number | null;
}
