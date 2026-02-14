## Titan Frontend Demo

### Run
1. `npm install`
2. `npm run dev`
3. Open the local Vite URL shown in terminal.

### What Was Added
- React + Vite app scaffold at repo root.
- Branded finance dashboard in `src/App.jsx` and `src/styles.css`.
- Mock API service in `src/api/mockApi.js` with async delays and data jitter for live-feel demos.

### Branding Controls
- Edit `src/branding.js`:
  - `company`, `product`, `slogan`
  - `palette` colors (`accent`, `signal`, `panel`, etc.)
- Replace logo at `public/titan-wordmark.svg`.

### Mock API Controls
- Update base KPIs, opportunities, and activities in `src/api/mockApi.js`.
- Adjust timing/latency by editing `wait(...)` calls.
- Adjust refresh cadence in `src/App.jsx` (`setInterval`, currently every 20s).
