#!/usr/bin/env python3
"""
Capital Flow Map — NSE sector-rotation tracker.

Pulls the whole NSE equity universe from TradingView's scanner endpoint,
buckets it by industry, and ranks industries by performance RELATIVE to the
Nifty 500 (CNX500) over a chosen window. Writes an HTML dashboard, a CSV
snapshot, and appends to a history file so you can see whether a rotation is
fresh or already three weeks old.

Usage:
    python capital_flow.py                    # 1-month window, default filters
    python capital_flow.py --window 1W        # weekly rotation
    python capital_flow.py --min-mcap 5000    # only >= Rs 5,000 cr companies
    python capital_flow.py --weighting equal  # equal-weight instead of capped

No API key. Data is TradingView's free delayed feed (fine for EOD work).
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

import pandas as pd
from tradingview_screener import Column, Query

# --------------------------------------------------------------------------
# Config
# --------------------------------------------------------------------------

__version__ = "1.1"

MARKET = "india"
BENCHMARK_TICKER = "NSE:CNX500"          # Nifty 500
CRORE = 1e7                               # 1 crore in rupees

WINDOWS = {
    "1W": "Perf.W",
    "1M": "Perf.1M",
    "3M": "Perf.3M",
    "6M": "Perf.6M",
    "YTD": "Perf.YTD",
    "1Y": "Perf.Y",
}

# Columns we want. If TradingView renames any of these the fetch degrades to
# CORE_COLS rather than dying outright.
CORE_COLS = [
    "name",
    "description",
    "close",
    "sector",
    "industry",
    "market_cap_basic",
]
EXTRA_COLS = [
    "change",
    "Value.Traded",
    "average_volume_30d_calc",
    "average_volume_90d_calc",
    "relative_volume_10d_calc",
]


# --------------------------------------------------------------------------
# Fetch
# --------------------------------------------------------------------------


def fetch_universe(perf_field: str, min_mcap_cr: float, min_turnover_cr: float) -> pd.DataFrame:
    """Every primary-listed NSE common stock above the size/liquidity floors."""
    wanted = CORE_COLS + [perf_field] + EXTRA_COLS

    def run(columns):
        q = (
            Query()
            .set_markets(MARKET)
            .select(*columns)
            .where(
                Column("is_primary") == True,  # noqa: E712  (TV needs a literal)
                Column("type") == "stock",
                Column("typespecs").has(["common"]),
                Column("exchange") == "NSE",
                Column("market_cap_basic") >= min_mcap_cr * CRORE,
            )
            .order_by("market_cap_basic", ascending=False)
            .limit(5000)
        )
        return q.get_scanner_data()

    try:
        _, df = run(wanted)
    except Exception as exc:  # a renamed column is the usual culprit
        print(f"  ! full column set failed ({exc}); retrying with core columns", file=sys.stderr)
        _, df = run(CORE_COLS + [perf_field])

    if df is None or df.empty:
        raise RuntimeError("Scanner returned no rows — check your network or the filters.")

    # Liquidity floor. Value.Traded is today's rupee turnover.
    if "Value.Traded" in df.columns and min_turnover_cr > 0:
        df = df[df["Value.Traded"].fillna(0) >= min_turnover_cr * CRORE]

    df = df.dropna(subset=["industry", perf_field, "market_cap_basic"])
    return df.reset_index(drop=True)


def fetch_benchmark(perf_field: str, fallback: pd.DataFrame) -> tuple[float, str]:
    """CNX500 return over the window. Falls back to a cap-weighted universe mean."""
    try:
        _, bdf = (
            Query()
            .set_markets(MARKET)
            .select("name", "close", perf_field)
            .set_tickers(BENCHMARK_TICKER)
            .get_scanner_data()
        )
        if bdf is not None and not bdf.empty and pd.notna(bdf[perf_field].iloc[0]):
            return float(bdf[perf_field].iloc[0]), "CNX500"
    except Exception:
        pass

    w = fallback["market_cap_basic"] / fallback["market_cap_basic"].sum()
    return float((fallback[perf_field] * w).sum()), "cap-weighted universe (CNX500 unavailable)"


# --------------------------------------------------------------------------
# Aggregate
# --------------------------------------------------------------------------


def capped_weights(mcaps: pd.Series, cap: float = 0.25) -> pd.Series:
    """
    Cap-weight, but no single stock gets more than `cap` of its industry.

    Straight cap-weighting makes 'Oil Refining' just mean Reliance. Capping
    keeps the number a statement about the industry, not its largest member.
    """
    w = mcaps / mcaps.sum()
    for _ in range(50):
        over = w > cap
        if not over.any():
            break
        excess = float((w[over] - cap).sum())
        w = w.copy()
        w[over] = cap
        under = ~over
        room = float(w[under].sum())
        if room <= 0:
            break
        w[under] = w[under] + excess * w[under] / room
    return w / w.sum()


def build_industries(
    df: pd.DataFrame,
    perf_field: str,
    benchmark: float,
    weighting: str,
    min_members: int,
) -> pd.DataFrame:
    """One row per industry: its return, its spread vs the benchmark, its members."""
    rows = []
    for industry, grp in df.groupby("industry"):
        if len(grp) < min_members:
            continue

        if weighting == "equal":
            w = pd.Series(1.0 / len(grp), index=grp.index)
        elif weighting == "cap":
            w = grp["market_cap_basic"] / grp["market_cap_basic"].sum()
        else:  # capped (default)
            w = capped_weights(grp["market_cap_basic"])

        ret = float((grp[perf_field] * w).sum())

        # Participation: is the move backed by more money changing hands than
        # usual? >1 means turnover is running hot vs its own 90-day baseline.
        thrust = None
        if {"average_volume_30d_calc", "average_volume_90d_calc"} <= set(grp.columns):
            v30 = (grp["average_volume_30d_calc"] * grp["close"]).sum()
            v90 = (grp["average_volume_90d_calc"] * grp["close"]).sum()
            if v90 and v90 > 0:
                thrust = float(v30 / v90)

        rows.append(
            {
                "industry": industry,
                "sector": grp["sector"].mode().iat[0] if grp["sector"].notna().any() else "",
                "members": len(grp),
                "ret": ret,
                "rel": ret - benchmark,
                "mcap_cr": float(grp["market_cap_basic"].sum() / CRORE),
                "thrust": thrust,
            }
        )

    out = pd.DataFrame(rows).sort_values("rel", ascending=False).reset_index(drop=True)
    out["rank"] = out.index + 1
    return out


def members_of(df: pd.DataFrame, industry: str, perf_field: str,
               industry_ret: float, benchmark: float, top_n: int) -> list[dict]:
    """Stocks inside an industry, best first, starred if they beat both bars."""
    grp = df[df["industry"] == industry].sort_values(perf_field, ascending=False)
    out = []
    for _, r in grp.head(top_n).iterrows():
        out.append(
            {
                "symbol": r["name"],
                "company": r.get("description") or r["name"],
                "ret": float(r[perf_field]),
                "beats_sector": bool(r[perf_field] > industry_ret),
                "beats_bench": bool(r[perf_field] > benchmark),
                "mcap_cr": float(r["market_cap_basic"] / CRORE),
            }
        )
    return out


# --------------------------------------------------------------------------
# History (so you can tell a new rotation from a stale one)
# --------------------------------------------------------------------------


def load_prior_ranks(history_path: Path, window: str) -> dict[str, int]:
    if not history_path.exists():
        return {}
    try:
        h = pd.read_csv(history_path)
        h = h[h["window"] == window]
        if h.empty:
            return {}
        last = h[h["date"] == h["date"].max()]
        return dict(zip(last["industry"], last["rank"]))
    except Exception:
        return {}


def append_history(history_path: Path, ind: pd.DataFrame, window: str, today: str) -> None:
    snap = ind[["industry", "rank", "ret", "rel", "members"]].copy()
    snap.insert(0, "window", window)
    snap.insert(0, "date", today)
    history_path.parent.mkdir(parents=True, exist_ok=True)
    if history_path.exists():
        old = pd.read_csv(history_path)
        old = old[~((old["date"] == today) & (old["window"] == window))]
        snap = pd.concat([old, snap], ignore_index=True)
    snap.to_csv(history_path, index=False)


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------


def main() -> int:
    p = argparse.ArgumentParser(description="Capital Flow Map for NSE")
    p.add_argument("--window", default="1M", choices=list(WINDOWS), help="lookback window")
    p.add_argument("--min-mcap", type=float, default=1000, help="min market cap in Rs crore")
    p.add_argument("--min-turnover", type=float, default=1.0, help="min daily turnover in Rs crore")
    p.add_argument("--min-members", type=int, default=2, help="min stocks for an industry to count")
    p.add_argument("--weighting", default="capped", choices=["capped", "cap", "equal"])
    p.add_argument("--show", type=int, default=6, help="industries shown per side")
    p.add_argument("--stocks", type=int, default=5, help="stocks listed per industry")
    p.add_argument("--outdir", default="output")
    p.add_argument("--nav", default="", help="comma-separated windows to link, e.g. 1W,1M,3M")
    args = p.parse_args()

    perf_field = WINDOWS[args.window]
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    today = dt.date.today().isoformat()

    print(f"capital_flow.py v{__version__}")
    print(f"Fetching NSE universe ({args.window} window)...")
    df = fetch_universe(perf_field, args.min_mcap, args.min_turnover)
    print(f"  {len(df)} stocks passed the filters")

    benchmark, bench_label = fetch_benchmark(perf_field, df)
    print(f"  benchmark {bench_label}: {benchmark:+.2f}%")

    ind = build_industries(df, perf_field, benchmark, args.weighting, args.min_members)
    print(f"  {len(ind)} industries with >= {args.min_members} members")

    history_path = outdir / "history.csv"
    prior = load_prior_ranks(history_path, args.window)
    ind["prev_rank"] = ind["industry"].map(prior)
    ind["rank_delta"] = ind["prev_rank"] - ind["rank"]  # positive = climbing

    inflow = ind.head(args.show).to_dict("records")
    outflow = ind.tail(args.show).iloc[::-1].to_dict("records")  # worst first

    for row in inflow:
        row["stocks"] = members_of(df, row["industry"], perf_field, row["ret"], benchmark, args.stocks)
    for row in outflow:
        grp = df[df["industry"] == row["industry"]].sort_values(perf_field)
        row["stocks"] = [
            {
                "symbol": r["name"],
                "company": r.get("description") or r["name"],
                "ret": float(r[perf_field]),
                "beats_sector": bool(r[perf_field] > row["ret"]),
                "beats_bench": bool(r[perf_field] > benchmark),
                "mcap_cr": float(r["market_cap_basic"] / CRORE),
            }
            for _, r in grp.head(args.stocks).iterrows()
        ]

    payload = {
        "date": today,
        "window": args.window,
        "benchmark": benchmark,
        "benchmark_label": bench_label,
        "weighting": args.weighting,
        "universe_size": int(len(df)),
        "industry_count": int(len(ind)),
        "inflow": inflow,
        "outflow": outflow,
    }

    from render import render_html

    nav_windows = [w.strip() for w in args.nav.split(",") if w.strip()]
    html = render_html(payload, nav_windows)
    (outdir / "index.html").write_text(html, encoding="utf-8")
    (outdir / f"flowmap_{today}_{args.window}.html").write_text(html, encoding="utf-8")
    ind.to_csv(outdir / f"industries_{today}_{args.window}.csv", index=False)
    df.to_csv(outdir / f"universe_{today}.csv", index=False)
    (outdir / "latest.json").write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    append_history(history_path, ind, args.window, today)

    print(f"\nWrote {outdir / 'index.html'}")
    print("\nTop 5 inflow:")
    for r in inflow[:5]:
        print(f"  {r['industry']:<38} {r['ret']:+7.2f}%  (vs bench {r['rel']:+6.2f}%)")
    print("Top 5 outflow:")
    for r in outflow[:5]:
        print(f"  {r['industry']:<38} {r['ret']:+7.2f}%  (vs bench {r['rel']:+6.2f}%)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
