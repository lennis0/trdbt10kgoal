"""Live-Dashboard: zeigt, was der Paper-Bot gerade macht.

Liest den Zustand aus state/paper_state.json und die aktuellen Kurse, und baut
daraus eine eigenstaendige HTML-Datei. Keine Trading-Logik, nur Anzeige.

Aufruf:  python build_live_dashboard.py
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from src.data.klines import fetch_klines
from src.paper import state as state_mod
from src.paper.runner import SETUP, SYMBOL, TRADES_PER_YEAR
from src.strategies.reversion import ReversionStrategy
from src.strategies.trend import TrendStrategy
from src.utils.config import load_config

OUT = Path(__file__).resolve().parents[2] / "dashboard" / "live.html"
VENDOR = Path(__file__).resolve().parent / "vendor" / "lightweight-charts.standalone.production.js"

BOT_INFO = {
    "trend_ema": {
        "titel": "Bot A · Trendfolge",
        "idee": "EMA 21 kreuzt EMA 55 — handelt nur in klaren Trends (ADX ≥ 30)",
        "charakter": "10% Winrate, Gewinn aus wenigen grossen Bewegungen",
        "pro_jahr": 47,
        "overlays": {"ema_fast": "EMA 21", "ema_slow": "EMA 55"},
    },
    "reversion_bb": {
        "titel": "Bot B · Mean-Reversion",
        "idee": "Rückkehr ins Bollinger-Band + RSI — nur in Seitwärtsphasen (ADX ≤ 25)",
        "charakter": "54% Winrate, viele kleine Gewinne",
        "pro_jahr": 38,
        "overlays": {"bb_lower": "BB unten", "bb_mid": "BB Mitte", "bb_upper": "BB oben"},
    },
}


def _series(data: pd.DataFrame, column: str) -> list[dict]:
    if column not in data.columns:
        return []
    return [{"time": int(ts.timestamp()), "value": round(float(v), 2)}
            for ts, v in data[column].items() if pd.notna(v)]


def build() -> Path:
    config = load_config()
    state = state_mod.load()
    now = datetime.now(timezone.utc)

    bots = []
    for name, cls, timeframe in SETUP:
        strategy = cls()
        info = BOT_INFO[name]
        df = fetch_klines(SYMBOL, timeframe, _start(timeframe), use_cache=False)
        data = strategy.prepare(df).tail(500)

        open_here = [t for t in state.get("open_trades", []) if t.strategy == name]
        closed_here = [t for t in state.get("closed_trades", []) if t.strategy == name]

        markers = []
        for t in open_here + closed_here:
            long = t.side.value == "long"
            markers.append({
                "time": int(t.entry_time.timestamp()),
                "position": "belowBar" if long else "aboveBar",
                "color": "#3b82f6" if long else "#a855f7",
                "shape": "arrowUp" if long else "arrowDown",
                "text": "Einstieg",
            })
            if t.exit_time:
                markers.append({
                    "time": int(t.exit_time.timestamp()),
                    "position": "aboveBar" if long else "belowBar",
                    "color": "#16a34a" if (t.pnl or 0) > 0 else "#dc2626",
                    "shape": "circle",
                    "text": f"{t.r_multiple:+.1f}R",
                })
        markers.sort(key=lambda m: m["time"])

        last_iso = state.get("last_candle", {}).get(timeframe)
        age = (now - datetime.fromisoformat(last_iso)).total_seconds() / 60 if last_iso else None
        grenze = {"15m": 45, "1h": 150, "4h": 600}.get(timeframe, 600)

        bots.append({
            "name": name,
            "titel": info["titel"],
            "idee": info["idee"],
            "charakter": info["charakter"],
            "timeframe": timeframe,
            "pro_jahr": info["pro_jahr"],
            "trades": len(closed_here),
            "offen": [{
                "seite": t.side.value, "entry": round(t.entry_price, 2),
                "stop": round(t.stop, 2), "size": t.size,
                "seit": t.entry_time.isoformat(),
                "risiko": round(abs(t.entry_price - t.stop) * t.size, 2),
            } for t in open_here],
            "candles": [{"time": int(ts.timestamp()), "open": float(r.open),
                         "high": float(r.high), "low": float(r.low), "close": float(r.close)}
                        for ts, r in zip(data.index, data.itertuples())],
            "lines": {label: _series(data, col) for col, label in info["overlays"].items()},
            "markers": markers,
            "kerze_alter_min": round(age) if age is not None else None,
            "frisch": age is not None and age < grenze,
            "kurs": round(float(data["close"].iloc[-1]), 2),
        })

    started = state.get("started_at")
    tage = (now - datetime.fromisoformat(started)).total_seconds() / 86400 if started else 0
    updated = state.get("updated_at")
    lauf_alter = (now - datetime.fromisoformat(updated)).total_seconds() / 60 if updated else None

    payload = {
        "symbol": SYMBOL,
        "equity": state.get("equity") or 200,
        "start_equity": 200,
        "tage": round(tage, 1),
        "trades_gesamt": len(state.get("closed_trades", [])),
        "erwartet": round(TRADES_PER_YEAR * tage / 365, 1),
        "lauf_alter_min": round(lauf_alter) if lauf_alter is not None else None,
        "gebaut": now.strftime("%d.%m.%Y %H:%M UTC"),
        "risiko": {
            "pro_trade": config.risk.base_risk_pct,
            "max_hebel": config.risk.max_leverage,
            "kill": config.risk.daily_loss_kill_pct,
            "fee": config.costs.taker_fee,
        },
        "bots": bots,
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        TEMPLATE.replace("__LIB__", VENDOR.read_text(encoding="utf-8"))
                .replace("__DATA__", json.dumps(payload)),
        encoding="utf-8")
    return OUT


def _start(timeframe: str) -> str:
    minutes = {"15m": 15, "1h": 60, "4h": 240}[timeframe]
    days = max(int(500 * minutes / 1440) + 2, 7)
    return (pd.Timestamp.now("UTC") - pd.Timedelta(days=days)).strftime("%Y-%m-%d")


TEMPLATE = r"""<!doctype html>
<html lang="de"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>TradingBot Live</title>
<script>__LIB__</script>
<style>
  :root{--bg:#0f1117;--panel:#171a21;--line:#262a33;--text:#e6e8ec;--dim:#8b91a0;
        --pos:#16a34a;--neg:#dc2626;--warn:#eab308;--accent:#38bdf8}
  *{box-sizing:border-box}
  body{margin:0;background:var(--bg);color:var(--text);
       font:14px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif}
  .wrap{max-width:1200px;margin:0 auto;padding:22px}
  header{display:flex;align-items:baseline;gap:12px;flex-wrap:wrap;margin-bottom:4px}
  h1{font-size:19px;margin:0;font-weight:600}
  h2{font-size:15px;margin:0;font-weight:600}
  .dim{color:var(--dim);font-size:13px}
  .stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));
         gap:10px;margin:16px 0 26px}
  .stat{background:var(--panel);border:1px solid var(--line);border-radius:9px;padding:11px 14px}
  .stat .k{color:var(--dim);font-size:11px;text-transform:uppercase;letter-spacing:.5px}
  .stat .v{font-size:19px;font-weight:600;font-variant-numeric:tabular-nums;margin-top:2px}
  .pos{color:var(--pos)} .neg{color:var(--neg)} .warn{color:var(--warn)}
  .bot{background:var(--panel);border:1px solid var(--line);border-radius:11px;
       padding:17px;margin-bottom:20px}
  .bothead{display:flex;justify-content:space-between;align-items:flex-start;
           gap:14px;flex-wrap:wrap;margin-bottom:6px}
  .badge{font-size:11px;padding:3px 9px;border-radius:99px;border:1px solid var(--line);
         color:var(--dim);white-space:nowrap}
  .badge.ok{color:var(--pos);border-color:rgba(22,163,74,.45)}
  .badge.bad{color:var(--neg);border-color:rgba(220,38,38,.45)}
  .idee{color:var(--dim);font-size:13px;margin:2px 0 12px}
  .pos-box{background:rgba(56,189,248,.07);border:1px solid rgba(56,189,248,.28);
           border-radius:8px;padding:10px 13px;margin-bottom:12px;font-size:13px}
  .pos-box b{font-variant-numeric:tabular-nums}
  .flat{color:var(--dim);font-size:13px;margin-bottom:12px}
  .chart{height:300px;border:1px solid var(--line);border-radius:8px;overflow:hidden}
  footer{color:var(--dim);font-size:12px;margin-top:26px;border-top:1px solid var(--line);
         padding-top:14px}
  code{background:var(--panel);padding:2px 6px;border-radius:4px;font-size:12px}
</style></head><body><div class="wrap">
<header><h1 id="title"></h1><span class="dim" id="sub"></span></header>
<div class="stats" id="stats"></div>
<div id="bots"></div>
<footer id="foot"></footer>
</div>
<script>
const D = __DATA__;
document.getElementById('title').textContent = 'TradingBot Live · ' + D.symbol;
document.getElementById('sub').textContent =
  `läuft seit ${D.tage} Tagen · gebaut ${D.gebaut}`;

const pnl = D.equity / D.start_equity - 1;
const alive = D.lauf_alter_min !== null && D.lauf_alter_min < 60;
const cells = [
  ['Equity', D.equity.toFixed(2) + ' CHF', pnl >= 0 ? 'pos' : 'neg'],
  ['Ergebnis', (pnl * 100).toFixed(2) + '%', pnl >= 0 ? 'pos' : 'neg'],
  ['Trades', D.trades_gesamt, ''],
  ['erwartet bisher', '~' + D.erwartet, ''],
  ['Risiko/Trade', (D.risiko.pro_trade * 100).toFixed(0) + '%', ''],
  ['Letzter Lauf', D.lauf_alter_min === null ? '–' : D.lauf_alter_min + ' min',
   alive ? 'pos' : 'warn'],
];
document.getElementById('stats').innerHTML = cells.map(([k, v, cls]) =>
  `<div class="stat"><div class="k">${k}</div><div class="v ${cls}">${v}</div></div>`).join('');

const fmt = n => n.toLocaleString('de-CH', {minimumFractionDigits: 2, maximumFractionDigits: 2});

document.getElementById('bots').innerHTML = D.bots.map((b, i) => {
  const offen = b.offen.map(p => {
    const dist = Math.abs(p.entry - p.stop) / p.entry * 100;
    return `<div class="pos-box">Offene Position · <b>${p.seite === 'long' ? 'Long' : 'Short'}</b>
      seit ${new Date(p.seit).toLocaleString('de-CH')}<br>
      Einstieg <b>${fmt(p.entry)}</b> · Stop <b>${fmt(p.stop)}</b> (${dist.toFixed(2)}% entfernt)
      · Risiko <b>${fmt(p.risiko)} CHF</b></div>`;
  }).join('') || '<div class="flat">Keine offene Position — wartet auf ein Signal.</div>';

  const frisch = b.frisch
    ? `<span class="badge ok">Daten frisch · ${b.kerze_alter_min} min</span>`
    : `<span class="badge bad">Daten alt · ${b.kerze_alter_min} min</span>`;

  return `<div class="bot">
    <div class="bothead">
      <div><h2>${b.titel}</h2><div class="idee">${b.idee}</div></div>
      <div style="display:flex;gap:6px;flex-wrap:wrap">
        <span class="badge">${b.timeframe}</span>
        <span class="badge">~${b.pro_jahr} Trades/Jahr</span>
        ${frisch}
      </div>
    </div>
    <div class="idee" style="margin-top:-6px">${b.charakter} · Kurs ${fmt(b.kurs)}</div>
    ${offen}
    <div class="chart" id="c${i}"></div>
  </div>`;
}).join('');

const base = {
  layout:{background:{color:'#171a21'},textColor:'#8b91a0',attributionLogo:true},
  grid:{vertLines:{color:'#1f232b'},horzLines:{color:'#1f232b'}},
  rightPriceScale:{borderColor:'#262a33'},
  timeScale:{borderColor:'#262a33',timeVisible:true,minBarSpacing:0.04},
  crosshair:{mode:0}
};
const colors = ['#eab308','#38bdf8','#f472b6','#a3e635'];

D.bots.forEach((b, i) => {
  const el = document.getElementById('c' + i);
  const chart = LightweightCharts.createChart(el, base);
  const candles = chart.addCandlestickSeries({
    upColor:'#16a34a',downColor:'#dc2626',borderVisible:false,
    wickUpColor:'#16a34a',wickDownColor:'#dc2626'});
  candles.setData(b.candles);
  if (b.markers.length) candles.setMarkers(b.markers);

  Object.entries(b.lines).forEach(([name, data], k) => {
    if (!data.length) return;
    const s = chart.addLineSeries({color:colors[k % colors.length],lineWidth:1,
      priceLineVisible:false,lastValueVisible:false,title:name});
    s.setData(data);
  });

  // Offene Position als waagrechte Linien: Einstieg und Stop
  b.offen.forEach(p => {
    candles.createPriceLine({price:p.entry,color:'#38bdf8',lineWidth:1,
      lineStyle:2,axisLabelVisible:true,title:'Einstieg'});
    candles.createPriceLine({price:p.stop,color:'#dc2626',lineWidth:1,
      lineStyle:2,axisLabelVisible:true,title:'Stop'});
  });

  const fit = () => { chart.applyOptions({width: el.clientWidth}); chart.timeScale().fitContent(); };
  new ResizeObserver(fit).observe(el);
  fit();
});

document.getElementById('foot').innerHTML =
  `Papier-Handel mit echten Kursen — kein echtes Geld. Startkapital ${D.start_equity} CHF, ` +
  `${(D.risiko.pro_trade * 100).toFixed(0)}% Risiko pro Trade, max ${D.risiko.max_hebel}x Hebel, ` +
  `Kill-Switch bei −${(D.risiko.kill * 100).toFixed(0)}% am Tag, ` +
  `${(D.risiko.fee * 100).toFixed(3)}% Gebühren je Seite.<br>` +
  `Momentaufnahme — neu bauen mit <code>python build_live_dashboard.py</code>`;
</script></body></html>
"""
