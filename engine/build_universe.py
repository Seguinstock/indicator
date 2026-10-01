import csv, json, re, urllib.request
from pathlib import Path
import pandas as pd
import pitindex
import yfinance as yf

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'config/symbols.csv'
CANADA_PER_EXCHANGE=500

def tmx_companies(exchange, market):
    url=f'https://www.tsx.com/json/company-directory/search/{exchange}/%5E'
    req=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0','Accept':'application/json'})
    with urllib.request.urlopen(req,timeout=30) as r:
        payload=json.loads(r.read().decode('utf-8'))
    rows=[]
    for item in payload.get('results',[]):
        symbol=str(item.get('symbol','')).strip().upper()
        name=str(item.get('name','')).strip()
        if not symbol or not name:
            continue
        # Keep operating-company style primary listings; exclude obvious exchange products.
        upper=name.upper()
        if ' CDR ' in f' {upper} ' or upper.endswith(' CDR') or 'EXCHANGE TRADED FUND' in upper or upper.endswith(' ETF'):
            continue
        if any(x in symbol for x in ['.WT','.DB','.PR','.RT']):
            continue
        rows.append((symbol,market,'CA','true',name))
    return rows

def yahoo_symbol(symbol, market):
    s=symbol.replace('.','-')
    return s+'.TO' if market=='XTSE' else s+'.V'

def liquid_top(rows, n):
    if len(rows)<=n:
        return rows
    lookup={yahoo_symbol(s,m):(s,m,c,e,name) for s,m,c,e,name in rows}
    tickers=list(lookup)
    scores={}
    for start in range(0,len(tickers),100):
        batch=tickers[start:start+100]
        try:
            data=yf.download(batch,period='3mo',interval='1d',auto_adjust=True,progress=False,threads=True,group_by='column')
        except Exception:
            continue
        for t in batch:
            try:
                if len(batch)==1:
                    close=data['Close']; volume=data['Volume']
                else:
                    close=data['Close'][t]; volume=data['Volume'][t]
                dv=(close*volume).dropna()
                if len(dv)>=10:
                    scores[t]=float(dv.tail(60).median())
            except Exception:
                pass
    ranked=sorted(tickers,key=lambda t:scores.get(t,-1),reverse=True)
    selected=[lookup[t] for t in ranked[:n] if scores.get(t,-1)>=0]
    if len(selected)<n:
        used={r[0] for r in selected}
        selected += [r for r in rows if r[0] not in used][:n-len(selected)]
    return selected[:n]

def portfolio_symbols(existing):
    extra=[]
    portfolios=json.loads((ROOT/'config/portfolios.json').read_text(encoding='utf-8'))
    for p in portfolios:
        path=ROOT/p['file']
        if not p.get('active',True) or not path.exists(): continue
        with open(path,encoding='utf-8-sig') as f:
            for row in csv.DictReader(f):
                s=str(row.get('symbol','')).strip().upper()
                if s and s in existing: extra.append(existing[s])
    return extra

def main():
    existing={}
    if OUT.exists():
        with open(OUT,encoding='utf-8-sig') as f:
            for r in csv.DictReader(f):
                if r.get('symbol'): existing[r['symbol'].upper()]=(r['symbol'],r['market'],r['country'],r.get('enabled','true'))

    members=pitindex.get_constituents(pd.Timestamp.utcnow().date().isoformat(),index='sp1500')
    us=[]; seen=set()
    for ticker in members['ticker'].tolist():
        s=str(ticker).strip().upper().replace('.','-')
        if s and s not in seen:
            seen.add(s); us.append((s,'XNYS','US','true'))

    tsx=liquid_top(tmx_companies('tsx','XTSE'),CANADA_PER_EXCHANGE)
    tsxv=liquid_top(tmx_companies('tsxv','XTSX'),CANADA_PER_EXCHANGE)
    ca=[(s,m,c,e) for s,m,c,e,_ in tsx+tsxv]

    rows=us+ca
    present={r[0] for r in rows}
    extras=[r for r in portfolio_symbols(existing) if r[0] not in present]
    # Deduplicate portfolio extras too.
    for r in extras:
        if r[0] not in present:
            rows.append(r); present.add(r[0])

    with open(OUT,'w',newline='',encoding='utf-8') as f:
        w=csv.writer(f); w.writerow(['symbol','market','country','enabled']); w.writerows(rows)
    print(f'Universe: {len(us)} S&P 1500 + {len(tsx)} TSX + {len(tsxv)} TSXV + {len(rows)-len(us)-len(ca)} portfolio extras = {len(rows)}')

if __name__=='__main__': main()
