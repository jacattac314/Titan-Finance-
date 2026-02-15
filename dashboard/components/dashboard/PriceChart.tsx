"use client";

import { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from 'recharts';
import { useEffect, useState, useRef } from 'react';
import io from 'socket.io-client';

interface PricePoint {
    time: string;
    value: number;
}

interface MarketTick {
    symbol: string;
    price: number;
    timestamp: number | string;
}

function buildInitialData(): PricePoint[] {
    return Array.from({ length: 50 }, (_, i) => ({
        time: new Date(Date.now() - (50 - i) * 1000).toLocaleTimeString(),
        value: 450 + Math.random() * 2
    }));
}

function formatTickTime(timestamp: number | string): string {
    if (typeof timestamp === "string") {
        const parsed = new Date(timestamp);
        if (!Number.isNaN(parsed.getTime())) {
            return parsed.toLocaleTimeString();
        }
    }
    return new Date(Number(timestamp) / 1_000_000).toLocaleTimeString();
}

export default function PriceChart() {
    const [data, setData] = useState<PricePoint[]>(() => buildInitialData());
    const socketRef = useRef<ReturnType<typeof io> | null>(null);

    useEffect(() => {
        const socket = io({
            path: "/api/socket/io",
            addTrailingSlash: false,
        });
        socketRef.current = socket;

        socket.on("connect", () => {
            console.log("PriceChart connected to socket");
        });

        socket.on("price_update", (tick: MarketTick) => {
            // tick format: { symbol, price, size, timestamp }
            if (tick.symbol === "SPY") { // Filter for main symbol for now
                setData(prev => {
                    const newData = [...prev, {
                        time: formatTickTime(tick.timestamp),
                        value: tick.price
                    }];
                    return newData.slice(-100); // Keep last 100 points
                });
            }
        });

        return () => {
            if (socketRef.current) socketRef.current.disconnect();
        };
    }, []);

    return (
        <ResponsiveContainer width="100%" height="100%" minWidth={0} minHeight={300}>
            <AreaChart data={data}>
                <defs>
                    <linearGradient id="colorValue" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor="#3b82f6" stopOpacity={0.3} />
                        <stop offset="95%" stopColor="#3b82f6" stopOpacity={0} />
                    </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" opacity={0.1} vertical={false} />
                <XAxis dataKey="time" hide />
                <YAxis
                    domain={['auto', 'auto']}
                    orientation="right"
                    tick={{ fontSize: 12, fill: '#64748b' }}
                    axisLine={false}
                    tickLine={false}
                    width={50}
                />
                <Tooltip
                    contentStyle={{ backgroundColor: '#0f172a', border: '1px solid #1e293b', borderRadius: '8px' }}
                    itemStyle={{ color: '#fff' }}
                />
                <Area
                    type="monotone"
                    dataKey="value"
                    stroke="#3b82f6"
                    strokeWidth={2}
                    fillOpacity={1}
                    fill="url(#colorValue)"
                    isAnimationActive={false} // Disable animation for smoother high-freq updates
                />
            </AreaChart>
        </ResponsiveContainer>
    );
}
