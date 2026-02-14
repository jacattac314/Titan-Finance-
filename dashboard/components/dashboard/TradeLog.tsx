
const trades = [
    { id: 'T-1023', symbol: 'NVDA', side: 'BUY', qty: 10, price: 724.50, time: '10:42:01', status: 'FILLED' },
    { id: 'T-1022', symbol: 'AMD', side: 'SELL', qty: 50, price: 178.10, time: '10:15:22', status: 'FILLED' },
    { id: 'T-1021', symbol: 'MSFT', side: 'BUY', qty: 25, price: 405.30, time: '09:55:10', status: 'FILLED' },
    { id: 'T-1020', symbol: 'TSLA', side: 'BUY', qty: 15, price: 195.40, time: '09:48:05', status: 'FILLED' },
];

export default function TradeLog() {
    return (
        <div className="overflow-x-auto">
            <table className="w-full text-sm text-left">
                <thead className="text-xs text-muted-foreground uppercase bg-white/5">
                    <tr>
                        <th className="px-4 py-3 rounded-tl-lg">Time</th>
                        <th className="px-4 py-3">Sym</th>
                        <th className="px-4 py-3">Side</th>
                        <th className="px-4 py-3">Qty</th>
                        <th className="px-4 py-3">Price</th>
                        <th className="px-4 py-3 rounded-tr-lg">Status</th>
                    </tr>
                </thead>
                <tbody className="divide-y divide-white/5">
                    {trades.map((trade) => (
                        <tr key={trade.id} className="hover:bg-white/5 transition-colors">
                            <td className="px-4 py-3 font-mono text-xs">{trade.time}</td>
                            <td className="px-4 py-3 font-semibold">{trade.symbol}</td>
                            <td className={`px-4 py-3 font-semibold ${trade.side === 'BUY' ? 'text-emerald-400' : 'text-rose-400'}`}>
                                {trade.side}
                            </td>
                            <td className="px-4 py-3">{trade.qty}</td>
                            <td className="px-4 py-3 font-mono">${trade.price}</td>
                            <td className="px-4 py-3">
                                <span className="px-2 py-0.5 rounded text-[10px] bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
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
