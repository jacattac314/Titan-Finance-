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
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
            {metrics.map((m) => (
                <div key={m.label} className="glass-card p-4 flex items-center justify-between group">
                    <div>
                        <p className="text-sm text-muted-foreground font-medium">{m.label}</p>
                        <div className="flex items-baseline gap-2 mt-1">
                            <span className="text-2xl font-bold text-white tracking-tight">{m.value}</span>
                            <span className={cn("text-xs font-semibold", m.color)}>
                                {m.change}
                            </span>
                        </div>
                    </div>
                    <div className={cn("p-3 rounded-xl bg-white/5 border border-white/5 group-hover:scale-110 transition-transform duration-300", m.color)}>
                        <m.icon className="w-5 h-5" />
                    </div>
                </div>
            ))}
        </div>
    );
}
