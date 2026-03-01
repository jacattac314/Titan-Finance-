"use client";

import { TrendingUp, Activity, DollarSign, BarChart3 } from 'lucide-react';
import { useMemo } from 'react';
import { cn } from '@/lib/utils';
import { LeaderboardRow } from '@/components/dashboard/types';

interface MetricsGridProps {
    rows: LeaderboardRow[];
}

function safeNumber(value: unknown, fallback = 0): number {
    const num = Number(value);
    return Number.isFinite(num) ? num : fallback;
}

export default function MetricsGrid({ rows }: MetricsGridProps) {
    const metrics = useMemo(() => {
        const models = rows || [];
        const totalPnl = models.reduce((sum, model) => sum + safeNumber(model.pnl), 0);
        const totalTrades = models.reduce((sum, model) => sum + safeNumber(model.trades), 0);
        const avgWinRate = models.length
            ? models.reduce((sum, model) => sum + safeNumber(model.win_rate), 0) / models.length
            : 0;
        const bestModel = models.length ? models[0] : null;
        const bestModelPnlPct = safeNumber(bestModel?.pnl_pct);

        return [
            {
                label: 'Paper PnL',
                value: `${totalPnl >= 0 ? '+' : '-'}$${Math.abs(totalPnl).toFixed(2)}`,
                change: `${models.length} models`,
                icon: DollarSign,
                color: totalPnl >= 0 ? 'text-emerald-400' : 'text-rose-400'
            },
            {
                label: 'Best Model',
                value: bestModel ? bestModel.model_name : 'Waiting',
                change: bestModel ? `${bestModelPnlPct >= 0 ? '+' : ''}${bestModelPnlPct.toFixed(2)}%` : '--',
                icon: Activity,
                color: 'text-blue-400'
            },
            {
                label: 'Avg Win Rate',
                value: `${avgWinRate.toFixed(1)}%`,
                change: `${totalTrades} trades`,
                icon: TrendingUp,
                color: avgWinRate >= 50 ? 'text-emerald-400' : 'text-rose-400'
            },
            {
                label: 'Active Models',
                value: `${models.length}`,
                change: `${models.reduce((sum, model) => sum + safeNumber(model.open_positions), 0)} open positions`,
                icon: BarChart3,
                color: 'text-cyan-400'
            },
        ];
    }, [rows]);

    return (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
            {metrics.map((m) => (
                <div key={m.label} className="glass-card p-5 flex items-center justify-between group cursor-default">
                    <div>
                        <p className="text-sm text-slate-400 font-medium tracking-wide uppercase text-[11px] mb-1">{m.label}</p>
                        <div className="flex items-baseline gap-2 mt-1">
                            <span className="text-3xl font-extrabold tracking-tighter bg-clip-text text-transparent bg-gradient-to-br from-white to-slate-400">{m.value}</span>
                            <span className={cn("text-xs font-semibold px-2 py-0.5 rounded-full bg-black/20 backdrop-blur-sm border border-white/5", m.color)}>
                                {m.change}
                            </span>
                        </div>
                    </div>
                    <div className={cn("p-3.5 rounded-2xl bg-gradient-to-br from-white/10 to-transparent border border-white/10 group-hover:scale-110 group-hover:shadow-[0_0_20px_rgba(255,255,255,0.1)] transition-all duration-300 relative overflow-hidden", m.color)}>
                        <div className="absolute inset-0 bg-gradient-to-tr from-white/5 to-transparent opacity-0 group-hover:opacity-100 transition-opacity"></div>
                        <m.icon className="w-6 h-6 relative z-10 drop-shadow-md group-hover:animate-pulse-subtle" />
                    </div>
                </div>
            ))}
        </div>
    );
}
