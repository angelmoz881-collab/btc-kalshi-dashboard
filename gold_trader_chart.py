import json
import math

import numpy as np
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components


def _safe_float(value):
    try:
        x = float(value)
        return x if np.isfinite(x) else None
    except (TypeError, ValueError):
        return None


def _unix_seconds(value):
    try:
        ts = pd.to_datetime(value, utc=True)
        if pd.isna(ts):
            return None
        return int(ts.timestamp())
    except Exception:
        return None


def render_gold_expiry_timer(expiry, ticker="gold"):
    """Browser-clocked Kalshi countdown that does not depend on Streamlit rerun cadence."""
    expiry_ts = _unix_seconds(expiry)
    payload = json.dumps({"expiry": expiry_ts, "ticker": str(ticker or "gold")})
    html = r"""<!doctype html><html><head>
    <meta name="viewport" content="width=device-width,initial-scale=1" />
    <style>
    *{box-sizing:border-box}html,body{margin:0;background:transparent;color:#edf5ff;font-family:system-ui,sans-serif}
    .metric{min-height:88px;border:1px solid rgba(212,175,55,.2);border-radius:14px;padding:12px 14px;
      background:linear-gradient(145deg,rgba(31,34,44,.95),rgba(17,19,27,.97));display:flex;flex-direction:column;justify-content:center}
    .label{color:#aeb8ca;font-size:13px;line-height:1.2}.value{font-size:28px;font-weight:800;letter-spacing:-.035em;line-height:1.12;margin-top:4px}
    .sub{color:#8d99aa;font-size:10px;margin-top:3px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
    @media(max-width:650px){.metric{min-height:68px;padding:8px 9px;border-radius:10px}.label{font-size:11px}.value{font-size:19px}.sub{font-size:8px}}
    </style></head><body><div class="metric"><div class="label">Time left</div><div class="value" id="count">--:--</div><div class="sub" id="sub">browser clock · refresh-safe</div></div>
    <script>
    const d=__PAYLOAD__;
    const count=document.getElementById('count');
    const sub=document.getElementById('sub');
    function formatLeft(total){
      total=Math.max(0,Math.floor(total));
      const h=Math.floor(total/3600),m=Math.floor((total%3600)/60),s=total%60;
      return h>0 ? `${h}:${String(m).padStart(2,'0')}:${String(s).padStart(2,'0')}` : `${String(m).padStart(2,'0')}:${String(s).padStart(2,'0')}`;
    }
    function tick(){
      if(!Number.isFinite(d.expiry)){count.textContent='—';sub.textContent='expiration unavailable';return;}
      const left=d.expiry-(Date.now()/1000);
      if(left<=0){count.textContent='00:00';sub.textContent='contract expired';return;}
      count.textContent=formatLeft(left);
    }
    tick();
    setInterval(tick,250);
    </script></body></html>""".replace("__PAYLOAD__", payload)
    components.html(html, height=92, scrolling=False)


def render_gold_trader_chart(candles, strike=None, current_ref=None, ticker=None, refresh_label=None):
    """Render Gold with the same HyperTradez-style Lightweight Charts UI as BTC."""
    if candles is None or candles.empty:
        st.info("No Gold candle data available yet.")
        return

    chart = candles.tail(180).copy()
    chart["time"] = pd.to_datetime(chart["time"], utc=True, errors="coerce")
    for col in ("open", "high", "low", "close"):
        chart[col] = pd.to_numeric(chart[col], errors="coerce")
    chart = chart.dropna(subset=["time", "open", "high", "low", "close"])
    chart = chart.sort_values("time").drop_duplicates("time", keep="last")
    if len(chart) < 2:
        st.error("At least two distinct Gold candles are required to draw the chart.")
        return

    bars = []
    for row in chart.itertuples(index=False):
        ts = _unix_seconds(row.time)
        if ts is None:
            continue
        bars.append({
            "time": ts,
            "open": float(row.open),
            "high": float(row.high),
            "low": float(row.low),
            "close": float(row.close),
        })
    bars = sorted({b["time"]: b for b in bars}.values(), key=lambda b: b["time"])
    if len(bars) < 2:
        st.error("At least two distinct Gold candles are required to draw the chart.")
        return

    closes = pd.Series([b["close"] for b in bars], dtype="float64")
    overlays = []
    for span, color in ((5, "#fbbf24"), (15, "#a78bfa")):
        avg = closes.ewm(span=span, adjust=False).mean()
        overlays.append({
            "color": color,
            "points": [{"time": b["time"], "value": float(v)} for b, v in zip(bars, avg)],
        })

    strike_value = _safe_float(strike)
    current_value = _safe_float(current_ref)
    payload = json.dumps({
        "bars": bars,
        "overlays": overlays,
        "visible": min(60, len(bars)),
        "strike": strike_value,
        "reference": current_value,
        "ticker": str(ticker or "KXGOLD15M"),
    }, allow_nan=False)

    st.markdown("### Gold / Kalshi live")
    chart_html = r"""<!doctype html><html><head>
    <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1" />
    <style>
    html,body{margin:0;background:#0b0b11;color:#d9e3f1;font-family:system-ui;overflow:hidden}
    #frame{position:relative;width:100%;height:300px;overflow:hidden}
    #chart{width:100%;height:300px;touch-action:none;overscroll-behavior:contain}
    #status{position:absolute;top:9px;left:12px;pointer-events:none;background:#120e16d9;
      border:1px solid #56303a;border-radius:8px;padding:6px 9px;font-size:12px;z-index:2}
    #reset-view{position:absolute;top:9px;right:70px;z-index:3;background:#211925;color:#d9e3f1;border:1px solid #56303a;border-radius:6px;padding:5px 8px;cursor:pointer}
    #error{color:#ff9eaa;padding:15px;display:none}
    </style></head><body>
    <div id="frame"><button id="reset-view" type="button">Reset view</button><div id="status">GC=F GOLD · 1M · __TICKER__</div><div id="chart"></div><div id="error"></div></div>
    <script src="https://cdn.jsdelivr.net/npm/lightweight-charts@4.2.3/dist/lightweight-charts.standalone.production.js"></script>
    <script>
    const data=__PAYLOAD__;
    const root=document.getElementById('chart');
    const error=document.getElementById('error');
    try {
      if(!window.LightweightCharts) throw new Error('Chart library unavailable.');
      const LC=window.LightweightCharts;
      const chart=LC.createChart(root,{
        width:root.clientWidth,height:300,
        layout:{background:{type:'solid',color:'#0b0b11'},textColor:'#b9c9df'},
        grid:{vertLines:{color:'#251c27'},horzLines:{color:'#251c27'}},
        rightPriceScale:{borderColor:'#51303b',scaleMargins:{top:.08,bottom:.12}},
        timeScale:{timeVisible:true,secondsVisible:false,borderColor:'#51303b',barSpacing:8,minBarSpacing:2,rightOffset:3,lockVisibleTimeRangeOnResize:true},
        crosshair:{mode:LC.CrosshairMode.Magnet},
        handleScroll:{mouseWheel:false,pressedMouseMove:true,horzTouchDrag:false,vertTouchDrag:false},
        handleScale:{axisPressedMouseMove:false,mouseWheel:false,pinch:true},
        kineticScroll:{touch:true,mouse:false}
      });
      const main=chart.addCandlestickSeries({upColor:'#34d399',downColor:'#fb7185',borderVisible:false,wickUpColor:'#34d399',wickDownColor:'#fb7185'});
      main.setData(data.bars);

      if(Number.isFinite(data.strike)){
        main.createPriceLine({price:data.strike,color:'#ff3b5c',lineWidth:2,lineStyle:LC.LineStyle.Dashed,axisLabelVisible:true,title:'STRIKE'});
      }
      if(Number.isFinite(data.reference)){
        main.createPriceLine({price:data.reference,color:'#60a5fa',lineWidth:1,lineStyle:LC.LineStyle.Dotted,axisLabelVisible:true,title:'PYTH XAU'});
      }
      data.overlays.forEach(o=>{
        const s=chart.addLineSeries({color:o.color,lineWidth:1,lastValueVisible:false,priceLineVisible:false});
        s.setData(o.points);
      });

      const viewKey='gold-kalshi-view-1m';
      let savedView=null;
      try{savedView=JSON.parse(localStorage.getItem(viewKey)||'null');}catch(_){}
      let viewReady=false;
      const validView=v=>v&&Number.isFinite(v.span)&&v.span>0&&Number.isFinite(v.rightOffset);
      function defaultView(){
        const n=data.bars.length;
        const visible=Math.min(n,Math.max(3,data.visible));
        chart.timeScale().setVisibleLogicalRange({from:n-visible-1,to:n+2});
      }
      function saveView(r){
        if(!viewReady||!r||!Number.isFinite(r.from)||!Number.isFinite(r.to)||r.to<=r.from)return;
        const anchorIndex=Math.max(0,Math.min(data.bars.length-1,Math.floor(r.to)));
        try{
          localStorage.setItem(viewKey,JSON.stringify({
            span:r.to-r.from,rightOffset:(data.bars.length-1)-r.to,
            anchorTime:data.bars[anchorIndex].time,anchorOffset:r.to-anchorIndex,
            followLatest:r.to>=data.bars.length-1
          }));
        }catch(_){}
      }
      function setInitialView(){
        if(validView(savedView)){
          let to=(data.bars.length-1)-savedView.rightOffset;
          if(savedView.followLatest===false&&Number.isFinite(savedView.anchorTime)&&Number.isFinite(savedView.anchorOffset)){
            const index=data.bars.findIndex(b=>b.time===savedView.anchorTime);
            if(index>=0)to=index+savedView.anchorOffset;
          }
          chart.timeScale().setVisibleLogicalRange({from:to-savedView.span,to});
        }else{defaultView();}
        requestAnimationFrame(()=>{viewReady=true;chart.timeScale().subscribeVisibleLogicalRangeChange(saveView);});
      }
      requestAnimationFrame(()=>requestAnimationFrame(setInitialView));
      document.getElementById('reset-view').addEventListener('click',()=>{
        if(!viewReady)return;
        defaultView();
        saveView(chart.timeScale().getVisibleLogicalRange());
      });
      window.addEventListener('pagehide',()=>saveView(chart.timeScale().getVisibleLogicalRange()));
      new ResizeObserver(()=>{if(root.clientWidth>0)chart.applyOptions({width:root.clientWidth});}).observe(root);

      let panStartX=null;
      let panStartRange=null;
      root.addEventListener('touchstart',e=>{
        if(e.touches.length===1){
          panStartX=e.touches[0].clientX;
          const r=chart.timeScale().getVisibleLogicalRange();
          panStartRange=r?{from:r.from,to:r.to}:null;
        }else{panStartX=null;panStartRange=null;}
      },{passive:true});
      root.addEventListener('touchmove',e=>{
        if(e.touches.length!==1||panStartX===null||!panStartRange)return;
        e.preventDefault();
        const dx=e.touches[0].clientX-panStartX;
        const barsVisible=Math.max(1,panStartRange.to-panStartRange.from);
        const pxPerBar=Math.max(2,root.clientWidth/barsVisible);
        const shift=-dx/pxPerBar;
        chart.timeScale().setVisibleLogicalRange({from:panStartRange.from+shift,to:panStartRange.to+shift});
      },{passive:false});
      root.addEventListener('touchend',e=>{if(e.touches.length===0){panStartX=null;panStartRange=null;}},{passive:true});
      root.addEventListener('touchcancel',()=>{panStartX=null;panStartRange=null;},{passive:true});
      root.addEventListener('contextmenu',e=>e.preventDefault());
    }catch(e){error.style.display='block';error.textContent='Chart error: '+e.message;}
    </script></body></html>"""
    chart_html = chart_html.replace("__PAYLOAD__", payload).replace("__TICKER__", str(ticker or "KXGOLD15M"))
    components.html(chart_html, height=308, scrolling=False)

    latest_close = float(bars[-1]["close"])
    if strike_value is not None:
        side = "ABOVE" if latest_close >= strike_value else "BELOW"
        ref_text = ""
        if current_value is not None:
            ref_side = "ABOVE" if current_value >= strike_value else "BELOW"
            ref_text = f" · Pyth {ref_side} ${abs(current_value-strike_value):,.2f}"
        refresh_text = f" · ⚡ {str(refresh_label).replace(' · ', ' ')}" if refresh_label else ""
        st.caption(
            f"🔴 Strike ${strike_value:,.2f} · GC=F {side} ${abs(latest_close-strike_value):,.2f}{ref_text}{refresh_text} · 👆 Drag · 🤏 Pinch"
        )
    else:
        refresh_text = f" · ⚡ {str(refresh_label).replace(' · ', ' ')}" if refresh_label else ""
        st.caption(f"GC=F 1m proxy · EMA 5/15{refresh_text} · 👆 Drag · 🤏 Pinch zoom · Strike unavailable")

    st.caption(
        "Gold now uses the same HyperTradez-style Lightweight Charts renderer as BTC. "
        "GC=F supplies the candle proxy; Pyth XAU/USD remains the settlement-reference line when available."
    )
