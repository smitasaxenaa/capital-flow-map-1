# Capital Flow Map (NSE)

Ranks every NSE industry by how it performed **relative to the CNX500** over a
chosen window, splits them into "money flowing out" and "money flowing in", and
lists the leading/lagging stocks inside each. Rebuilds daily.

## Run it

```bash
pip install -r requirements.txt
python capital_flow.py                 # 1-month window
open output/index.html
```

Options:

```
--window 1W|1M|3M|6M|YTD|1Y    lookback (default 1M)
--min-mcap 1000                min market cap, Rs crore (default 1000)
--min-turnover 1.0             min daily turnover, Rs crore (default 1.0)
--min-members 2                industries below this are dropped (default 2)
--weighting capped|cap|equal   how stocks roll up into an industry
--show 6                       industries per side
--stocks 5                     stocks listed per industry
```

## Where the data comes from

TradingView's public scanner endpoint (`scanner.tradingview.com/india/scan`),
via the `tradingview-screener` package. No key, no login, no scraping — it's the
same JSON their own screener page uses.

This matters for one specific reason: the industry names in the tool you
screenshotted — *Drugstore Chains*, *Contract Drilling*, *Electronics
Distributors*, *Beverages: Non-Alcoholic* — are verbatim TradingView industry
labels. That taxonomy has ~145 industries. NSE's own classification is much
coarser (~20 sectors: "Healthcare", "Energy"), which is why sector dashboards
built on NSE data never look this granular. Using TradingView's feed gets you
the same buckets as the reference tool.

The trade-off: it's an undocumented endpoint on someone else's terms of service,
and the free tier is delayed. Fine for an end-of-day personal tool. If it ever
breaks or you want something contractual, swap `fetch_universe()` for a broker
API (Zerodha Kite, Upstox, Dhan all have historical OHLC) plus your own industry
mapping table — the rest of the pipeline doesn't change.

## How the numbers are built

1. **Universe** — primary-listed NSE common stocks above the market-cap and
   turnover floors. Floors matter: without them a ₹40 cr shell that doubled
   drags a whole industry's average with it.
2. **Industry return** — weighted mean of member returns. Default weighting is
   `capped`: cap-weighted, but no single stock exceeds 25% of its industry.
   Straight cap-weighting makes "Oil Refining" a synonym for Reliance; equal
   weighting lets the smallest, least liquid member speak as loudly as the
   largest. Capped sits between.
3. **Relative** — industry return minus CNX500 return over the same window.
   This is the ranking key, not raw return. In a month where the index is up 6%,
   an industry up 3% is losing capital, not gaining it.
4. **★** — a stock beat both its own industry and the CNX500.
5. **turnover ×** — 30-day traded value ÷ 90-day traded value. Above ~1.15 means
   the move is backed by unusually heavy participation.
6. **▲▼** — rank change since the previous run, read from `output/history.csv`.

## The one thing to be clear-eyed about

Despite the name, this measures **price performance, not capital flow.** Nothing
here observes money entering or leaving anything. A sector can lead the index on
thin volume while institutions quietly sell into it.

That's true of the tool you screenshotted too. It's still useful — relative
strength is a real signal — but treat it as a *rotation map*, not a flows
report. The `turnover ×` column exists as a partial corrective: price up **and**
turnover up is a much stronger read than price up alone. For actual flows you'd
need FII/DII activity data (NSE publishes daily provisional figures) or
mutual-fund AUM changes, which are monthly and lagged.

The second caveat: a 1-month lookback is a trailing window. By the time an
industry tops this list, a good part of the move has happened. Running `1W`
alongside `1M` helps — an industry rising in both is accelerating; strong on 1M
but weak on 1W is a rotation that may already be ending.

## Daily automation

`.github/workflows/daily.yml` runs at 17:00 IST on weekdays, builds the 1W/1M/3M
maps, commits history, and publishes to GitHub Pages. Push the repo, then enable
Settings → Pages → Source: **GitHub Actions**.

To run locally instead, add to `crontab -e`:

```
0 17 * * 1-5 cd /path/to/capflow && /usr/bin/python3 capital_flow.py >> run.log 2>&1
```

## Files produced

```
output/index.html                    the dashboard
output/flowmap_<date>_<window>.html  dated archive
output/industries_<date>_<w>.csv     every industry, ranked
output/universe_<date>.csv           raw per-stock data
output/history.csv                   appended each run — powers the ▲▼ arrows
output/latest.json                   for feeding other tools
```

`history.csv` is the part that compounds. After a couple of months you can ask
questions the dashboard alone can't answer: how long does an industry usually
stay in the top 5, and does entering it actually precede further gains?
