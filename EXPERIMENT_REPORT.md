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

---

# Task 2 — Regime Tests by Time

**Date:** 2026-05-07

## 1. User Request

Add two new "regime test" charts to the existing dashboard:

1. **Hourly regime**: bin per-market PnL by UTC hour-of-day of `market_end_ts`.
   x-axis = UTC hour (0–23), y-axis = mean PnL.
   Background-shade China trading hours (9:00–21:00 CN local) and
   US trading hours (9:00–21:00 ET local) with two distinct colors.
2. **Weekly regime**: bin by hour-of-week with the week starting Monday
   00:00 UTC and ending Sunday 23:59 UTC (168 hourly buckets).
   Background-shade China weekend (Sat–Sun CN) and US weekend (Sat–Sun ET)
   with two distinct colors; the overlap region should render in a deeper
   color.

Design must remain consistent with the existing institutional dark HUD aesthetic.

## 2. Confirmed Choices

- **US timezone**: Eastern Time (ET). Current data is May 2026 → DST is in
  effect → ET = UTC-4. Background overlays use this offset (the
  overlay-rectangle would shift by 1 hour when DST ends; data binning is
  unaffected since it lives in UTC).
- **Bucket key**: `market_end_ts` (consistent with `cumulative_pnl`).
- **Weekly granularity**: 168 hourly buckets (Mon 00 → Sun 23 UTC).
- **Layout**: insert as a new row (panels 06 + 07) after the existing
  04/05 regime row; do not replace existing regime charts.

## 3. Planned Approach

### Background-shade math

China trading hours, CN local 09:00–21:00 (UTC+8, no DST):
- UTC range: [01:00, 13:00) → buckets `[1, 12]` on hourly chart.

US trading hours, ET local 09:00–21:00 (UTC-4 in DST):
- UTC range: [13:00, 01:00 next day) → buckets `[13, 23] ∪ [0, 0]`.
- No overlap with China on hourly chart.

China weekend, Sat 00:00 – Sun 23:59 CN (UTC+8):
- UTC range: Fri 16:00 → Sun 16:00 → bucket idx `[112, 159]` (48 hr).

US weekend, Sat 00:00 – Sun 23:59 ET (UTC-4 DST):
- UTC range: Sat 04:00 → Mon 04:00 → bucket idx `[124, 167] ∪ [0, 3]`.

Three regions on weekly chart:
- China-only: idx `[112, 123]`
- Overlap (deeper color): idx `[124, 159]`
- US-only: idx `[160, 167] ∪ [0, 3]`

### Data layer

Add `regime_hourly` and `regime_weekly` arrays to `data.json`:
```jsonc
"regime_hourly": [{"hour": 0, "avg_pnl": ..., "n_markets": ..., "total_pnl": ...}, ...],
"regime_weekly": [{"idx": 0, "day": "Mon", "hour": 0, "avg_pnl": ..., "n_markets": ..., "total_pnl": ...}, ...]
```

Two new helpers in `calc_pnl.py`:
- `regime_hourly_table(per_market)` — groupby UTC hour of `market_end_ts`,
  reindex to dense 24-hour range.
- `regime_weekly_table(per_market)` — groupby `dayofweek*24 + hour`,
  reindex to dense 168-bucket range.

### Frontend

Two new ECharts panels using existing `axisCommon`/`tooltipBase` theme:
- Bars colored mint (positive) / coral (negative), matching panel 04 style.
- `markArea` rectangles for trading-hour / weekend overlays:
  - China = blue `rgba(96,165,250, ...)` low-alpha
  - US = violet `rgba(167,139,250, ...)` low-alpha
  - Overlap (weekly only) = deep purple `rgba(139,92,246, 0.22)` for clear contrast
- Sparse axis labels on weekly chart (one label per day at hour 0).
- Hover tooltip shows bucket label + n_markets + avg PnL + total PnL.
- Subtitle in `panel-meta` notes the timezone assumption.

## 4. Results & Observations

### Built
- `calc_pnl.py` gained `regime_hourly_table()` and `regime_weekly_table()`,
  both densified to 24 / 168 buckets and emitted in `data.json` under new
  keys `regime_hourly` and `regime_weekly`. Empty buckets are zero-filled
  with `n_markets = 0` so the UI can render a flat "no entry" gap.
- `index.html` gained a region-legend pill component and two new full-width
  panels (06 hour-of-day, 07 hour-of-week) inserted after the original
  04/05 regime row, preserving the original layout flow.
- `markArea` overlays:
  - Panel 06: blue [01,12] for China trade, violet [13,23] and [00,00]
    for US trade ET DST. No overlap exists on this chart.
  - Panel 07: blue [112,123] for CN-only, deep purple [124,159] for the
    overlap zone, violet [160,167] and [0,3] for US-only tail/wrap.
- Hourly bars share the same `makeBarItem` factory (mint gradient for
  positive, coral for negative, dim gray for zero-entry), keeping panel
  06/07 visually consistent with panel 04.
- Weekly chart axisLabel collapses to one tick per day (`Mon`/`Tue`/...)
  with dashed splitLines at every 24-hour boundary, so the 168-bucket
  density stays legible.
- Reveal animations extended with `.r-d12` / `.r-d13` delays so the new
  rows fade in after the existing extremes block.

### Verified
- `python calc_pnl.py` ran clean against the live cache, producing
  `regime_hourly` (length 24) and `regime_weekly` (length 168) with
  expected schema. Sample buckets: hour 0 has 17 markets avg +$0.50,
  hour 1 has 15 markets avg +$1.18, hour 2 has 16 markets avg +$1.57.
- Wallet now totals `+$35.16 USDC, 325 markets, 74.2% win, $4.03 rebates`
  — incremental fetch added 273 records since the prior run.
- Local HTTP server screenshot was blocked by sandbox policy; relied on
  static structural review (script-tag balance, function-def counts,
  ID resolution between div + init) plus careful category-name math
  for `markArea` boundaries.

### Known caveats
- `markArea` background offsets assume US ET DST (UTC-4). When DST ends
  on 2026-11-01, the US trading-hour and US-weekend rectangles will be
  off by 1 UTC hour visually until they're switched to UTC-5. The data
  binning itself stays correct (it's all UTC). A future enhancement
  could compute the offset per-row in Python and emit two background
  arrays for the frontend to switch between, but YAGNI for now.
- With only ~2 weeks of cached data the weekly chart has many empty
  buckets — the design accommodates this (no-entry buckets render as
  gaps). Density will fill in as the wallet trades through more weeks.

### Deployment (2026-05-07)

- Workflow `.github/workflows/refresh.yml` extended to also fire on
  pushes touching `index.html` or `requirements.txt` (in addition to
  `calc_pnl.py` and the workflow file). Frontend-only updates can now
  trigger a fresh data run alongside the 10-min cron.
- Local feature commit `f80169d` had to rebase onto 18 intervening
  `github-actions[bot]` data-refresh commits. Rebase strategy: keep
  local versions of `data.json` + `activity_cache.json` (they carry the
  new schema fields); the next cron tick regenerates with the fresh
  cache anyway. Rebased commit `a6907e1` pushed to `origin/main`.
- Push triggered the `refresh-pnl` workflow (path match on
  `calc_pnl.py` + `index.html`), so the bot regenerates `data.json`
  with the new schema immediately. Pages auto-redeploys the new
  `index.html` within ~1 min of push.
