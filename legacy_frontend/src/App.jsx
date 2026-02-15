import { useCallback, useEffect, useMemo, useState } from "react";
import { fetchDashboardSnapshot, fetchPerformanceSeries } from "./api/mockApi";
import { brand } from "./branding";

const ranges = ["1W", "1M", "1Y"];

function formatCurrency(value) {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    notation: "compact",
    maximumFractionDigits: 2
  }).format(value);
}

function buildChartPaths(managed, benchmark, width = 860, height = 250) {
  const values = [...managed, ...benchmark];
  const min = Math.min(...values) - 2;
  const max = Math.max(...values) + 2;
  const step = width / Math.max(managed.length - 1, 1);

  const toPoint = (value, index) => {
    const x = index * step;
    const normalized = (value - min) / (max - min || 1);
    const y = height - normalized * (height - 28) - 8;
    return [x, y];
  };

  const toPath = (series) => series
    .map((value, index) => {
      const [x, y] = toPoint(value, index);
      return `${index === 0 ? "M" : "L"}${x.toFixed(1)} ${y.toFixed(1)}`;
    })
    .join(" ");

  const managedPath = toPath(managed);
  const benchmarkPath = toPath(benchmark);
  const areaPath = `${managedPath} L${width} ${height} L0 ${height} Z`;

  return { managedPath, benchmarkPath, areaPath };
}

function priorityClass(priority) {
  if (priority === "High") return "high";
  if (priority === "Monitor") return "monitor";
  return "stable";
}

export default function App() {
  const wordmarkSrc = `${import.meta.env.BASE_URL}titan-wordmark.svg`;
  const [range, setRange] = useState("1M");
  const [snapshot, setSnapshot] = useState(null);
  const [series, setSeries] = useState({ managed: [], benchmark: [] });
  const [loadingSeries, setLoadingSeries] = useState(true);
  const [lastUpdated, setLastUpdated] = useState(null);

  const themeStyle = useMemo(() => ({
    "--bg": brand.palette.background,
    "--text": brand.palette.text,
    "--muted": brand.palette.muted,
    "--panel": brand.palette.panel,
    "--panel-alt": brand.palette.panelAlt,
    "--border": brand.palette.border,
    "--accent": brand.palette.accent,
    "--accent-soft": brand.palette.accentSoft,
    "--signal": brand.palette.signal,
    "--good": brand.palette.good
  }), []);

  const refreshSnapshot = useCallback(async () => {
    const data = await fetchDashboardSnapshot();
    setSnapshot(data);
    setLastUpdated(new Date());
  }, []);

  useEffect(() => {
    let alive = true;

    const loadSeries = async () => {
      setLoadingSeries(true);
      const next = await fetchPerformanceSeries(range);
      if (alive) {
        setSeries(next);
        setLoadingSeries(false);
      }
    };

    loadSeries();

    return () => {
      alive = false;
    };
  }, [range]);

  useEffect(() => {
    refreshSnapshot();
    const interval = setInterval(() => {
      refreshSnapshot();
    }, 20000);

    return () => clearInterval(interval);
  }, [refreshSnapshot]);

  useEffect(() => {
    const observer = new IntersectionObserver((entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          entry.target.classList.add("visible");
          observer.unobserve(entry.target);
        }
      });
    }, { threshold: 0.15 });

    document.querySelectorAll(".reveal").forEach((element) => observer.observe(element));

    return () => observer.disconnect();
  }, []);

  const chart = useMemo(() => {
    if (!series.managed.length) return null;
    return buildChartPaths(series.managed, series.benchmark);
  }, [series]);

  return (
    <div className="app" style={themeStyle}>
      <div className="ambient" aria-hidden="true" />
      <header className="topbar shell reveal">
        <div className="brand">
          <img src={wordmarkSrc} alt="Titan Finance" className="wordmark" />
          <div>
            <p className="eyebrow">{brand.company}</p>
            <h1>{brand.product}</h1>
          </div>
        </div>
        <nav>
          <a href="#dashboard">Dashboard</a>
          <a href="#signals">Signals</a>
          <a href="#activity">Activity</a>
          <button type="button" className="ghost" onClick={refreshSnapshot}>Refresh Data</button>
        </nav>
      </header>

      <main className="shell" id="dashboard">
        <section className="hero reveal">
          <div>
            <p className="eyebrow">{brand.slogan}</p>
            <h2>Institutional-grade portfolio intelligence for decisions that cannot wait.</h2>
            <p>
              A modern demo frontend with motion, responsive design, and mock API powered updates.
              Use this to showcase product vision to investors, executives, or potential clients.
            </p>
            <div className="hero-actions">
              <button type="button">Launch Live View</button>
              <button type="button" className="ghost">Schedule Briefing</button>
            </div>
            <small className="last-updated">
              Last refresh: {lastUpdated ? lastUpdated.toLocaleTimeString("en-US") : "syncing..."}
            </small>
          </div>

          <aside className="value-card">
            <p>Total Portfolio Value</p>
            <h3>{snapshot ? formatCurrency(snapshot.portfolioValue) : "Loading..."}</h3>
            <span className="trend">{snapshot ? `+${snapshot.deltaQuarterly}% vs prior quarter` : ""}</span>
            <div className="allocation">
              {snapshot?.allocation.map((slice) => (
                <div key={slice.name} className="alloc-item">
                  <span>{slice.name}</span>
                  <div className="alloc-track">
                    <i style={{ width: `${slice.weight}%` }} />
                  </div>
                  <strong>{slice.weight}%</strong>
                </div>
              ))}
            </div>
          </aside>
        </section>

        <section className="kpi-grid reveal">
          {snapshot?.kpis.map((kpi) => (
            <article className="kpi" key={kpi.label}>
              <p>{kpi.label}</p>
              <h3>{kpi.value}{kpi.suffix}</h3>
              <small>{kpi.note}</small>
            </article>
          ))}
          {!snapshot && Array.from({ length: 4 }).map((_, index) => (
            <article className="kpi loading" key={index}>
              <p>Loading</p>
              <h3>--</h3>
              <small>Fetching metrics</small>
            </article>
          ))}
        </section>

        <section className="panel reveal" id="signals">
          <div className="panel-head">
            <h3>Performance Signal Engine</h3>
            <div className="switches" role="tablist" aria-label="Performance range">
              {ranges.map((item) => (
                <button
                  key={item}
                  type="button"
                  className={`range ${item === range ? "active" : ""}`}
                  onClick={() => setRange(item)}
                >
                  {item}
                </button>
              ))}
            </div>
          </div>

          <div className="chart-wrap" aria-busy={loadingSeries}>
            {chart && (
              <svg viewBox="0 0 860 250" preserveAspectRatio="none" aria-label="Portfolio performance chart">
                <defs>
                  <linearGradient id="managedLine" x1="0" y1="0" x2="1" y2="0">
                    <stop offset="0%" stopColor="var(--accent)" />
                    <stop offset="100%" stopColor="var(--signal)" />
                  </linearGradient>
                  <linearGradient id="managedFill" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="var(--accent)" stopOpacity="0.32" />
                    <stop offset="100%" stopColor="var(--accent)" stopOpacity="0.04" />
                  </linearGradient>
                </defs>
                <path d={chart.areaPath} fill="url(#managedFill)" />
                <path d={chart.benchmarkPath} fill="none" stroke="#93a4bc" strokeWidth="2.6" strokeDasharray="7 8" />
                <path d={chart.managedPath} fill="none" stroke="url(#managedLine)" strokeWidth="4" strokeLinecap="round" />
              </svg>
            )}
          </div>

          <div className="legend">
            <span><i className="dot managed" /> Managed Portfolio</span>
            <span><i className="dot benchmark" /> Market Baseline</span>
          </div>
        </section>

        <section className="grid reveal" id="activity">
          <article className="panel">
            <h3>Opportunity Queue</h3>
            {snapshot?.opportunities.map((opportunity) => (
              <div key={opportunity.title} className="opportunity">
                <div className="opportunity-head">
                  <strong>{opportunity.title}</strong>
                  <span className={`tag ${priorityClass(opportunity.priority)}`}>{opportunity.priority}</span>
                </div>
                <small>{opportunity.detail}</small>
                <div className="meter">
                  <span style={{ width: `${opportunity.progress}%` }} />
                </div>
              </div>
            ))}
          </article>

          <article className="panel">
            <h3>Recent Activity</h3>
            <ul className="activity-list">
              {snapshot?.activities.map((event) => (
                <li key={event.title}>
                  <strong>{event.title}</strong>
                  <span>{event.detail}</span>
                  <small>{event.when}</small>
                </li>
              ))}
            </ul>
          </article>
        </section>
      </main>
    </div>
  );
}
