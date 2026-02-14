const ranges = {
  "1W": {
    managed: [64, 66, 68, 70, 73, 75, 78],
    benchmark: [63, 64, 65, 66, 68, 69, 70]
  },
  "1M": {
    managed: [52, 54, 56, 58, 61, 64, 62, 66, 69, 72, 74, 79],
    benchmark: [51, 52, 53, 55, 56, 58, 58, 60, 61, 63, 65, 67]
  },
  "1Y": {
    managed: [34, 36, 39, 38, 42, 45, 47, 46, 50, 54, 57, 62],
    benchmark: [34, 35, 36, 36, 38, 40, 41, 42, 44, 45, 47, 49]
  }
};

const baseSnapshot = {
  portfolioValue: 4290000,
  deltaQuarterly: 6.4,
  allocation: [
    { name: "Equities", weight: 42 },
    { name: "Fixed Income", weight: 27 },
    { name: "Private Markets", weight: 16 },
    { name: "Cash", weight: 15 }
  ],
  kpis: [
    {
      label: "Annualized Return",
      value: 12.8,
      suffix: "%",
      note: "Top decile benchmark: 10.2%"
    },
    {
      label: "Sharpe Ratio",
      value: 1.94,
      suffix: "",
      note: "Risk-adjusted quality signal"
    },
    {
      label: "Capital at Risk",
      value: 18.6,
      suffix: "%",
      note: "Contained below policy limit"
    },
    {
      label: "Liquidity Window",
      value: 36,
      suffix: " days",
      note: "Average position exit horizon"
    }
  ],
  opportunities: [
    {
      title: "Energy Infrastructure Credit",
      detail: "Yield spread anomaly",
      progress: 82,
      priority: "High"
    },
    {
      title: "AI Semiconductor Basket",
      detail: "Momentum + valuation reset",
      progress: 61,
      priority: "Monitor"
    },
    {
      title: "Municipal Bond Ladder",
      detail: "Tax-efficient cashflow extension",
      progress: 49,
      priority: "Stable"
    }
  ],
  activities: [
    {
      title: "Rebalanced Growth Sleeve",
      detail: "Shifted 4.2% into lower-volatility technology names",
      when: "2 hours ago"
    },
    {
      title: "Rate Sensitivity Alert",
      detail: "Duration exposure reduced from 5.6 years to 4.1 years",
      when: "Yesterday"
    },
    {
      title: "Private Credit Distribution",
      detail: "$138k coupon distribution posted",
      when: "2 days ago"
    },
    {
      title: "Compliance Checkpoint",
      detail: "All mandates remain inside policy risk boundaries",
      when: "This week"
    }
  ]
};

function wait(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function jitter(number, amplitude) {
  const delta = (Math.random() * 2 - 1) * amplitude;
  return Number((number + delta).toFixed(2));
}

export async function fetchDashboardSnapshot() {
  await wait(280 + Math.floor(Math.random() * 320));

  return {
    ...baseSnapshot,
    portfolioValue: Math.round(baseSnapshot.portfolioValue + (Math.random() * 70000 - 32000)),
    deltaQuarterly: jitter(baseSnapshot.deltaQuarterly, 0.6),
    kpis: baseSnapshot.kpis.map((kpi) => ({
      ...kpi,
      value: kpi.suffix.includes("days") ? Math.max(20, Math.round(jitter(kpi.value, 3))) : jitter(kpi.value, 0.5)
    }))
  };
}

export async function fetchPerformanceSeries(range) {
  await wait(180 + Math.floor(Math.random() * 260));

  const source = ranges[range] ?? ranges["1M"];

  return {
    managed: source.managed.map((point) => jitter(point, 0.7)),
    benchmark: source.benchmark.map((point) => jitter(point, 0.4))
  };
}
