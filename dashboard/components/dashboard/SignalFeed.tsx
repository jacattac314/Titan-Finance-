"use client";
import { BrainCircuit } from 'lucide-react';
import { SignalRecord } from '@/components/dashboard/types';

interface SignalFeedProps {
    signals: SignalRecord[];
}

function formatSignalTime(timestamp: number): string {
    const date = new Date(timestamp);
    if (Number.isNaN(date.getTime())) {
        return "--:--:--";
    }
    return date.toISOString().substring(11, 19);
}

export default function SignalFeed({ signals }: SignalFeedProps) {
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
                            <span className={`text-xs font-bold px-2 py-0.5 rounded-full ${signal.signal === 'BUY' ? 'bg-emerald-500/20 text-emerald-400' :
                                signal.signal === 'SELL' ? 'bg-rose-500/20 text-rose-400' : 'bg-yellow-500/20 text-yellow-400'
                                }`}>
                                {signal.signal}
                            </span>
                        </div>
                        <span className="text-xs text-muted-foreground">{formatSignalTime(signal.timestamp)}</span>
                    </div>

                    <div className="flex items-center justify-between text-xs text-muted-foreground mb-3">
                        <span>@ ${Number(signal.price ?? 0).toFixed(2)}</span>
                        <span className="flex items-center gap-1 text-cyan-400">
                            <BrainCircuit className="w-3 h-3" /> {(Number(signal.confidence ?? 0) * 100).toFixed(0)}% Conf
                        </span>
                    </div>

                    <div className="bg-black/20 p-2 rounded text-xs text-zinc-400 leading-relaxed border-l-2 border-primary/50">
                        <div className="mb-1 text-cyan-300">Model: {signal.modelName}</div>
                        {signal.explanation.length > 0 ? signal.explanation.join(", ") : "AI Decision"}
                    </div>
                </div>
            ))}
        </div>
    );
}
