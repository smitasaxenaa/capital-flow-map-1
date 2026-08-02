"""HTML renderer for the capital flow map."""

from __future__ import annotations

__version__ = "1.1"

import datetime as dt
import html


def _fmt_mcap(cr: float) -> str:
    if cr >= 1e5:
        return f"₹{cr / 1e5:.1f}L cr"
    if cr >= 1000:
        return f"₹{cr / 1000:.1f}k cr"
    return f"₹{cr:.0f} cr"


def _rank_badge(delta) -> str:
    if delta is None or delta != delta:  # NaN
        return '<span class="delta new">new</span>'
    d = int(delta)
    if d == 0:
        return '<span class="delta flat">—</span>'
    arrow = "▲" if d > 0 else "▼"
    cls = "up" if d > 0 else "down"
    return f'<span class="delta {cls}">{arrow}{abs(d)}</span>'


def _stock_rows(stocks: list[dict], side: str) -> str:
    out = []
    for s in stocks:
        star = "★" if (s["beats_sector"] and s["beats_bench"]) else ""
        tags = []
        if s["beats_sector"]:
            tags.append('<span class="tag">↑ind</span>')
        if s["beats_bench"]:
            tags.append('<span class="tag">↑CNX</span>')
        out.append(
            f'<tr>'
            f'<td class="star">{star}</td>'
            f'<td class="sym">{html.escape(s["symbol"])}'
            f'<span class="co">{html.escape(s["company"][:44])}</span></td>'
            f'<td class="mc">{_fmt_mcap(s["mcap_cr"])}</td>'
            f'<td class="pct {side}">{s["ret"]:+.1f}%</td>'
            f'<td class="tags">{"".join(tags)}</td>'
            f'</tr>'
        )
    return "".join(out)


def _industry_block(row: dict, idx: int, side: str) -> str:
    thrust = row.get("thrust")
    if thrust:
        t_cls = "hot" if thrust >= 1.15 else ("cold" if thrust <= 0.85 else "")
        thrust_html = (
            f'<span class="thrust {t_cls}" title="30-day turnover vs 90-day baseline. '
            f'Above 1.0 means more money is actually changing hands than usual.">'
            f'turnover {thrust:.2f}×</span>'
        )
    else:
        thrust_html = ""

    word = "OVER" if side == "in" else "UNDER"
    return f"""
    <details class="ind {side}" {'open' if idx == 1 else ''}>
      <summary>
        <span class="num">{idx}</span>
        <span class="iname">{html.escape(row["industry"])}
          <span class="meta">{row["members"]} stocks · {_fmt_mcap(row["mcap_cr"])} {thrust_html}</span>
        </span>
        <span class="figs">
          <span class="big {side}">{row["ret"]:+.1f}%</span>
          <span class="rel">{word} CNX500 by {row["rel"]:+.1f}% {_rank_badge(row.get("rank_delta"))}</span>
        </span>
      </summary>
      <table class="stocks">{_stock_rows(row["stocks"], side)}</table>
    </details>"""


def _nav(current: str, windows: list[str]) -> str:
    if not windows:
        return ""
    links = "".join(
        f'<a class="{"on" if w == current else ""}" href="../{w}/">{w}</a>' for w in windows
    )
    return f'<nav class="wnav">{links}</nav>'


def render_html(d: dict, nav_windows: list[str] | None = None) -> str:
    stamp = dt.datetime.now().strftime("%d %b %Y, %H:%M IST")
    nav = _nav(d["window"], nav_windows or [])
    outflow = "".join(_industry_block(r, i + 1, "out") for i, r in enumerate(d["outflow"]))
    inflow = "".join(_industry_block(r, i + 1, "in") for i, r in enumerate(d["inflow"]))

    return f"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="theme-color" content="#f7f8fa">
<title>Capital Flow Map — {d["window"]} — {d["date"]}</title>
<style>
  :root {{
    --ink:#12161c; --muted:#6b7683; --line:#e3e7ec; --bg:#f7f8fa; --card:#fff;
    --red:#c02f3c; --red-bg:#fdf2f3; --red-line:#f2d4d7;
    --green:#0f7a52; --green-bg:#f1faf5; --green-line:#cbe9da;
  }}
  @media (prefers-color-scheme: dark) {{
    :root {{ --ink:#e8ecf1; --muted:#8c98a6; --line:#252b33; --bg:#0e1116; --card:#151a21;
      --red:#f2727f; --red-bg:#1e1416; --red-line:#3a2226;
      --green:#4ecf99; --green-bg:#0f1a16; --green-line:#1e3a2c; }}
  }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; padding:28px 20px 60px; background:var(--bg); color:var(--ink);
    font:15px/1.5 ui-sans-serif,-apple-system,"Segoe UI",Inter,system-ui,sans-serif; }}
  .wrap {{ max-width:1360px; margin:0 auto; }}
  h1 {{ font-size:20px; letter-spacing:-.02em; margin:0 0 4px; text-align:center; }}
  .sub {{ text-align:center; color:var(--muted); font-size:13px; margin-bottom:6px; }}
  .stats {{ text-align:center; color:var(--muted); font-size:12px; margin-bottom:26px;
    font-variant-numeric:tabular-nums; }}
  .stats b {{ color:var(--ink); font-weight:600; }}

  .grid {{ display:grid; grid-template-columns:1fr 88px 1fr; gap:0 18px; align-items:start; }}
  @media (max-width:900px) {{ .grid {{ grid-template-columns:1fr; }} .spine {{ display:none; }} }}

  .head {{ display:flex; align-items:center; gap:10px; padding:13px 18px; border-radius:12px;
    margin-bottom:12px; font-weight:650; letter-spacing:.01em; }}
  .head small {{ display:block; font-weight:400; font-size:12px; color:var(--muted); }}
  .head.out {{ background:var(--red-bg); color:var(--red); border:1px solid var(--red-line); }}
  .head.in  {{ background:var(--green-bg); color:var(--green); border:1px solid var(--green-line); }}
  .dot {{ width:11px; height:11px; border-radius:50%; flex:none; }}
  .head.out .dot {{ background:var(--red); }} .head.in .dot {{ background:var(--green); }}

  /* Signature: the rotation spine. Bars lean left or right with the flow. */
  .spine {{ display:flex; flex-direction:column; align-items:center; gap:7px; padding-top:74px; }}
  .spine i {{ display:block; width:52px; height:7px; border-radius:4px;
    background:linear-gradient(90deg,var(--red),var(--green)); opacity:.5; }}
  .spine i:nth-child(2n) {{ width:38px; opacity:.3; }}
  .spine span {{ font-size:9.5px; letter-spacing:.14em; color:var(--muted);
    writing-mode:vertical-rl; margin:6px 0; }}

  details.ind {{ background:var(--card); border:1px solid var(--line); border-radius:12px;
    margin-bottom:10px; overflow:hidden; }}
  details.ind.out {{ border-color:var(--red-line); }}
  details.ind.in  {{ border-color:var(--green-line); }}
  summary {{ display:flex; align-items:center; gap:13px; padding:14px 16px; cursor:pointer;
    list-style:none; }}
  summary::-webkit-details-marker {{ display:none; }}
  summary:focus-visible {{ outline:2px solid var(--ink); outline-offset:-2px; }}
  .num {{ width:25px; height:25px; border-radius:50%; flex:none; display:grid; place-items:center;
    font-size:12px; font-weight:600; border:1px solid currentColor; }}
  .out .num {{ color:var(--red); }} .in .num {{ color:var(--green); }}
  .iname {{ flex:1; font-weight:600; font-size:14.5px; min-width:0; }}
  .meta {{ display:block; font-weight:400; font-size:11.5px; color:var(--muted); margin-top:2px; }}
  .thrust {{ margin-left:6px; padding:1px 5px; border-radius:4px; border:1px solid var(--line);
    font-variant-numeric:tabular-nums; }}
  .thrust.hot {{ color:var(--green); border-color:var(--green-line); }}
  .thrust.cold {{ color:var(--muted); }}
  .figs {{ text-align:right; flex:none; }}
  .big {{ display:block; font-size:23px; font-weight:600; letter-spacing:-.02em;
    font-variant-numeric:tabular-nums; }}
  .big.out {{ color:var(--red); }} .big.in {{ color:var(--green); }}
  .rel {{ font-size:11px; color:var(--muted); font-variant-numeric:tabular-nums; }}
  .delta {{ margin-left:5px; padding:1px 4px; border-radius:4px; font-size:10px; }}
  .delta.up {{ color:var(--green); background:var(--green-bg); }}
  .delta.down {{ color:var(--red); background:var(--red-bg); }}
  .delta.flat, .delta.new {{ color:var(--muted); }}

  table.stocks {{ width:100%; border-collapse:collapse; border-top:1px solid var(--line); }}
  table.stocks td {{ padding:8px 10px; border-bottom:1px solid var(--line); font-size:13px;
    vertical-align:middle; }}
  table.stocks tr:last-child td {{ border-bottom:none; }}
  td.star {{ width:20px; color:#d19a1a; }}
  td.sym {{ font-weight:600; }}
  .co {{ display:block; font-weight:400; font-size:11px; color:var(--muted); }}
  td.mc {{ text-align:right; color:var(--muted); font-size:11.5px;
    font-variant-numeric:tabular-nums; white-space:nowrap; }}
  td.pct {{ text-align:right; width:76px; font-weight:600;
    font-variant-numeric:tabular-nums; }}
  td.pct.out {{ color:var(--red); }} td.pct.in {{ color:var(--green); }}
  td.tags {{ width:96px; text-align:right; }}
  .tag {{ display:inline-block; margin-left:3px; padding:1px 5px; border-radius:4px;
    font-size:9.5px; border:1px solid var(--line); color:var(--muted); }}

  .wnav {{ display:flex; justify-content:center; gap:6px; margin:0 0 22px; }}
  .wnav a {{ padding:5px 15px; border-radius:999px; border:1px solid var(--line);
    text-decoration:none; color:var(--muted); font-size:12.5px; font-weight:600;
    background:var(--card); }}
  .wnav a.on {{ color:var(--card); background:var(--ink); border-color:var(--ink); }}

  footer {{ margin-top:34px; text-align:center; color:var(--muted); font-size:11.5px;
    line-height:1.7; }}

  @media (max-width:640px) {{
    body {{ padding:18px 12px 44px; }}
    h1 {{ font-size:17px; }}
    .sub, .stats {{ font-size:11.5px; }}
    summary {{ gap:9px; padding:12px 12px; flex-wrap:wrap; }}
    .iname {{ font-size:13.5px; flex-basis:calc(100% - 34px); }}
    .figs {{ flex-basis:100%; text-align:left; padding-left:34px;
      display:flex; align-items:baseline; gap:9px; }}
    .big {{ font-size:19px; }}
    table.stocks td {{ padding:7px 6px; font-size:12px; }}
    td.mc {{ display:none; }}
    td.tags {{ width:auto; }}
  }}
  @media (prefers-reduced-motion:reduce) {{ * {{ animation:none !important; transition:none !important; }} }}
</style></head><body><div class="wrap">

<h1>Capital Flow Map — {d["window"]}</h1>
<p class="sub">Money moved <b style="color:var(--red)">out of</b> the left,
   <b style="color:var(--green)">into</b> the right. Ranked by return relative to CNX500.</p>
<p class="stats">{stamp} · <b>{d["universe_size"]}</b> stocks ·
   <b>{d["industry_count"]}</b> industries · benchmark <b>{d["benchmark"]:+.2f}%</b>
   ({html.escape(d["benchmark_label"])}) · {d["weighting"]}-weighted</p>
{nav}

<div class="grid">
  <div>
    <div class="head out"><span class="dot"></span>
      <span>MONEY FLOWING OUT<small>Lagging the index — investors rotating away</small></span></div>
    {outflow}
  </div>

  <div class="spine"><i></i><i></i><i></i><span>CAPITAL ROTATES</span><i></i><i></i><i></i></div>

  <div>
    <div class="head in"><span class="dot"></span>
      <span>MONEY FLOWING IN<small>Leading the index — investors rotating toward</small></span></div>
    {inflow}
  </div>
</div>

<footer>
  ★ = beat its own industry <i>and</i> the CNX500 · turnover × compares 30-day traded value
  to its 90-day baseline · ▲▼ = rank change since the last run<br>
  Relative performance, not measured fund flows. Not investment advice.
</footer>
</div></body></html>"""
