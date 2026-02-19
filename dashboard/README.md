# TitanFlow Dashboard

Real-time trading dashboard built with Next.js 16, Socket.IO, and Tailwind CSS.

---

## Open the dashboard (fastest)

**Requires:** Docker

```bash
# From the repo root — starts the dashboard and a Redis broker
docker compose -f docker-compose.dashboard.yml up --build
```

Then visit **http://localhost:3000**

To share with anyone on the same network, use **http://\<your-ip\>:3000** — the server binds to all interfaces (`0.0.0.0`) by default.

The dashboard starts in **standalone mode** (full UI, no live trading data) and automatically upgrades to live mode once Redis is reachable.

---

## Run locally (no Docker)

**Requires:** Node.js 20+

```bash
cd dashboard
npm install
npm run dev
```

Open **http://localhost:3000**.

To connect to a running Redis instance:

```bash
REDIS_URL=redis://localhost:6379 npm run dev
```

For Windows PowerShell:

```powershell
$env:REDIS_URL="redis://localhost:6379"; npm run dev
```

---

## Run with the full trading stack

```bash
# From the repo root — starts all services (requires Alpaca API keys in .env)
docker compose up --build -d
```

See the [root README](../README.md) for environment variable setup.

---

## Available scripts

| Command | Description |
|---|---|
| `npm run dev` | Start development server (hot reload) |
| `npm run build` | Build for production |
| `npm run start` | Start production server |
| `npm run lint` | ESLint |
| `npm run typecheck` | TypeScript type check |
| `npm run test` | Unit tests (Vitest) |
| `npm run test:e2e` | End-to-end tests (Playwright, headless) |
| `npm run test:e2e:ui` | End-to-end tests with Playwright UI mode |
| `npm run test:e2e:headed` | End-to-end tests in a visible browser |
| `npm run test:e2e:report` | Open last Playwright HTML report |

---

## Environment variables

| Variable | Default | Description |
|---|---|---|
| `PORT` | `3000` | HTTP port the server listens on |
| `HOSTNAME` | `0.0.0.0` | Interface to bind (`127.0.0.1` restricts to localhost only) |
| `REDIS_URL` | `redis://localhost:6379` (dev) / `redis://redis:6379` (prod) | Redis connection string |
| `EXECUTION_MODE` | `paper` | Label shown in the status bar |
| `NODE_ENV` | `development` | `production` enables Next.js optimisations |

---

## Production Build Verification

```bash
npm run lint
npm run typecheck
npm run test
npm run test:e2e
npm run build
```
