"use client";

import { Cpu, ShieldAlert } from "lucide-react";
import { SystemStatus } from "@/components/dashboard/types";
import { cn } from "@/lib/utils";

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
    <header className="border-b border-white/5 bg-slate-950/60 backdrop-blur-xl px-6 py-3 sticky top-0 z-50 space-y-3 relative before:absolute before:inset-x-0 before:bottom-0 before:h-[1px] before:bg-gradient-to-r before:from-transparent before:via-white/20 before:to-transparent">
      <div className="flex flex-wrap items-center justify-between gap-4 relative z-10">
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

      <div className="flex flex-wrap gap-2 text-[11px] font-medium tracking-wide uppercase relative z-10">
        <div className="flex items-center gap-2 bg-slate-900/50 px-3 py-1.5 rounded-full border border-white/10 shadow-[inset_0_1px_1px_rgba(255,255,255,0.05)] text-slate-300">
          <span className={`relative flex h-2 w-2`}>
            {status.marketFeedConnected && <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>}
            <span className={`relative inline-flex rounded-full h-2 w-2 ${dotClass(status.marketFeedConnected)}`}></span>
          </span>
          Market Feed
        </div>
        <div className="flex items-center gap-2 bg-slate-900/50 px-3 py-1.5 rounded-full border border-white/10 shadow-[inset_0_1px_1px_rgba(255,255,255,0.05)] text-slate-300">
          <span className={`relative flex h-2 w-2`}>
            {status.redisConnected && <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>}
            <span className={`relative inline-flex rounded-full h-2 w-2 ${dotClass(status.redisConnected)}`}></span>
          </span>
          Redis
        </div>
        <div className="bg-slate-900/50 px-3 py-1.5 rounded-full border border-white/10 shadow-[inset_0_1px_1px_rgba(255,255,255,0.05)] text-slate-400">
          Mode: <span className="text-cyan-400 font-bold ml-1">{status.executionMode}</span>
        </div>
        <div className="bg-slate-900/50 px-3 py-1.5 rounded-full border border-white/10 shadow-[inset_0_1px_1px_rgba(255,255,255,0.05)] text-slate-400">
          Sync: <span className="text-white ml-1">{formatLastUpdate(status.lastUpdate)}</span>
        </div>
        <div className="bg-slate-900/50 px-3 py-1.5 rounded-full border border-white/10 shadow-[inset_0_1px_1px_rgba(255,255,255,0.05)] text-slate-400">
          Ping: <span className="text-white ml-1">{status.latencyMs !== null ? `${status.latencyMs} ms` : "--"}</span>
        </div>
        <div className="bg-slate-900/50 px-3 py-1.5 rounded-full border border-white/10 shadow-[inset_0_1px_1px_rgba(255,255,255,0.05)] text-slate-400">
          Socket: <span className={cn("ml-1 font-bold", status.socketConnected ? "text-emerald-400 drop-shadow-[0_0_8px_rgba(52,211,153,0.5)]" : "text-rose-400")}>{status.socketConnected ? "Stable" : "Lost"}</span>
        </div>
      </div>
    </header>
  );
}
