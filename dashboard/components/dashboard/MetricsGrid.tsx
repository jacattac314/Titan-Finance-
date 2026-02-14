import { TrendingUp, Activity, DollarSign, BarChart3 } from 'lucide-react';
import { cn } from '@/lib/utils';

const metrics = [
    { label: 'Total PnL', value: '+$1,240.50', change: '+2.4%', icon: DollarSign, color: 'text-emerald-400' },
    { label: 'Sharpe Ratio', value: '2.84', change: '+0.1', icon: Activity, color: 'text-blue-400' },
    { label: 'Max Drawdown', value: '-0.8%', change: 'Stable', icon: TrendingUp, color: 'text-rose-400' },
    { label: 'Win Rate', value: '68%', change: '34 Trades', icon: BarChart3, color: 'text-violet-400' },
];

export default function MetricsGrid() {
    return (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
            {metrics.map((m) => (
                <div key={m.label} className="glass-card p-4 flex items-center justify-between group">
                    <div>
                        <p className="text-sm text-muted-foreground font-medium">{m.label}</p>
                        <div className="flex items-baseline gap-2 mt-1">
                            <span className="text-2xl font-bold text-white tracking-tight">{m.value}</span>
                            <span className={cn("text-xs font-semibold", m.color.includes('rose') ? 'text-rose-400' : 'text-emerald-400')}>
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
