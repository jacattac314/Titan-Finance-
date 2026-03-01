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
                <div key={signal.id} className="p-3.5 rounded-xl bg-white/5 border border-white/5 shadow-sm hover:shadow-[0_4px_20px_rgba(0,0,0,0.2)] hover:bg-white/10 transition-all duration-300 group hover:-translate-y-0.5 relative overflow-hidden">
                    <div className="absolute top-0 left-0 w-1 h-full bg-gradient-to-b opacity-50 group-hover:opacity-100 transition-opacity
                        from-transparent via-cyan-500 to-transparent"></div>
                    <div className="flex justify-between items-start mb-2 pl-2">
                        <div className="flex items-center gap-2">
                            <span className="text-sm font-extrabold text-white tracking-wide">{signal.symbol}</span>
                            <span className={`text-[10px] font-bold px-2.5 py-0.5 rounded-full uppercase tracking-wider ${signal.signal === 'BUY' ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/20 shadow-[0_0_10px_rgba(16,185,129,0.2)]' :
                                signal.signal === 'SELL' ? 'bg-rose-500/20 text-rose-400 border border-rose-500/20 shadow-[0_0_10px_rgba(244,63,94,0.2)]' : 'bg-yellow-500/20 text-yellow-400 border border-yellow-500/20'
                                }`}>
                                {signal.signal}
                            </span>
                        </div>
                        <span className="text-[10px] uppercase tracking-wider text-slate-500 font-medium">{formatSignalTime(signal.timestamp)}</span>
                    </div>

                    <div className="flex items-center justify-between text-xs text-slate-400 mb-3 pl-2">
                        <span className="font-mono bg-white/5 px-2 py-0.5 rounded text-slate-300">@ ${Number(signal.price ?? 0).toFixed(2)}</span>
                        <span className="flex items-center gap-1 text-cyan-400 font-semibold bg-cyan-950/40 px-2 py-0.5 rounded-full border border-cyan-500/20">
                            <BrainCircuit className="w-3 h-3 group-hover:animate-pulse" /> {(Number(signal.confidence ?? 0) * 100).toFixed(0)}% Conf
                        </span>
                    </div>

                    <div className="bg-black/30 p-2.5 rounded-lg text-xs tracking-wide text-slate-400 leading-relaxed border-l-2 border-cyan-500/50 shadow-inner">
                        <div className="mb-1 text-cyan-300 font-semibold flex items-center gap-1">
                            <span className="w-1.5 h-1.5 rounded-full bg-cyan-400 animate-pulse"></span>
                            {signal.modelName}
                        </div>
                        <span className="text-slate-300">{signal.explanation.length > 0 ? signal.explanation.join(", ") : "AI Decision"}</span>
                    </div>
                </div>
            ))}
        </div>
    );
}
