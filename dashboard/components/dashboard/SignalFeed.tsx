import { BrainCircuit } from 'lucide-react';
import { useEffect, useState } from 'react';
import io from 'socket.io-client';

// Keep some mock data for initial load/demo if needed, or start empty
const initialSignals = [];

export default function SignalFeed() {
    const [signals, setSignals] = useState(initialSignals);
    const [mounted, setMounted] = useState(false);

    useEffect(() => {
        setMounted(true);

        // Connect to Socket.io
        const socket = io({
            path: "/api/socket/io",
            addTrailingSlash: false,
        });

        socket.on("connect", () => {
            console.log("Connected to SignalFeed Socket");
        });

        socket.on("signal", (newSignal) => {
            console.log("Received signal:", newSignal);
            // newSignal format expected: { symbol, signal, confidence, timestamp, explanation, ... }

            // Transform to UI format if needed
            const uiSignal = {
                id: Date.now(), // Unique ID
                symbol: newSignal.symbol,
                type: newSignal.signal, // BUY/SELL
                price: newSignal.price || 0, // signals might not have price, check paylod
                time: new Date(newSignal.timestamp / 1000000).toLocaleTimeString(), // TS is ns potentially? Check DB.
                confidence: (newSignal.confidence * 100).toFixed(0),
                reasoning: newSignal.explanation ?
                    newSignal.explanation.map(e => `${e.feature} (${e.impact.toFixed(2)})`).join(', ')
                    : "AI Decision"
            };

            setSignals((prev) => [uiSignal, ...prev].slice(0, 50)); // Keep last 50
        });

        return () => {
            socket.disconnect();
        };
    }, []);

    if (!mounted) return null;

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
                        {signal.reasoning}
                    </div>
                </div>
            ))}
        </div>
    );
}
