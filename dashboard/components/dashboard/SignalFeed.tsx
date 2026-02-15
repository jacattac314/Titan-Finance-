"use client";
import { BrainCircuit } from 'lucide-react';
import { useEffect, useState } from 'react';
import io from 'socket.io-client';

// Keep some mock data for initial load/demo if needed, or start empty
interface Signal {
    id: number;
    symbol: string;
    type: string;
    price: number;
    time: string;
    confidence: string;
    reasoning: string;
    model: string;
}

const initialSignals: Signal[] = [];

interface SignalExplanationItem {
    feature: string;
    impact: number;
}

interface SignalEvent {
    symbol: string;
    signal: string;
    price?: number;
    confidence?: number;
    timestamp?: string | number;
    explanation?: SignalExplanationItem[];
    model_name?: string;
    model_id?: string;
}

function formatSignalTime(timestamp: unknown): string {
    if (typeof timestamp === "string") {
        const parsed = new Date(timestamp);
        if (!Number.isNaN(parsed.getTime())) {
            return parsed.toLocaleTimeString();
        }
    }
    if (typeof timestamp === "number") {
        // Gateway currently emits pseudo-ns timestamps.
        return new Date(timestamp / 1_000_000).toLocaleTimeString();
    }
    return new Date().toLocaleTimeString();
}

export default function SignalFeed() {
    const [signals, setSignals] = useState<Signal[]>(initialSignals);

    useEffect(() => {
        // Connect to Socket.io
        const socket = io({
            path: "/api/socket/io",
            addTrailingSlash: false,
        });

        socket.on("connect", () => {
            console.log("Connected to SignalFeed Socket");
        });

        socket.on("signal", (newSignal: SignalEvent) => {
            console.log("Received signal:", newSignal);
            // newSignal format expected: { symbol, signal, confidence, timestamp, explanation, ... }

            // Transform to UI format if needed
            const reasoning = newSignal.explanation && newSignal.explanation.length > 0
                ? newSignal.explanation
                    .map((e) => {
                        const impact = Number(e.impact || 0);
                        return `${e.feature} (${impact.toFixed(2)})`;
                    })
                    .join(', ')
                : "AI Decision";
            const uiSignal: Signal = {
                id: Date.now(), // Unique ID
                symbol: newSignal.symbol,
                type: newSignal.signal, // BUY/SELL
                price: newSignal.price || 0, // signals might not have price, check paylod
                time: formatSignalTime(newSignal.timestamp),
                confidence: `${((newSignal.confidence || 0) * 100).toFixed(0)}`,
                reasoning,
                model: newSignal.model_name || newSignal.model_id || "Unknown"
            };

            setSignals((prev) => [uiSignal, ...prev].slice(0, 50)); // Keep last 50
        });

        return () => {
            socket.disconnect();
        };
    }, []);

    return (
        <div className="flex-1 overflow-y-auto p-4 space-y-3">
            {signals.length === 0 && (
                <div className="text-center text-muted-foreground text-sm py-10">
                    Waiting for signals...
                </div>
            )}

            {signals.map((signal) => (
                <div key={signal.id} className="p-3 rounded-lg bg-white/5 border border-white/5 hover:bg-white/10 transition-colors group">
                    <div className="flex justify-between items-start mb-2">
                        <div className="flex items-center gap-2">
                            <span className="text-sm font-bold text-white">{signal.symbol}</span>
                            <span className={`text-xs font-bold px-2 py-0.5 rounded-full ${signal.type === 'BUY' ? 'bg-emerald-500/20 text-emerald-400' :
                                signal.type === 'SELL' ? 'bg-rose-500/20 text-rose-400' : 'bg-yellow-500/20 text-yellow-400'
                                }`}>
                                {signal.type}
                            </span>
                        </div>
                        <span className="text-xs text-muted-foreground">{signal.time}</span>
                    </div>

                    <div className="flex items-center justify-between text-xs text-muted-foreground mb-3">
                        <span>@ ${signal.price}</span>
                        <span className="flex items-center gap-1 text-cyan-400">
                            <BrainCircuit className="w-3 h-3" /> {signal.confidence}% Conf
                        </span>
                    </div>

                    <div className="bg-black/20 p-2 rounded text-xs text-zinc-400 leading-relaxed border-l-2 border-primary/50">
                        <div className="mb-1 text-cyan-300">Model: {signal.model}</div>
                        {signal.reasoning}
                    </div>
                </div>
            ))}
        </div>
    );
}
