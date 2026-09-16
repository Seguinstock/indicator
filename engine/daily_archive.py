import json
import sys
from datetime import datetime
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
    vol=float(x.get('volatility_pct') or 0); price=float(x.get('price') or x.get('close') or 0); rvol=x.get('rvol')
    risk=min(70,max(0,vol)*7)
    if price>0: risk+=min(20,max(0,20-price))
    try:
        rv=float(rvol); risk+=min(10,max(0,rv-1)*10) if rv>=1 else 5
    except (TypeError,ValueError): pass
    return round(min(100,max(0,risk)),1)


def yahoo_symbol(row):
    symbol=str(row.get('symbol','')).strip(); market=str(row.get('market','')).strip()
    if market=='XTSE' and not symbol.endswith('.TO'): return symbol+'.TO'
    if market=='XTSX' and not symbol.endswith('.V'): return symbol+'.V'
    return symbol


def daily_ohlc(symbols, day):
    out={}
    if not symbols: return out
    # Daily bar gives the official session Open and Close and avoids attributing overnight gaps to the strategy.
    for s in symbols:
        try:
            frame=yf.download(s,start=day,end=(datetime.fromisoformat(day).date().fromordinal(datetime.fromisoformat(day).date().toordinal()+1)).isoformat(),interval='1d',auto_adjust=False,progress=False,threads=False)
            if not frame.empty:
                def scalar(col):
                    v=frame[col].iloc[0]
                    try: return float(v.iloc[0])
                    except AttributeError: return float(v)
                out[s]={'open':scalar('Open'),'close':scalar('Close')}
        except Exception: continue
    return out


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
    bars=daily_ohlc([yahoo_symbol(p) for p in entry.get('picks',[])],day); returns=[]
    for p in entry.get('picks',[]):
        bar=bars.get(yahoo_symbol(p));
        if not bar: continue
        start=bar['open']; end=bar['close']; p['start_price']=start; p['end_price']=end
        if start and end: p['return_pct']=round((end/start-1)*100,3); returns.append(p['return_pct'])
    entry['entry_method']='official_open'; entry['exit_method']='official_close'; entry['average_return_pct']=round(sum(returns)/len(returns),3) if returns else None; entry['completed_at']=datetime.now(TZ).isoformat(timespec='seconds'); entry['status']='complete' if len(returns)==len(entry.get('picks',[])) else ('partial' if returns else 'no_prices')
    ARCHIVE.write_text(json.dumps(archive,ensure_ascii=False,indent=2),encoding='utf-8')


if __name__=='__main__':
    mode=sys.argv[1] if len(sys.argv)>1 else ''
    if mode=='morning': morning()
    elif mode=='evening': evening()
    else: raise SystemExit('usage: daily_archive.py morning|evening')
