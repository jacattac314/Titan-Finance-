"use client";

import { useState } from "react";
import { TradeRecord } from "@/components/dashboard/types";

interface TradeLogProps {
  trades: TradeRecord[];
}

const getModelBadge = (modelId: string) => {
  if (!modelId) return 'bg-zinc-500/20 text-zinc-400 border-zinc-500/30';
  if (modelId.includes('lgb')) return 'bg-blue-500/20 text-blue-400 border-blue-500/30';
  if (modelId.includes('lstm')) return 'bg-purple-500/20 text-purple-400 border-purple-500/30';
  if (modelId.includes('tft')) return 'bg-amber-500/20 text-amber-400 border-amber-500/30';
  if (modelId.includes('sma')) return 'bg-gray-500/20 text-gray-400 border-gray-500/30';
  return 'bg-zinc-500/20 text-zinc-400 border-zinc-500/30';
};

const formatTime = (timestamp: number | string) => {
  const date = new Date(timestamp);
  if (Number.isNaN(date.getTime())) {
    return "--:--:--";
  }
  return date.toISOString().substring(11, 19);
};

export default function TradeLog({ trades }: TradeLogProps) {
  const [selectedExplanation, setSelectedExplanation] = useState<{ id: string, lines: string[], model: string } | null>(null);

  return (
    <div className="relative">
      {/* Explanation Modal */}
      {selectedExplanation && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm" onClick={() => setSelectedExplanation(null)}>
          <div className="bg-zinc-900 border border-white/10 p-6 rounded-xl shadow-2xl max-w-md w-full" onClick={e => e.stopPropagation()}>
            <div className="flex justify-between items-center mb-4">
              <h3 className="text-lg font-bold text-white">Trade Logic</h3>
              <span className={`px-2 py-0.5 rounded text-xs border ${getModelBadge(selectedExplanation.model)}`}>
                {selectedExplanation.model}
              </span>
            </div>
            <div className="space-y-3">
              <p className="text-sm text-zinc-400">Primary factors driving this decision:</p>
              {selectedExplanation.lines && selectedExplanation.lines.length > 0 ? (
                selectedExplanation.lines.map((line, i) => (
                  <div key={i} className="flex items-center justify-between p-3 bg-white/5 rounded-lg border border-white/5">
                    <span className="text-zinc-200 font-mono text-sm">{line}</span>
                  </div>
                ))
              ) : (
                <p className="text-zinc-500 italic">No specific explanation available.</p>
              )}
            </div>
            <button
              className="mt-6 w-full py-2 bg-indigo-600 hover:bg-indigo-500 text-white font-medium rounded transition-colors"
              onClick={() => setSelectedExplanation(null)}
            >
              Close Analysis
            </button>
          </div>
        </div>
      )}

      <div className="overflow-x-auto">
        <table className="w-full text-sm text-left">
          <thead className="text-xs text-muted-foreground uppercase bg-white/5">
            <tr>
              <th className="px-4 py-3 rounded-tl-lg">Time</th>
              <th className="px-4 py-3">Sym</th>
              <th className="px-4 py-3">Side</th>
              <th className="px-4 py-3">Strategy / Model</th>
              <th className="px-4 py-3">Qty</th>
              <th className="px-4 py-3">Price</th>
              <th className="px-4 py-3">PnL</th>
              <th className="px-4 py-3">Insight</th>
              <th className="px-4 py-3 rounded-tr-lg">Status</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-white/5">
            {trades.length === 0 && (
              <tr>
                <td colSpan={9} className="text-center py-8 text-muted-foreground">
                  Waiting for trade signals...
                </td>
              </tr>
            )}
            {trades.map((trade) => (
              <tr key={trade.id} className="hover:bg-white/5 transition-colors group">
                <td className="px-4 py-3 font-mono text-xs text-zinc-400">{formatTime(trade.timestamp)}</td>
                <td className="px-4 py-3 font-semibold text-white">{trade.symbol}</td>
                <td className={`px-4 py-3 font-bold ${trade.side.toUpperCase() === 'BUY' ? 'text-emerald-400' : 'text-rose-400'}`}>
                  {trade.side}
                </td>
                <td className="px-4 py-3">
                  <span className={`px-2 py-1 rounded text-[10px] font-medium border ${getModelBadge(trade.modelId)}`}>
                    {trade.modelName}
                  </span>
                </td>
                <td className="px-4 py-3 text-zinc-300">{trade.qty}</td>
                <td className="px-4 py-3 font-mono text-zinc-300">${Number(trade.price ?? 0) > 0 ? Number(trade.price ?? 0).toFixed(2) : '-'}</td>
                <td className={`px-4 py-3 font-mono ${trade.realizedPnl >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                  {Number(trade.realizedPnl ?? 0) === 0 ? '-' : `${Number(trade.realizedPnl ?? 0) > 0 ? '+' : ''}$${Number(trade.realizedPnl ?? 0).toFixed(2)}`}
                </td>
                <td className="px-4 py-3">
                  {trade.explanation && trade.explanation.length > 0 ? (
                    <button
                      onClick={() => setSelectedExplanation({ id: trade.id, lines: trade.explanation!, model: trade.modelName })}
                      className="flex items-center gap-1 text-xs bg-indigo-500/10 text-indigo-400 border border-indigo-500/20 px-3 py-1.5 rounded hover:bg-indigo-500/20 transition-all font-medium"
                    >
                      <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>
                      Analyze
                    </button>
                  ) : (
                    <span className="text-zinc-600 text-xs">-</span>
                  )}
                </td>
                <td className="px-4 py-3">
                  <span className={`px-2 py-0.5 rounded text-[10px] border ${trade.status === 'FILLED' ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20' : 'bg-yellow-500/10 text-yellow-400 border-yellow-500/20'
                    }`}>
                    {trade.status}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
