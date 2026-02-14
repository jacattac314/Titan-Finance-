
import MetricsGrid from '@/components/dashboard/MetricsGrid';
import SignalFeed from '@/components/dashboard/SignalFeed';
import PriceChart from '@/components/dashboard/PriceChart';
import TradeLog from '@/components/dashboard/TradeLog';
import Header from '@/components/dashboard/Header';

export default function Home() {
  return (
    <main className="min-h-screen bg-background text-foreground flex flex-col">
      <Header />

      <div className="flex-1 p-6 grid grid-cols-12 gap-6 max-w-[1920px] mx-auto w-full">
        {/* Left Column: Metrics & Chart (8 cols) */}
        <div className="col-span-12 lg:col-span-8 flex flex-col gap-6">
          <MetricsGrid />
          <div className="glass-card flex-1 p-6 min-h-[500px] flex flex-col">
            <div className="flex justify-between items-center mb-4">
              <h2 className="text-xl font-semibold tracking-tight text-white/90">Market Overview</h2>
              <div className="flex gap-2">
                {['1H', '4H', '1D'].map(tf => (
                  <button key={tf} className="px-3 py-1 text-xs rounded-md bg-white/5 hover:bg-white/10 transition">
                    {tf}
                  </button>
                ))}
              </div>
            </div>
            <div className="flex-1 w-full h-full min-h-[400px]">
              <PriceChart />
            </div>
          </div>
        </div>

        {/* Right Column: AI Feed & Logs (4 cols) */}
        <div className="col-span-12 lg:col-span-4 flex flex-col gap-6">
          <div className="glass-card flex-1 p-0 flex flex-col max-h-[600px] overflow-hidden">
            <div className="p-4 border-b border-white/5 bg-white/5 backdrop-blur-sm">
              <h2 className="text-lg font-semibold flex items-center gap-2">
                <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse"></span>
                AI Signal Feed
              </h2>
            </div>
            <SignalFeed />
          </div>

          <div className="glass-card flex-1 p-4 min-h-[300px]">
            <h2 className="text-lg font-semibold mb-4">Recent Executions</h2>
            <TradeLog />
          </div>
        </div>
      </div>
    </main>
  );
}
