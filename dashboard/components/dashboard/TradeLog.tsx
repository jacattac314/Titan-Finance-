
"use client";
import { useEffect, useState } from 'react';
import io from 'socket.io-client';

interface Trade {
    id: string;
    symbol: string;
    side: string;
    qty: number;
    price: number;
    time: string; // Display time
    status: string;
    model: string;
    realizedPnl: number;
}

interface TradeEvent {
    id: string;
    symbol: string;
    side: string;
    qty: number;
    price: number;
    timestamp: string;
    status: string;
    model_name?: string;
    model_id?: string;
    realized_pnl?: number;
}

export default function TradeLog() {
    const [trades, setTrades] = useState<Trade[]>([]);

    useEffect(() => {
        const socket = io({
            path: "/api/socket/io",
            addTrailingSlash: false,
        });

        socket.on("trade_update", (trade: TradeEvent) => {
            console.log("Trade Log received:", trade);
            const newTrade: Trade = {
                id: trade.id,
                symbol: trade.symbol,
                side: trade.side,
                qty: trade.qty,
                price: trade.price,
                time: new Date(trade.timestamp).toLocaleTimeString(),
                status: trade.status,
                model: trade.model_name || trade.model_id || "Unknown",
                realizedPnl: trade.realized_pnl || 0
            };
            setTrades(prev => [newTrade, ...prev].slice(0, 50));
        });

        return () => {
            socket.disconnect();
        };
    }, []);

    return (
        <div className="overflow-x-auto">
            <table className="w-full text-sm text-left">
                <thead className="text-xs text-muted-foreground uppercase bg-white/5">
                    <tr>
                        <th className="px-4 py-3 rounded-tl-lg">Time</th>
                        <th className="px-4 py-3">Sym</th>
                        <th className="px-4 py-3">Side</th>
                        <th className="px-4 py-3">Model</th>
                        <th className="px-4 py-3">Qty</th>
                        <th className="px-4 py-3">Price</th>
                        <th className="px-4 py-3">PnL</th>
                        <th className="px-4 py-3 rounded-tr-lg">Status</th>
                    </tr>
                </thead>
                <tbody className="divide-y divide-white/5">
                    {trades.length === 0 && (
                        <tr>
                            <td colSpan={8} className="text-center py-4 text-muted-foreground">No trades yet</td>
                        </tr>
                    )}
                    {trades.map((trade) => (
                        <tr key={trade.id} className="hover:bg-white/5 transition-colors">
                            <td className="px-4 py-3 font-mono text-xs">{trade.time}</td>
                            <td className="px-4 py-3 font-semibold">{trade.symbol}</td>
                            <td className={`px-4 py-3 font-semibold ${trade.side.toUpperCase() === 'BUY' ? 'text-emerald-400' : 'text-rose-400'}`}>
                                {trade.side}
                            </td>
                            <td className="px-4 py-3 text-xs text-cyan-300">{trade.model}</td>
                            <td className="px-4 py-3">{trade.qty}</td>
                            <td className="px-4 py-3 font-mono">${trade.price > 0 ? trade.price.toFixed(2) : '-'}</td>
                            <td className={`px-4 py-3 font-mono ${trade.realizedPnl >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                                {trade.realizedPnl === 0 ? '-' : `${trade.realizedPnl > 0 ? '+' : ''}$${trade.realizedPnl.toFixed(2)}`}
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
    );
}
