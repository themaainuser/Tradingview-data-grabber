import pandas as pd
import numpy as np
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import argparse
import re
import os

import matplotlib
matplotlib.use("Agg")

plt.rcParams["figure.dpi"] = 110

GREEN = "#26a69a"
RED = "#ef5350"
HEAT = "YlOrRd"


def parse_time(s):
    s = re.sub(r"\s*\([^)]*\)\s*$", "", str(s).strip())
    for fmt in ("%a %b %d %Y %H:%M:%S GMT%z", "%Y/%m/%d, %H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            return pd.to_datetime(s, format=fmt)
        except (ValueError, TypeError):
            continue
    return pd.to_datetime(s, errors="coerce")


def load_csv(path):
    df = pd.read_csv(path)
    df["index"] = df["index"].astype(
        str).str.replace(r"[\[\]]", "", regex=True)
    df["dt"] = df["time"].map(parse_time)
    df = df.dropna(subset=["dt", "open", "high", "low", "close"])
    df["volume"] = pd.to_numeric(df["volume"], errors="coerce").fillna(0)
    df = df.sort_values("dt").set_index("dt")
    return df


def save(fig, outdir, name, title):
    path = os.path.join(outdir, name)
    fig.suptitle(title, fontsize=13, fontweight="bold")
    fig.tight_layout(rect=(0, 0, 1, 0.97))
    fig.savefig(path)
    plt.close(fig)
    print("saved", path)


def chart_candles(df, outdir):
    fig, (ax, axv) = plt.subplots(
        2, 1, figsize=(13, 8), sharex=True,
        gridspec_kw={"height_ratios": [3, 1]})
    x = np.arange(len(df))
    up = df["close"] >= df["open"]
    for col, m in ((GREEN, up), (RED, ~up)):
        sub = df[m]
        xi = x[m]
        ax.vlines(xi, sub["low"], sub["high"], color=col, linewidth=0.8)
        ax.bar(xi, (sub["close"] - sub["open"]).abs(),
               bottom=sub[["open", "close"]].min(axis=1),
               color=col, width=0.7, edgecolor=col)
    axv.bar(x, df["volume"], color=np.where(up, GREEN, RED), width=0.8)
    ticks = np.linspace(0, len(df) - 1, 8).astype(int)
    ax.set_xticks(ticks)
    ax.set_xticklabels([df.index[i].strftime("%m-%d %H:%M")
                       for i in ticks], rotation=30)
    ax.set_ylabel("price")
    axv.set_ylabel("volume")
    ax.grid(alpha=0.2)
    save(fig, outdir, "1_candles_volume.png", "Candles + Volume")


def chart_volume_profile(df, outdir):
    nbins = 60
    lo, hi = df["low"].min(), df["high"].max()
    edges = np.linspace(lo, hi, nbins + 1)
    mid = (edges[:-1] + edges[1:]) / 2
    prof = np.zeros(nbins)
    for r in df.itertuples():
        o, h, l, c, v = r.open, r.high, r.low, r.close, r.volume
        span = max(h - l, 1e-9)
        for i in range(nbins):
            ov = min(h, edges[i + 1]) - max(l, edges[i])
            if ov > 0:
                prof[i] += v * ov / span
    poc = mid[np.argmax(prof)]
    fig, (axh, axc) = plt.subplots(
        1, 2, figsize=(12, 7), sharey=True,
        gridspec_kw={"width_ratios": [1, 3]})
    norm = (prof - prof.min()) / max(prof.max() - prof.min(), 1e-9)
    axh.barh(mid, prof, height=edges[1] - edges[0],
             color=plt.get_cmap(HEAT)(norm), edgecolor="none")
    axh.invert_xaxis()
    axh.axhline(poc, color="blue", linewidth=1, linestyle="--", alpha=0.7)
    axh.set_ylabel("price")
    axh.set_title("Volume Profile (POC dashed)")
    axc.plot(df.index, df["close"], color="black", linewidth=1.2)
    axc.fill_between(df.index, df["low"], df["high"], alpha=0.15, color="gray")
    axc.axhline(poc, color="blue", linewidth=1, linestyle="--", alpha=0.7)
    axc.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d %H:%M"))
    axc.grid(alpha=0.2)
    save(fig, outdir, "2_volume_profile.png", "Volume Profile / Value Areas")


def time_grid(df):
    df = df.copy()
    df["hour"] = df.index.hour
    df["slot"] = (df.index.minute // 5) * 5
    return df


def chart_time_volume_heatmap(df, outdir):
    df = time_grid(df)
    piv = df.pivot_table(index="hour", columns="slot",
                         values="volume", aggfunc="sum", fill_value=0)
    fig, ax = plt.subplots(figsize=(13, 6))
    im = ax.imshow(piv, aspect="auto", cmap=HEAT, interpolation="nearest")
    ax.set_yticks(range(len(piv)))
    ax.set_yticklabels(piv.index)
    ax.set_xticks(range(len(piv.columns)))
    ax.set_xticklabels(["{:02d}".format(c)
                       for c in piv.columns], rotation=90, fontsize=7)
    ax.set_xlabel("minute-of-hour (5-min slots)")
    ax.set_ylabel("hour of day (IST)")
    fig.colorbar(im, ax=ax, label="volume")
    save(fig, outdir, "3_volume_by_time_heatmap.png",
         "When does liquidity trade? (hour x 5-min)")


def chart_volatility_heatmap(df, outdir):
    df = time_grid(df)
    df["range_pct"] = (df["high"] - df["low"]) / df["open"] * 100
    piv = df.pivot_table(index="hour", columns="slot",
                         values="range_pct", aggfunc="mean")
    fig, ax = plt.subplots(figsize=(13, 6))
    im = ax.imshow(piv, aspect="auto", cmap="RdYlGn_r",
                   interpolation="nearest")
    ax.set_yticks(range(len(piv)))
    ax.set_yticklabels(piv.index)
    ax.set_xticks(range(len(piv.columns)))
    ax.set_xticklabels(["{:02d}".format(c)
                       for c in piv.columns], rotation=90, fontsize=7)
    ax.set_xlabel("minute-of-hour (5-min slots)")
    ax.set_ylabel("hour of day (IST)")
    fig.colorbar(im, ax=ax, label="avg bar range %")
    save(fig, outdir, "4_volatility_by_time_heatmap.png",
         "Where does price move? (hour x 5-min)")


def chart_price_time_heatmap(df, outdir):
    nbins = 80
    lo, hi = df["low"].min(), df["high"].max()
    price_edges = np.linspace(lo, hi, nbins + 1)
    time_idx = np.arange(len(df))
    H, _, _ = np.histogram2d(time_idx, (df["high"] + df["low"]) / 2,
                             bins=[len(df), nbins],
                             weights=df["volume"])
    fig, ax = plt.subplots(figsize=(13, 6))
    im = ax.imshow(H.T, aspect="auto", cmap="YlOrRd", interpolation="nearest",
                   extent=[0, len(df), lo, hi])  # type: ignore
    ax.set_ylabel("price")
    ticks = np.linspace(0, len(df) - 1, 8).astype(int)
    ax.set_xticks(ticks)
    ax.set_xticklabels([df.index[i].strftime("%m-%d %H:%M")
                       for i in ticks], rotation=30)
    fig.colorbar(im, ax=ax, label="volume density")
    save(fig, outdir, "5_price_time_heatmap.png",
         "Volume density across time x price")


def chart_returns_atr(df, outdir):
    ret = df["close"].pct_change().dropna()
    tr = pd.concat([df["high"] - df["low"], (df["high"] - df["close"].shift()).abs(),
                    (df["low"] - df["close"].shift()).abs()], axis=1).max(axis=1)
    atr = tr.rolling(14).mean()
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(13, 7))
    ax1.hist(ret * 100, bins=40, color="#42a5f5", alpha=0.85)
    ax1.axvline(ret.mean() * 100, color="red", linestyle="--", label="mean")
    ax1.axvline(0, color="black", linewidth=0.8)
    ax1.set_xlabel("per-bar return %")
    ax1.legend()
    ax2.plot(df.index, atr, color="#7e57c2", linewidth=1.3)
    ax2.set_ylabel("ATR(14)")
    ax2.grid(alpha=0.2)
    save(fig, outdir, "6_returns_atr.png",
         "Return distribution + volatility (ATR)")


def chart_correlation(files, outdir):
    closes = {}
    for f in files:
        df = load_csv(f)
        name = os.path.splitext(os.path.basename(f))[0]
        closes[name] = df["close"].resample("1h").last()
    frame = pd.DataFrame(closes).dropna()
    corr = frame.pct_change().corr()
    fig, ax = plt.subplots(figsize=(9, 7))
    im = ax.imshow(corr, cmap="coolwarm", vmin=-1, vmax=1)
    ax.set_xticks(range(len(corr)))
    ax.set_yticks(range(len(corr)))
    ax.set_xticklabels(corr.columns, rotation=45, ha="right")
    ax.set_yticklabels(corr.columns)
    for i in range(len(corr)):
        for j in range(len(corr)):
            ax.text(j, i, "{:.2f}".format(
                corr.iloc[i, j]), ha="center", va="center", fontsize=9)
    fig.colorbar(im, ax=ax)
    save(fig, outdir, "7_correlation_heatmap.png",
         "Cross-symbol return correlation")


def build_html(outdir):
    from datetime import datetime as _dt
    pngs = sorted(f for f in os.listdir(outdir) if f.endswith(".png"))

    def title(p):
        return " ".join(w.capitalize() for w in p.replace(".png", "").split("_"))

    library_cards = "\n".join(
        '<div class="pool-card" draggable="true" data-src="{}">'
        '<img src="{}" alt="{}"/><span>{}</span></div>'.format(
            p, p, p, title(p))
        for p in pngs)
    slot_placeholders = "\n".join(
        '<div class="slot" data-idx="{}"><div class="slot-empty">Drag a chart here</div></div>'
        .format(i) for i in range(4))
    header = ("<header><h1>Trading Visuals Dashboard</h1>"
              "<p>{} charts &middot; generated {}</p></header>").format(
        len(pngs), _dt.now().strftime("%Y-%m-%d %H:%M:%S"))

    css = (
        "*{box-sizing:border-box;margin:0;padding:0}"
        "body{font-family:Segoe UI,Arial,sans-serif;background:#0d1117;color:#e6edf3;padding:24px}"
        "header{max-width:1400px;margin:0 auto 20px;border-bottom:1px solid #21262d;padding-bottom:14px}"
        "header h1{font-size:22px;color:#ffd54f;letter-spacing:.4px}"
        "header p{font-size:13px;color:#8b949e;margin-top:4px}"
        ".wrap{max-width:1400px;margin:0 auto}"
        "section{margin-bottom:28px}"
        "section h2{font-size:16px;color:#ffd54f;margin-bottom:12px}"
        ".slots{display:grid;grid-template-columns:repeat(2,1fr);gap:16px}"
        ".slot{min-height:340px;background:#161b22;border:2px dashed #30363d;border-radius:10px;"
        "display:flex;align-items:center;justify-content:center;position:relative;overflow:hidden;"
        "transition:border-color .15s ease,background .15s ease}"
        ".slot.drag-over{border-color:#ffd54f;background:#1c2128}"
        ".slot img{position:absolute;inset:0;width:100%;height:100%;object-fit:contain;background:#0d1117;"
        "cursor:zoom-in}"
        "body.edit .slot img{cursor:grab}"
        ".slot-empty{color:#484f58;font-size:14px;user-select:none}"
        ".slot-title{position:absolute;top:8px;left:8px;background:#0d1117cc;color:#c9d1d9;font-size:11px;"
        "padding:3px 8px;border-radius:4px;pointer-events:none}"
        ".controls{margin-top:12px;display:flex;gap:10px}"
        ".controls button{background:#21262d;color:#e6edf3;border:1px solid #30363d;border-radius:6px;"
        "padding:7px 14px;font-size:13px;cursor:pointer;transition:background .15s}"
        ".controls button:hover{background:#30363d}"
        "#btn-edit.on,#btn-refresh.on{background:#ffd54f;color:#0d1117;border-color:#ffd54f;font-weight:600}"
        "#refresh-int{background:#21262d;color:#e6edf3;border:1px solid #30363d;border-radius:6px;"
        "padding:7px 8px;font-size:13px;cursor:pointer}"
        ".pool{display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:14px}"
        ".pool-card{background:#161b22;border:1px solid #21262d;border-radius:10px;overflow:hidden;"
        "cursor:pointer;transition:transform .15s,border-color .15s}"
        "body.edit .pool-card{cursor:grab}"
        ".pool-card:hover{transform:translateY(-2px);border-color:#ffd54f55}"
        ".pool-card img{width:100%;height:110px;object-fit:cover;background:#0d1117;display:block;"
        "pointer-events:none}"
        ".pool-card span{display:block;font-size:12px;font-weight:600;padding:8px 10px;color:#c9d1d9;"
        "pointer-events:none}"
        ".pool-card.dragging{opacity:.4}"
        "@media(max-width:800px){.slots{grid-template-columns:1fr}}")

    js = (
        "(function(){"
        "var KEY='tv_dash_slots';"
        "var KEY_EDIT='tv_dash_edit';"
        "var KEY_REF='tv_dash_refresh';"
        "var KEY_INT='tv_dash_refresh_int';"
        "var slots=Array.prototype.slice.call(document.querySelectorAll('.slot'));"
        "var pool=document.querySelector('#pool');"
        "var dragSrc=null;"
        "var dragKind=null;"
        "var editBtn=document.querySelector('#btn-edit');"
        "var editOn=localStorage.getItem(KEY_EDIT)==='1';"
        "var refreshBtn=document.querySelector('#btn-refresh');"
        "var refreshInt=document.querySelector('#refresh-int');"
        "var refreshOn=localStorage.getItem(KEY_REF)==='1';"
        "var refreshMs=+(localStorage.getItem(KEY_INT)||30000);"
        "var refreshTimer=null;"
        "refreshInt.value=String(refreshMs);"
        "function bust(src){return src+(src.indexOf('?')>=0?'&':'?')+'t='+Date.now();}"
        "function setRefresh(on){"
        "  refreshOn=on;refreshBtn.classList.toggle('on',on);"
        "  refreshBtn.textContent='Auto-refresh: '+(on?'ON':'OFF');"
        "  localStorage.setItem(KEY_REF,on?'1':'0');"
        "  if(refreshTimer){clearInterval(refreshTimer);refreshTimer=null;}"
        "  if(on){refreshTimer=setInterval(function(){doRefresh();},refreshMs);}"
        "}"
        "function doRefresh(){"
        "  render();"
        "  pool.querySelectorAll('.pool-card img').forEach(function(im){"
        "    im.src=bust(im.src.split('?')[0]);});"
        "}"
        "function setEdit(on){"
        "  editOn=on;document.body.classList.toggle('edit',on);"
        "  editBtn.classList.toggle('on',on);"
        "  editBtn.textContent='Edit layout: '+(on?'ON':'OFF');"
        "  localStorage.setItem(KEY_EDIT,on?'1':'0');"
        "  render();"
        "}"
        "function openChart(src){window.open(src,'_blank');}"
        "function chartTitle(src){"
        "  var c=pool.querySelector('.pool-card[data-src=\"'+src+'\"] span');"
        "  return c?c.textContent:src;"
        "}"
        "function render(){"
        "  var sel=JSON.parse(localStorage.getItem(KEY)||'[]');"
        "  slots.forEach(function(s,i){"
        "    var src=sel[i]||null;"
        "    var img=s.querySelector('img');"
        "    var ttl=s.querySelector('.slot-title');"
        "    var empty=s.querySelector('.slot-empty');"
        "    if(img){img.remove();}if(ttl){ttl.remove();}"
        "    if(src){"
        "      if(empty){empty.remove();}"
        "      var im=document.createElement('img');im.src=bust(src);im.alt=src;"
        "      im.draggable=editOn;"
        "      im.addEventListener('dragstart',slotDragStart);"
        "      im.addEventListener('click',function(){if(!editOn){openChart(src);}});"
        "      s.appendChild(im);"
        "      var t=document.createElement('div');t.className='slot-title';t.textContent=chartTitle(src);"
        "      s.appendChild(t);"
        "    }else{"
        "      if(!empty){var e=document.createElement('div');e.className='slot-empty';"
        "        e.textContent='Drag a chart here';s.appendChild(e);}"
        "    }"
        "  });"
        "}"
        "function save(){"
        "  var sel=slots.map(function(s){var im=s.querySelector('img');return im?im.src.split('/').pop():null;});"
        "  localStorage.setItem(KEY,JSON.stringify(sel));"
        "}"
        "function poolDragStart(e){"
        "  if(!editOn){openChart(e.target.closest('.pool-card').dataset.src);return;}"
        "  dragSrc=e.target.closest('.pool-card');dragKind='pool';"
        "  dragSrc.classList.add('dragging');"
        "  e.dataTransfer.effectAllowed='copy';e.dataTransfer.setData('text/plain',dragSrc.dataset.src);}"
        "function poolDragEnd(){if(dragSrc){dragSrc.classList.remove('dragging');}dragSrc=null;dragKind=null;}"
        "function slotDragStart(e){"
        "  if(!editOn)return;var im=e.target.closest('img');if(!im)return;"
        "  dragSrc=slots.indexOf(im.parentElement);dragKind='slot';"
        "  e.dataTransfer.effectAllowed='move';e.dataTransfer.setData('text/plain',im.src.split('/').pop());}"
        "function slotDragOver(e){e.preventDefault();e.dataTransfer.dropEffect=dragKind==='slot'?'move':'copy';"
        "  e.currentTarget.classList.add('drag-over');}"
        "function slotDragLeave(e){e.currentTarget.classList.remove('drag-over');}"
        "function slotDrop(e){"
        "  e.preventDefault();var slot=e.currentTarget;slot.classList.remove('drag-over');"
        "  if(!editOn){return;}"
        "  var targetIdx=+slot.dataset.idx;"
        "  var sel=JSON.parse(localStorage.getItem(KEY)||'[]');"
        "  if(dragKind==='slot'){"
        "    var a=sel[dragSrc],b=sel[targetIdx];sel[dragSrc]=b;sel[targetIdx]=a;"
        "  }else if(dragKind==='pool'){"
        "    sel[targetIdx]=e.dataTransfer.getData('text/plain');"
        "  }else{return;}"
        "  localStorage.setItem(KEY,JSON.stringify(sel));render();"
        "  dragSrc=null;dragKind=null;"
        "}"
        "slots.forEach(function(s){"
        "  s.addEventListener('dragover',slotDragOver);"
        "  s.addEventListener('dragleave',slotDragLeave);"
        "  s.addEventListener('drop',slotDrop);"
        "});"
        "pool.querySelectorAll('.pool-card').forEach(function(c){"
        "  c.addEventListener('dragstart',poolDragStart);"
        "  c.addEventListener('dragend',poolDragEnd);"
        "});"
        "document.querySelector('#btn-edit').addEventListener('click',function(){setEdit(!editOn);});"
        "refreshBtn.addEventListener('click',function(){setRefresh(!refreshOn);});"
        "refreshInt.addEventListener('change',function(){"
        "  refreshMs=+refreshInt.value;localStorage.setItem(KEY_INT,String(refreshMs));"
        "  if(refreshOn){clearInterval(refreshTimer);"
        "    refreshTimer=setInterval(function(){doRefresh();},refreshMs);}"
        "});"
        "document.querySelector('#btn-clear').addEventListener('click',function(){"
        "  localStorage.setItem(KEY,'[null,null,null,null]');render();});"
        "document.querySelector('#btn-reset').addEventListener('click',function(){"
        "  var def=[];var cards=pool.querySelectorAll('.pool-card');"
        "  for(var i=0;i<4&&i<cards.length;i++){def.push(cards[i].dataset.src);}"
        "  localStorage.setItem(KEY,JSON.stringify(def));render();});"
        "if(!localStorage.getItem(KEY)){document.querySelector('#btn-reset').click();}"
        "setEdit(editOn);"
        "setRefresh(refreshOn);"
        "})();")

    html = (
        "<!doctype html><html><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width, initial-scale=1'>"
        "<title>Trading Visuals Dashboard</title><style>" + css + "</style></head><body>" +
        header +
        '<div class="wrap">' +
        "<section><h2>Pin 4 Charts</h2>" +
        '<div class="controls"><button id="btn-edit">Edit layout: OFF</button>'
        '<button id="btn-refresh">Auto-refresh: OFF</button>'
        '<select id="refresh-int">'
        '<option value="10000">10s</option>'
        '<option value="30000">30s</option>'
        '<option value="60000">60s</option>'
        '</select>'
        '<button id="btn-clear">Clear</button>'
        '<button id="btn-reset">Reset to default</button></div>' +
        '<div class="slots" id="slots">' + slot_placeholders + "</div></section>" +
        '<section><h2>Chart Library (click to view, enable Edit layout to pin)</h2>' +
        '<div class="pool" id="pool">' + library_cards + "</div></section>" +
        "</div><script>" + js + "</script></body></html>")
    with open(os.path.join(outdir, "dashboard.html"), "w") as f:
        f.write(html)
    print("saved", os.path.join(outdir, "dashboard.html"))


def main():
    parser = argparse.ArgumentParser(
        description="Turn captured OHLCV CSVs into charts and heatmaps")
    parser.add_argument("files", nargs="+",
                        help="captured csv files (livestreamtest.py output)")
    parser.add_argument("-o", "--outdir", default="charts",
                        help="output directory (default: charts)")
    args = parser.parse_args()
    os.makedirs(args.outdir, exist_ok=True)
    for f in args.files:
        df = load_csv(f)
        title = os.path.splitext(os.path.basename(f))[0]
        print("loaded {}: {} bars, {} - {}".format(f,
              len(df), df.index[0], df.index[-1]))
        chart_candles(df, args.outdir)
        chart_volume_profile(df, args.outdir)
        chart_time_volume_heatmap(df, args.outdir)
        chart_volatility_heatmap(df, args.outdir)
        chart_price_time_heatmap(df, args.outdir)
        chart_returns_atr(df, args.outdir)
    if len(args.files) > 1:
        chart_correlation(args.files, args.outdir)
    build_html(args.outdir)


if __name__ == "__main__":
    main()
