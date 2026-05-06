# Experiment Report — Online PnL Web Dashboard

**Date:** 2026-05-06
**Working dir:** `crypto-up-or-down/5min markets/online_pnl_web/`

## 1. User Request

User wants to upload the existing `signal_dashboard/online_pnl/` project to GitHub
as a **dynamically refreshing webpage** so they can monitor account PnL in
near-real-time. Specific requirements:

1. Place the new project in a **new folder** under `5min markets/`, NOT mixed
   with the existing `online_pnl/` directory. Treat it as a fresh copy.
2. Replace static matplotlib PNG charts with **interactive web-native charts**
   (rendered client-side, with hover, animations, tooltips).
3. Redesign the entire page with a **highly tech / premium / monitoring-station
   aesthetic** with rich animations. Activate the frontend-design skill.
4. Extract `MAKER_REBATE` rows from the activity cache and surface them as a
   dedicated **daily rebate bar chart**, separate from the trading PnL.

## 2. Planned Approach

### Architecture
- Static-site only — hostable on GitHub Pages with zero backend.
- Python script (`calc_pnl.py`) pulls Polymarket `/activity` API, computes
  derived series, and writes a single `data.json` consumed by the browser.
- `index.html` loads ECharts from CDN, fetches `./data.json` on load, re-fetches
  every 60s for live updates without full-page reloads.
- GitHub Actions cron runs the Python script every ~10 min and commits the
  refreshed `data.json` + `activity_cache.json` back to the repo.

### Data layer changes vs. original `online_pnl/calc_pnl.py`
- **Rebate handling fix**: original code reads `usdcSize` for `MAKER_REBATE`,
  but inspection showed those rows have no `usdcSize` field — only `size`.
  New code falls back to `size` when `usdcSize` is absent on rebate types.
- **Daily rebate series**: new aggregation grouping rebate cash flow by UTC
  calendar day, emitted as `data.daily_rebates: [{date, usdc}, ...]`.
- **Output format**: pure JSON instead of base64-embedded PNGs. Schema:
  - `meta` — generated_at, wallet, window
  - `kpi` — total_pnl, n_markets, win_rate, rot, running_days, total_rebates
  - `cumulative_pnl` — `[{t: epoch_ms, v: cum_usdc}, ...]`
  - `regime` — `[{bin, avg_pnl, n_markets}, ...]`
  - `daily_rebates` — `[{date, usdc}, ...]`
  - `extremes` — best/worst markets
  - `recent` — last 12 markets

### Frontend design direction
- **Aesthetic**: institutional dark-mode "mission control" — Bloomberg-terminal
  density meets modern HUD/dashboard refinement.
- **Typography**: `Chakra Petch` (geometric, technical) for display headers +
  `JetBrains Mono` for all numerics and tabular data. Avoids generic
  Inter/Roboto/Arial.
- **Color**: deep near-black background `#0a0e14`, cool panel surfaces with
  subtle 1px borders, mint accent for positive, coral for negative, amber for
  rebates, blue for neutral chart lines.
- **Motion**: staggered card reveal on load (cascade fade-up), animated
  count-up on KPI numbers, ECharts native chart-grow animation, slow scrolling
  background grid, pulsing live-status dot, on-tick chart re-render with
  smooth interpolation.
- **Decorative**: HUD corner brackets on chart panels, subtle scanline overlay,
  faint geometric grid in the background, animated sweep line over charts.
- **Charts**: ECharts (Apache) — best dark-theme support and animation engine.

### CI / Deployment
- `.github/workflows/refresh.yml` — cron `*/10 * * * *`, also `workflow_dispatch`.
  Steps: checkout → setup Python → pip install → run `python calc_pnl.py` →
  commit + push if `data.json` changed.
- `requirements.txt` — `pandas`, `requests`, `numpy`. (No matplotlib needed.)
- `README.md` — setup instructions, GitHub Pages activation steps.
- Pages serves `/index.html` from main branch. User adds wallet address as
  a repo variable if they want to swap address without touching code.

## 3. Results & Observations

### Built
- New folder `online_pnl_web/` created at `5min markets/online_pnl_web/`,
  separate from the existing `signal_dashboard/online_pnl/` project.
- `activity_cache.json` copied over (520 → 521 records on first incremental
  pull). `data.json` regenerated from cache.
- New `calc_pnl.py` writes only `data.json`; no PNGs, no embedded HTML, no
  matplotlib import.
- New `index.html` is a single static page (~37 KB) loading ECharts from CDN
  and fetching `./data.json` client-side. Re-fetches every 60s without
  reload.
- `.github/workflows/refresh.yml` runs `python calc_pnl.py` on a 10-min cron,
  commits regenerated artifacts.
- Documentation: `README.md` (deployment guide), this report, `.gitignore`,
  `requirements.txt`, `docs/preview.png` (rendered screenshot).

### Data layer correctness
- Running `python calc_pnl.py` produces:
  - `total_pnl = +$112.14`
  - `n_markets = 215`, `win_rate = 78.6%`
  - `total_rebates = $2.0149` (one MAKER_REBATE row dated 2026-05-06)
- **Rebate fix verified**: original `online_pnl/calc_pnl.py` would have
  reported $0 in rebates because the row has no `usdcSize` field, only
  `size`. New code falls back to `size` for rebate types and now correctly
  picks up the $2.01 payout.
- Cumulative PnL series has 618 5-min bins from 2026-05-04 onward, terminal
  value matches per-market sum.
- Daily rebate aggregation produces a dense series (currently length-1, will
  grow as the wallet earns more rebates over calendar days).

### Frontend verification
- Headless Chrome screenshot confirms: brand mark with HUD corner brackets,
  staggered card reveal animation (caught mid-flight in early capture, fully
  resolved at 8s budget), animated KPI count-up, mint cumulative PnL line
  chart with gradient area fill, amber daily rebate bar chart with elastic-out
  entry animation, blue regime entry-count bars, mint/coral regime avg-PnL
  bars, recent-markets table with up/down outcome tags, best/worst extreme
  cards with glow.
- Sign-formatting bug found and fixed: dollar amounts now render as
  `+$112.14` / `-$9.25` (sign outside the `$`) rather than `$+112.14` /
  `$-9.25`. Affects KPI tiles, extremes panel, and chart tooltips.
- Auto-refresh: page loads `./data.json?t=<timestamp>` to bust HTTP cache
  every 60s, in-place re-renders all charts via ECharts `setOption`.
- Live status pulse, animated grid drift, ambient radial glows, scanlines all
  render as designed.

### Known limitations
- GitHub Actions cron has 5–15 min real-world latency, so backend refresh is
  effectively every 10–20 min — page tells you "live" but it's bounded by
  this. Documented in README. Faster needs a real backend (out of scope).
- Single rebate row in current data → daily-rebate chart shows one bar. Will
  fill in over time; the densify step ensures empty days render as 0-height
  bars rather than gaps.
- Wallet address is committed in source; would need repo to be private +
  Cloudflare Pages if user wants to hide it.

### Next steps (for the user)
1. Create empty GitHub repo, push `online_pnl_web/` contents to its root.
2. Repo Settings → Pages → source = main branch, root folder.
3. Repo Settings → Actions → General → workflow permissions = read+write.
4. Trigger workflow once manually to generate the first deploy.
5. Live URL: `https://<user>.github.io/<repo>/`.
