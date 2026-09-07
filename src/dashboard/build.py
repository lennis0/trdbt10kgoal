"""Baut ein eigenstaendiges HTML-Dashboard aus einem Backtest.

Liest nur Kursdaten und Trades - keine Trading-Logik. Ausgabe ist eine einzelne
HTML-Datei, die man per Doppelklick oeffnet.

Chart: TradingView Lightweight Charts (Apache-2.0), fest eingebettet unter
src/dashboard/vendor/. Bewusst kein CDN: die Datei funktioniert damit offline,
in fuenf Jahren noch, und kann nicht durch ein CDN-Update kaputtgehen. Kostet
160 KB pro Dashboard - bei Dateien von ~1 MB irrelevant.

Die Lizenz verlangt eine Attribution mit Link auf tradingview.com - dafuer ist
die Chart-Option `attributionLogo: true` gesetzt. Nicht entfernen.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from src.backtest.engine import metrics, run_backtest
from src.core import Side
from src.data.klines import fetch_klines
from src.strategies.base import Strategy
from src.utils.config import load_config

OUT_DIR = Path(__file__).resolve().parents[2] / "dashboard"
VENDOR = Path(__file__).resolve().parent / "vendor" / "lightweight-charts.standalone.production.js"


def _ts(index) -> list[int]:
    return [int(t.timestamp()) for t in index]


def build(
    symbol: str,
    timeframe: str,
    strategy: Strategy,
    portfolio: str,
    overlays: dict[str, str],
    start: str = "2024-01-01",
    max_bars: int = 6000,
) -> Path:
    cfg = load_config()
    df = fetch_klines(symbol, timeframe, start)
    broker = run_backtest(df, strategy, cfg, symbol, portfolio)
    stats = metrics(broker)

    data = strategy.prepare(df).tail(max_bars)
    t = _ts(data.index)

    candles = [
        {"time": t[i], "open": float(r.open), "high": float(r.high),
         "low": float(r.low), "close": float(r.close)}
        for i, r in enumerate(data.itertuples())
    ]

    lines = {}
    for col, label in overlays.items():
        if col in data.columns:
            series = data[col]
            lines[label] = [
                {"time": t[i], "value": round(float(v), 2)}
                for i, v in enumerate(series) if pd.notna(v)
            ]

    first = data.index[0]
    markers, equity = [], []
    for tr in broker.closed_trades:
        if tr.entry_time < first:
            continue
        long = tr.side is Side.LONG
        markers.append({
            "time": int(tr.entry_time.timestamp()),
            "position": "belowBar" if long else "aboveBar",
            "color": "#3b82f6" if long else "#a855f7",
            "shape": "arrowUp" if long else "arrowDown",
        })
        won = (tr.pnl or 0) > 0
        markers.append({
            "time": int(tr.exit_time.timestamp()),
            "position": "aboveBar" if long else "belowBar",
            "color": "#16a34a" if won else "#dc2626",
            "shape": "circle",
            "text": f"{tr.r_multiple:+.1f}R",
        })
    markers.sort(key=lambda m: m["time"])

    seen = set()
    if broker.equity_curve:
        equity.append({"time": int(data.index[0].timestamp()),
                       "value": round(broker.start_equity, 2)})
        seen.add(int(data.index[0].timestamp()))
    for ts, eq in broker.equity_curve:
        sec = int(ts.timestamp())
        if sec in seen:
            continue
        seen.add(sec)
        equity.append({"time": sec, "value": round(eq, 2)})

    payload = {
        "symbol": symbol, "timeframe": timeframe, "strategy": strategy.name,
        "stats": stats, "candles": candles, "lines": lines,
        "markers": markers, "equity": equity,
    }

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    if not VENDOR.exists():
        raise FileNotFoundError(
            f"Chart-Bibliothek fehlt: {VENDOR}\n"
            "Holen mit: npm pack lightweight-charts@4.2.3 und "
            "dist/lightweight-charts.standalone.production.js dorthin kopieren."
        )

    html = (TEMPLATE
            .replace("__LIB__", VENDOR.read_text(encoding="utf-8"))
            .replace("__DATA__", json.dumps(payload)))
    path = OUT_DIR / f"{symbol}_{timeframe}_{strategy.name}.html"
    path.write_text(html, encoding="utf-8")
    return path


TEMPLATE = r"""<!doctype html>
<html lang="de"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>TradingBot Dashboard</title>
<script>__LIB__</script>
<style>
  :root{--bg:#0f1117;--panel:#171a21;--line:#262a33;--text:#e6e8ec;--dim:#8b91a0;
        --pos:#16a34a;--neg:#dc2626}
  *{box-sizing:border-box}
  body{margin:0;background:var(--bg);color:var(--text);
       font:14px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif}
  header{padding:16px 20px;border-bottom:1px solid var(--line);display:flex;
         align-items:baseline;gap:12px;flex-wrap:wrap}
  h1{font-size:17px;margin:0;font-weight:600}
  .sub{color:var(--dim);font-size:13px}
  .stats{display:flex;gap:10px;padding:14px 20px;flex-wrap:wrap}
  .stat{background:var(--panel);border:1px solid var(--line);border-radius:8px;
        padding:9px 14px;min-width:96px}
  .stat .k{color:var(--dim);font-size:11px;text-transform:uppercase;letter-spacing:.4px}
  .stat .v{font-size:17px;font-weight:600;font-variant-numeric:tabular-nums}
  .pos{color:var(--pos)} .neg{color:var(--neg)}
  .wrap{padding:0 20px 20px}
  .label{color:var(--dim);font-size:12px;margin:14px 0 6px}
  #chart,#eq{border:1px solid var(--line);border-radius:8px;overflow:hidden}
</style></head><body>
<header>
  <h1 id="title"></h1><span class="sub" id="subtitle"></span>
</header>
<div class="stats" id="stats"></div>
<div class="wrap">
  <div class="label">Kurs, Indikatoren und Trades — Pfeil = Einstieg, Punkt = Ausstieg mit R-Multiple</div>
  <div id="chart" style="height:460px"></div>
  <div class="label">Equity-Kurve</div>
  <div id="eq" style="height:190px"></div>
</div>
<script>
const D = __DATA__;
document.getElementById('title').textContent = D.symbol + ' · ' + D.timeframe + ' · ' + D.strategy;
document.getElementById('subtitle').textContent = D.candles.length + ' Kerzen dargestellt';

const S = D.stats;
const cells = [
  ['Return', S.return_pct + '%', S.return_pct >= 0],
  ['Endkapital', S.equity, S.equity >= 200],
  ['Max Drawdown', S.max_drawdown_pct + '%', false],
  ['Trades', S.trades, null],
  ['Winrate', S.winrate_pct + '%', null],
  ['avg R', S.avg_r, S.avg_r >= 0],
  ['Calmar', S.calmar, S.calmar >= 0],
  ['Gebühren', S.total_fees, false],
];
document.getElementById('stats').innerHTML = cells.map(([k,v,good]) =>
  `<div class="stat"><div class="k">${k}</div><div class="v ${good===null?'':good?'pos':'neg'}">${v}</div></div>`
).join('');

const base = {
  layout:{background:{color:'#0f1117'},textColor:'#8b91a0',attributionLogo:true},
  grid:{vertLines:{color:'#1c1f27'},horzLines:{color:'#1c1f27'}},
  rightPriceScale:{borderColor:'#262a33'},
  // minBarSpacing runtersetzen: der Standard (0.5 px pro Kerze) verhindert, dass
  // fitContent tausende Kerzen ueberhaupt ins Fenster bekommt - der Chart zeigt
  // dann stillschweigend nur den letzten Teil der Daten.
  timeScale:{borderColor:'#262a33',timeVisible:true,minBarSpacing:0.04},
  crosshair:{mode:0}
};

const chart = LightweightCharts.createChart(document.getElementById('chart'), base);
const candles = chart.addCandlestickSeries({
  upColor:'#16a34a',downColor:'#dc2626',borderVisible:false,
  wickUpColor:'#16a34a',wickDownColor:'#dc2626'
});
candles.setData(D.candles);
candles.setMarkers(D.markers);

const colors = ['#eab308','#38bdf8','#f472b6','#a3e635'];
Object.entries(D.lines).forEach(([name, data], i) => {
  const s = chart.addLineSeries({color:colors[i%colors.length],lineWidth:1,
    priceLineVisible:false,lastValueVisible:false,title:name});
  s.setData(data);
});

const eq = LightweightCharts.createChart(document.getElementById('eq'), base);
const eqSeries = eq.addAreaSeries({lineColor:'#38bdf8',topColor:'rgba(56,189,248,.28)',
  bottomColor:'rgba(56,189,248,0)',lineWidth:2});
eqSeries.setData(D.equity);

// Beide Charts auf derselben Zeitachse halten.
// WICHTIG: ueber die Zeit synchronisieren, nicht ueber logische Indizes. Der
// Kurschart hat tausende Kerzen, die Equity-Kurve nur ~100 Punkte - ein
// logischer Bereich bedeutet in beiden etwas voellig anderes und quetscht die
// Equity-Kurve auf einen unsichtbaren Ausschnitt zusammen.
let syncing = false;
const sync = (from, to) => from.timeScale().subscribeVisibleTimeRangeChange(r => {
  if (!r || syncing) return;
  syncing = true;
  try { to.timeScale().setVisibleRange(r); } catch (e) {}
  syncing = false;
});
chart.timeScale().fitContent();
eq.timeScale().fitContent();
// Sync erst NACH fitContent verdrahten, sonst zieht der erste Sync-Durchlauf
// beide Charts auf einen zufaelligen Ausschnitt.
setTimeout(() => { sync(chart, eq); sync(eq, chart); }, 0);
new ResizeObserver(() => {
  chart.applyOptions({width:document.getElementById('chart').clientWidth});
  eq.applyOptions({width:document.getElementById('eq').clientWidth});
}).observe(document.body);
chart.applyOptions({width:document.getElementById('chart').clientWidth});
eq.applyOptions({width:document.getElementById('eq').clientWidth});
</script></body></html>
"""
