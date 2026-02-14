import { ShieldAlert, Cpu } from 'lucide-react';

export default function Header() {
    return (
        <header className="h-16 border-b border-white/10 bg-background/80 backdrop-blur-md px-6 flex items-center justify-between sticky top-0 z-50">
            <div className="flex items-center gap-3">
                <div className="w-8 h-8 rounded-lg bg-gradient-to-tr from-blue-600 to-cyan-400 flex items-center justify-center shadow-lg shadow-blue-500/20">
                    <Cpu className="w-5 h-5 text-white" />
                </div>
                <h1 className="text-xl font-bold tracking-tight bg-clip-text text-transparent bg-gradient-to-r from-white to-white/70">
                    TitanFlow <span className="text-xs font-mono text-emerald-400 align-top ml-1">LIVE</span>
                </h1>
            </div>

            <div className="flex items-center gap-6">
                <div className="flex items-center gap-2 text-sm text-muted-foreground bg-secondary/30 px-3 py-1.5 rounded-full border border-white/5">
                    <span className="w-2 h-2 rounded-full bg-emerald-500"></span>
                    Gateway: Connected
                </div>

                <button className="flex items-center gap-2 px-4 py-2 bg-destructive/10 hover:bg-destructive/20 text-destructive border border-destructive/20 rounded-lg transition-all text-sm font-semibold group">
                    <ShieldAlert className="w-4 h-4 group-hover:rotate-12 transition-transform" />
                    KILL SWITCH
                </button>
            </div>
        </header>
    );
}
