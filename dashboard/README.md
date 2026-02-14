# TitanFlow Dashboard

Next.js dashboard for monitoring trade signals, execution activity, and system health.

## Scripts

- `npm run dev`: Start the dashboard with custom Socket.IO server (`server.js`).
- `npm run build`: Create a production build.
- `npm run start`: Start production server from `server.js`.
- `npm run lint`: Run ESLint.
- `npm run typecheck`: Run TypeScript checks.
- `npm run test`: Run Vitest tests.

## Local Setup

1. Install dependencies.

```bash
npm install
```

2. Ensure Redis is reachable (default from `server.js`):

```text
REDIS_URL=redis://redis:6379
```

For local host Redis on Windows PowerShell:

```powershell
$env:REDIS_URL="redis://localhost:6379"
```

3. Start development server.

```bash
npm run dev
```

The dashboard runs on `http://localhost:3000` by default.

## Production Build Verification

```bash
npm run lint
npm run typecheck
npm run test
npm run build
```
