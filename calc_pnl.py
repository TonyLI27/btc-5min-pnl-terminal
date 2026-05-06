"""
Compute realized PnL + rebate stream for a Polymarket account from
on-chain activity. JSON-only — no PNGs. Drives the static HTML dashboard.

- Pulls /activity from data-api.polymarket.com for our address since 2026-05-04 UTC
- Caches to activity_cache.json with idempotent incremental updates
- Filters bitcoin trades, aggregates per-market BUY+REDEEM into single PnL
- Extracts MAKER_REBATE rows separately and bins by UTC calendar day
- Emits data.json consumed by index.html via fetch()

Run: `python calc_pnl.py`
"""

from __future__ import annotations

import json
import re
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import requests


ADDRESS = "0x6639985946d3016B83Ca5Cf1667810DAc3587202"
API_URL = "https://data-api.polymarket.com/activity"

START_TS = int(datetime(2026, 5, 4, 0, 0, 0, tzinfo=timezone.utc).timestamp())

PAGE_LIMIT = 500
MAX_OFFSET = 10000
INCREMENTAL_BUFFER_S = 3600

SCRIPT_DIR = Path(__file__).resolve().parent
CACHE_FILE = SCRIPT_DIR / "activity_cache.json"
DATA_FILE = SCRIPT_DIR / "data.json"


# ---------------------------------------------------------------------------
# Cache I/O
# ---------------------------------------------------------------------------

def load_cache() -> list[dict]:
    if CACHE_FILE.exists():
        with CACHE_FILE.open("r", encoding="utf-8") as f:
            return json.load(f)
    return []


def save_cache(records: list[dict]) -> None:
    with CACHE_FILE.open("w", encoding="utf-8") as f:
        json.dump(records, f, indent=2, sort_keys=True)


def record_key(rec: dict) -> str:
    return "|".join(str(rec.get(k, "")) for k in
                    ("transactionHash", "asset", "type", "side", "timestamp", "size"))


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------

def fetch_activity(start_ts: int) -> list[dict]:
    out: list[dict] = []
    offset = 0
    session = requests.Session()
    while True:
        params = {
            "user": ADDRESS,
            "limit": PAGE_LIMIT,
            "offset": offset,
            "start": start_ts,
            "sortBy": "TIMESTAMP",
            "sortDirection": "ASC",
        }
        r = session.get(API_URL, params=params, timeout=30)
        r.raise_for_status()
        batch = r.json() or []
        print(f"  start={start_ts} offset={offset}: got {len(batch)} records")
        if not batch:
            break
        out.extend(batch)
        if len(batch) < PAGE_LIMIT:
            break
        offset += PAGE_LIMIT
        if offset > MAX_OFFSET:
            last_ts = int(batch[-1]["timestamp"])
            print(f"  hit offset cap; advancing start to {last_ts}")
            out.extend(fetch_activity(last_ts))
            break
        time.sleep(0.15)
    return out


def update_cache() -> list[dict]:
    cached = load_cache()
    if cached:
        max_ts = max(int(r["timestamp"]) for r in cached)
        fetch_from = max(START_TS, max_ts - INCREMENTAL_BUFFER_S)
        print(f"Incremental fetch from {fetch_from} "
              f"(cache has {len(cached)} records, max ts {max_ts})")
    else:
        fetch_from = START_TS
        print(f"Cold fetch from {fetch_from}")

    new_records = fetch_activity(fetch_from)

    seen = {record_key(r) for r in cached}
    added = 0
    for r in new_records:
        k = record_key(r)
        if k not in seen:
            cached.append(r)
            seen.add(k)
            added += 1
    cached.sort(key=lambda r: int(r["timestamp"]))
    save_cache(cached)
    print(f"Added {added} new records. Cache now {len(cached)} total.")
    return cached


# ---------------------------------------------------------------------------
# Cash-impact mapping
# ---------------------------------------------------------------------------

REBATE_TYPES = {"REWARD", "MAKER_REBATE", "REFERRAL_REWARD"}


def cash_delta(rec: dict) -> float:
    """Signed change in our USDC cash balance for one activity row."""
    t = (rec.get("type") or "").upper()
    side = (rec.get("side") or "").upper()
    usdc = float(rec.get("usdcSize") or 0.0)

    if t == "TRADE":
        if side == "BUY":
            return -usdc
        if side == "SELL":
            return +usdc
        return 0.0
    if t == "SPLIT":
        return -usdc
    if t == "MERGE":
        return +usdc
    if t == "REDEEM":
        return +usdc
    if t in REBATE_TYPES:
        # Rebate rows have no usdcSize on Polymarket — payout is in `size`
        # (already denominated in USDC since price is implicitly 1).
        if usdc == 0.0:
            usdc = float(rec.get("size") or 0.0)
        return +usdc
    if t == "CONVERSION":
        return 0.0
    return 0.0


# ---------------------------------------------------------------------------
# Bitcoin filter + market identity
# ---------------------------------------------------------------------------

def is_bitcoin(rec: dict) -> bool:
    blob = " ".join(str(rec.get(k) or "") for k in ("title", "slug", "eventSlug")).lower()
    return "bitcoin" in blob or "btc" in blob


_SLUG_TS_RE = re.compile(r"-(\d{10})$")


def market_id(rec: dict) -> str:
    return (rec.get("eventSlug") or rec.get("slug")
            or rec.get("conditionId") or "")


def market_end_ts(rec: dict) -> int | None:
    for key in ("eventSlug", "slug"):
        s = rec.get(key) or ""
        m = _SLUG_TS_RE.search(s)
        if m:
            return int(m.group(1)) + 300
    return None


# ---------------------------------------------------------------------------
# Per-market aggregation + regime
# ---------------------------------------------------------------------------

def aggregate_per_market(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for mid, g in df.groupby("market_id"):
        buys = g[g["side"] == "BUY"]
        size_sum = buys["size"].sum()
        wap = (buys["size"] * buys["price"]).sum() / size_sum if size_sum > 0 else np.nan
        end_ts = (g["market_end_ts"].dropna().iloc[0]
                  if g["market_end_ts"].notna().any()
                  else g["timestamp"].max())
        rows.append({
            "market_id": mid,
            "title": g["title"].iloc[0],
            "market_end_ts": int(end_ts),
            "pnl": float(g["cash_delta"].sum()),
            "n_buys": int(len(buys)),
            "total_buy_size": float(size_sum),
            "weighted_entry_price": float(wap) if not pd.isna(wap) else None,
            "outcome": (buys["outcome"].iloc[0] if len(buys) else ""),
        })
    return (pd.DataFrame(rows)
            .sort_values("market_end_ts")
            .reset_index(drop=True))


def regime_table(per_market: pd.DataFrame) -> pd.DataFrame:
    bins = np.round(np.arange(0.0, 1.0001, 0.1), 2)
    labels = [f"[{bins[i]:.1f},{bins[i+1]:.1f})" for i in range(len(bins) - 1)]
    labels[-1] = f"[{bins[-2]:.1f},{bins[-1]:.1f}]"

    valid = per_market.dropna(subset=["weighted_entry_price"]).copy()
    valid["bin"] = pd.cut(valid["weighted_entry_price"],
                          bins=bins, labels=labels,
                          include_lowest=True, right=False)
    edge = valid["weighted_entry_price"] >= bins[-1]
    if edge.any():
        valid.loc[edge, "bin"] = labels[-1]

    g = valid.groupby("bin", observed=False)["pnl"].agg(["mean", "sum", "count"])
    g = g.rename(columns={"mean": "avg_pnl", "sum": "total_pnl", "count": "n_markets"})
    return g.reindex(labels).reset_index()


# ---------------------------------------------------------------------------
# Cumulative time series, resampled to 5-min buckets
# ---------------------------------------------------------------------------

def build_cumulative_series(per_market: pd.DataFrame) -> list[dict]:
    if per_market.empty:
        return []
    s = pd.Series(
        per_market["pnl"].values,
        index=pd.to_datetime(per_market["market_end_ts"], unit="s", utc=True),
    ).sort_index()
    binned = s.resample("5min", label="right", closed="right").sum()
    cum = binned.cumsum()
    return [{"t": int(idx.value // 1_000_000), "v": float(v)}
            for idx, v in cum.items()]


# ---------------------------------------------------------------------------
# Daily rebate aggregation
# ---------------------------------------------------------------------------

def build_daily_rebates(records: list[dict]) -> list[dict]:
    """Group all REBATE-type rows by UTC calendar day, emit a dense series."""
    rebates = [r for r in records if (r.get("type") or "").upper() in REBATE_TYPES]
    if not rebates:
        return []

    rows = []
    for r in rebates:
        ts = int(r["timestamp"])
        amt = float(r.get("usdcSize") or 0.0) or float(r.get("size") or 0.0)
        rows.append({"ts": ts, "usdc": amt})

    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["ts"], unit="s", utc=True).dt.date
    daily = df.groupby("date")["usdc"].sum().sort_index()

    # Densify — fill calendar gaps with 0, so the bar chart shows empty days.
    if len(daily):
        full_idx = pd.date_range(daily.index.min(), daily.index.max(), freq="D").date
        daily = daily.reindex(full_idx, fill_value=0.0)

    return [{"date": d.isoformat(), "usdc": float(v)} for d, v in daily.items()]


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    records = update_cache()

    btc = [r for r in records if is_bitcoin(r)]
    print(f"\nBitcoin-related activities: {len(btc)} / {len(records)}")

    # Per-row dataframe for trade-side aggregation
    trade_rows = []
    for r in btc:
        ts = int(r["timestamp"])
        trade_rows.append({
            "timestamp": ts,
            "type": (r.get("type") or "").upper(),
            "side": (r.get("side") or "").upper(),
            "title": r.get("title"),
            "outcome": r.get("outcome"),
            "size": float(r.get("size") or 0),
            "price": float(r.get("price") or 0),
            "usdcSize": float(r.get("usdcSize") or 0),
            "cash_delta": cash_delta(r),
            "market_id": market_id(r),
            "market_end_ts": market_end_ts(r),
        })

    per_market = pd.DataFrame()
    cumulative = []
    regime = pd.DataFrame()
    if trade_rows:
        df = pd.DataFrame(trade_rows).sort_values("timestamp").reset_index(drop=True)
        per_market = aggregate_per_market(df)
        cumulative = build_cumulative_series(per_market)
        regime = regime_table(per_market)

    # ---- Rebates (across ALL markets, not just BTC — wallet-level stream) ----
    daily_rebates = build_daily_rebates(records)
    total_rebates = sum(d["usdc"] for d in daily_rebates)

    # ---- KPIs ---------------------------------------------------------------
    total_pnl = float(per_market["pnl"].sum()) if len(per_market) else 0.0
    n_markets = int(len(per_market))
    n_winners = int((per_market["pnl"] > 0).sum()) if n_markets else 0
    n_losers = int((per_market["pnl"] < 0).sum()) if n_markets else 0
    win_rate = (n_winners / n_markets * 100) if n_markets else 0.0
    avg_pnl = float(per_market["pnl"].mean()) if n_markets else 0.0
    median_pnl = float(per_market["pnl"].median()) if n_markets else 0.0
    total_buy_volume = float(per_market["total_buy_size"].sum()) if n_markets else 0.0
    rot = (total_pnl / total_buy_volume) if total_buy_volume else 0.0

    if n_markets:
        first_end = int(per_market["market_end_ts"].min())
        last_end = int(per_market["market_end_ts"].max())
        first_dt = datetime.fromtimestamp(first_end, tz=timezone.utc)
        last_dt = datetime.fromtimestamp(last_end, tz=timezone.utc)
        running_days = (last_dt.date() - first_dt.date()).days + 1
    else:
        first_end = last_end = 0
        running_days = 0

    # ---- Extremes -----------------------------------------------------------
    def _market_summary(row) -> dict:
        return {
            "title": row["title"],
            "outcome": row["outcome"] or "",
            "market_end_ts": int(row["market_end_ts"]),
            "weighted_entry_price": (
                float(row["weighted_entry_price"])
                if row["weighted_entry_price"] is not None
                and not pd.isna(row["weighted_entry_price"])
                else None
            ),
            "n_buys": int(row["n_buys"]),
            "total_buy_size": float(row["total_buy_size"]),
            "pnl": float(row["pnl"]),
        }

    extremes = {}
    if n_markets:
        best = per_market.loc[per_market["pnl"].idxmax()]
        worst = per_market.loc[per_market["pnl"].idxmin()]
        extremes = {"best": _market_summary(best), "worst": _market_summary(worst)}

    # ---- Recent (last 24 markets) -------------------------------------------
    recent = []
    if n_markets:
        rec_df = per_market.sort_values("market_end_ts", ascending=False).head(24)
        recent = [_market_summary(r) for _, r in rec_df.iterrows()]

    # ---- Regime list --------------------------------------------------------
    regime_list = []
    for _, r in regime.iterrows():
        regime_list.append({
            "bin": str(r["bin"]),
            "avg_pnl": (float(r["avg_pnl"]) if not pd.isna(r["avg_pnl"]) else 0.0),
            "n_markets": (int(r["n_markets"]) if not pd.isna(r["n_markets"]) else 0),
            "total_pnl": (float(r["total_pnl"]) if not pd.isna(r["total_pnl"]) else 0.0),
        })

    payload = {
        "meta": {
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "wallet": ADDRESS,
            "window_start_ts": first_end if n_markets else None,
            "window_end_ts": last_end if n_markets else None,
            "n_total_records": len(records),
            "n_btc_records": len(btc),
        },
        "kpi": {
            "total_pnl": total_pnl,
            "n_markets": n_markets,
            "n_winners": n_winners,
            "n_losers": n_losers,
            "win_rate_pct": win_rate,
            "avg_pnl": avg_pnl,
            "median_pnl": median_pnl,
            "rot": rot,
            "total_buy_volume": total_buy_volume,
            "running_days": running_days,
            "total_rebates": total_rebates,
        },
        "cumulative_pnl": cumulative,
        "regime": regime_list,
        "daily_rebates": daily_rebates,
        "extremes": extremes,
        "recent": recent,
    }

    DATA_FILE.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"\nSaved → {DATA_FILE.name}")
    print(f"  total_pnl={total_pnl:+.2f} USDC | markets={n_markets} | "
          f"win={win_rate:.1f}% | rebates=${total_rebates:.4f}")


if __name__ == "__main__":
    main()
