"use client";

import { Cpu, ShieldAlert } from "lucide-react";
import { SystemStatus } from "@/components/dashboard/types";

interface HeaderProps {
  status: SystemStatus;
}

function dotClass(connected: boolean): string {
  return connected ? "bg-emerald-400" : "bg-rose-400";
}

function formatLastUpdate(value: number | null): string {
  if (!value) {
    return "No data";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "No data";
  }
  return date.toISOString().substring(11, 19);
}

export default function Header({ status }: HeaderProps) {
  return (
    <header className="border-b border-white/10 bg-background/80 backdrop-blur-md px-6 py-3 sticky top-0 z-50 space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-gradient-to-tr from-blue-600 to-cyan-400 flex items-center justify-center shadow-lg shadow-blue-500/20">
            <Cpu className="w-5 h-5 text-white" />
          </div>
          <h1 className="text-xl font-bold tracking-tight bg-clip-text text-transparent bg-gradient-to-r from-white to-white/70">
            TitanFlow <span className="text-xs font-mono text-cyan-300 align-top ml-1">PAPER MODE</span>
          </h1>
        </div>

        <button className="flex items-center gap-2 px-4 py-2 bg-destructive/10 hover:bg-destructive/20 text-destructive border border-destructive/20 rounded-lg transition-all text-sm font-semibold group">
          <ShieldAlert className="w-4 h-4 group-hover:rotate-12 transition-transform" />
          KILL SWITCH
        </button>
      </div>

      <div className="flex flex-wrap gap-2 text-xs">
        <div className="flex items-center gap-2 bg-secondary/30 px-3 py-1.5 rounded-full border border-white/5">
          <span className={`w-2 h-2 rounded-full ${dotClass(status.marketFeedConnected)}`} />
          Market Feed
        </div>
        <div className="flex items-center gap-2 bg-secondary/30 px-3 py-1.5 rounded-full border border-white/5">
          <span className={`w-2 h-2 rounded-full ${dotClass(status.redisConnected)}`} />
          Redis
        </div>
        <div className="bg-secondary/30 px-3 py-1.5 rounded-full border border-white/5 text-muted-foreground">
          Mode: <span className="text-cyan-300 font-semibold uppercase">{status.executionMode}</span>
        </div>
        <div className="bg-secondary/30 px-3 py-1.5 rounded-full border border-white/5 text-muted-foreground">
          Last Update: <span className="text-white">{formatLastUpdate(status.lastUpdate)}</span>
        </div>
        <div className="bg-secondary/30 px-3 py-1.5 rounded-full border border-white/5 text-muted-foreground">
          Latency: <span className="text-white">{status.latencyMs !== null ? `${status.latencyMs} ms` : "--"}</span>
        </div>
        <div className="bg-secondary/30 px-3 py-1.5 rounded-full border border-white/5 text-muted-foreground">
          Socket: <span className={status.socketConnected ? "text-emerald-400" : "text-rose-400"}>{status.socketConnected ? "Connected" : "Disconnected"}</span>
        </div>
      </div>
    </header>
  );
}
