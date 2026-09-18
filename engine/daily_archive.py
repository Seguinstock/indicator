import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import yfinance as yf

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / 'data' / 'results.json'
ARCHIVE = ROOT / 'data' / 'daily_archive.json'
TZ = ZoneInfo('America/Toronto')


def load_json(path, default):
    try: return json.loads(path.read_text(encoding='utf-8'))
    except (FileNotFoundError, json.JSONDecodeError): return default


def market_risk(x):
    # Keep archive eligibility identical to the dashboard's marketRisk().
    try: vol=float(x.get('volatility_pct'))
    except (TypeError,ValueError): vol=None
    try: price=float(x.get('price') or x.get('close'))
    except (TypeError,ValueError): price=None
    try: rvol=float(x.get('rvol'))
    except (TypeError,ValueError): rvol=None
    risk=max(0,min(70,(vol-15)/65*70)) if vol is not None else 35
    if price is not None:
        if price<1: risk+=20
        elif price<2: risk+=17
        elif price<5: risk+=13
        elif price<10: risk+=8
        elif price<20: risk+=4
    if rvol is not None:
        if rvol>=3: risk+=10
        elif rvol>=2: risk+=7
        elif rvol>=1.5: risk+=4
        elif rvol<0.5: risk+=5
    return round(min(100,max(0,risk)),1)


def yahoo_symbol(row):
    symbol=str(row.get('symbol','')).strip(); market=str(row.get('market','')).strip()
    if market=='XTSE' and not symbol.endswith('.TO'): return symbol+'.TO'
    if market=='XTSX' and not symbol.endswith('.V'): return symbol+'.V'
    return symbol


def daily_ohlc(symbols, day):
    out={}
    if not symbols: return out
    end=(datetime.fromisoformat(day).date()+timedelta(days=1)).isoformat()
    for s in symbols:
        try:
            frame=yf.download(s,start=day,end=end,interval='1d',auto_adjust=False,progress=False,threads=False)
            if not frame.empty:
                def scalar(col):
                    v=frame[col].iloc[0]
                    try: return float(v.iloc[0])
                    except AttributeError: return float(v)
                out[s]={'open':scalar('Open'),'close':scalar('Close')}
        except Exception: continue
    return out


def result_index():
    rows=load_json(RESULTS,{}).get('buy',[])
    return {str(r.get('symbol','')).upper():r for r in rows}


def enrich_pick_identity(p, index):
    r=index.get(str(p.get('symbol','')).upper())
    if not r: return
    if not p.get('market'): p['market']=r.get('market')
    if p.get('timing') is None: p['timing']=r.get('buy_timing',r.get('timing_v14'))


def benchmark_for(entry, day):
    """Open-to-close benchmark matching the strategy holding window.

    Canadian picks are compared with the S&P/TSX Composite; US picks with the
    S&P 500. The combined benchmark is weighted by the number of picks in each
    market so it mirrors the day's geographic mix.
    """
    bars=daily_ohlc(['^GSPTSE','^GSPC'],day)
    def ret(symbol):
        b=bars.get(symbol)
        if not b or not b.get('open') or not b.get('close'): return None
        return round((b['close']/b['open']-1)*100,3)
    tsx=ret('^GSPTSE'); sp=ret('^GSPC')
    ca=sum(1 for p in entry.get('picks',[]) if p.get('market') in ('XTSE','XTSX'))
    us=len(entry.get('picks',[]))-ca
    weighted=None
    parts=[]
    if ca and tsx is not None: parts.append((ca,tsx))
    if us and sp is not None: parts.append((us,sp))
    covered=sum(n for n,_ in parts)
    if covered==len(entry.get('picks',[])) and covered:
        weighted=round(sum(n*r for n,r in parts)/covered,3)
    return {'method':'open_to_close_weighted_by_pick_market','tsx_composite_return_pct':tsx,'sp500_return_pct':sp,'canada_picks':ca,'usa_picks':us,'return_pct':weighted}


def morning():
    results=load_json(RESULTS,{}); rows=results.get('buy',[])
    eligible=[r for r in rows if market_risk(r)<65]
    eligible.sort(key=lambda r:float(r.get('score') or r.get('buy_potential') or 0),reverse=True)
    picks=eligible[:12]; now=datetime.now(TZ); day=now.date().isoformat()
    archive=load_json(ARCHIVE,{'days':[]}); archive['days']=[d for d in archive.get('days',[]) if d.get('date')!=day]
    archive['days'].append({'date':day,'selected_at':now.isoformat(timespec='seconds'),'entry_method':'official_open','exit_method':'official_close','risk_limit':65,'count':len(picks),'status':'selected','average_return_pct':None,'picks':[{'symbol':r.get('symbol'),'market':r.get('market'),'score':r.get('score') or r.get('buy_potential'),'risk':market_risk(r),'timing':r.get('buy_timing',r.get('timing_v14')),'start_price':None,'end_price':None,'return_pct':None} for r in picks]})
    archive['days'].sort(key=lambda d:d.get('date',''),reverse=True); ARCHIVE.write_text(json.dumps(archive,ensure_ascii=False,indent=2),encoding='utf-8')


def evening():
    archive=load_json(ARCHIVE,{'days':[]}); day=datetime.now(TZ).date().isoformat(); entry=next((d for d in archive.get('days',[]) if d.get('date')==day),None)
    if not entry: return
    idx=result_index()
    for p in entry.get('picks',[]): enrich_pick_identity(p,idx)
    bars=daily_ohlc([yahoo_symbol(p) for p in entry.get('picks',[])],day); returns=[]
    for p in entry.get('picks',[]):
        bar=bars.get(yahoo_symbol(p))
        if not bar: continue
        start=bar['open']; end=bar['close']; p['start_price']=start; p['end_price']=end
        if start and end: p['return_pct']=round((end/start-1)*100,3); returns.append(p['return_pct'])
    entry['entry_method']='official_open'; entry['exit_method']='official_close'; entry['average_return_pct']=round(sum(returns)/len(returns),3) if len(returns)==len(entry.get('picks',[])) else None
    entry['benchmark']=benchmark_for(entry,day)
    if entry['average_return_pct'] is not None and entry['benchmark'].get('return_pct') is not None:
        entry['vs_benchmark_pct']=round(entry['average_return_pct']-entry['benchmark']['return_pct'],3)
    else: entry['vs_benchmark_pct']=None
    entry['completed_at']=datetime.now(TZ).isoformat(timespec='seconds'); entry['status']='complete' if len(returns)==len(entry.get('picks',[])) else ('partial' if returns else 'no_prices')
    ARCHIVE.write_text(json.dumps(archive,ensure_ascii=False,indent=2),encoding='utf-8')


if __name__=='__main__':
    mode=sys.argv[1] if len(sys.argv)>1 else ''
    if mode=='morning': morning()
    elif mode=='evening': evening()
    else: raise SystemExit('usage: daily_archive.py morning|evening')
