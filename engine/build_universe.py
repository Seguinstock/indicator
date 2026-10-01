import csv, json, re, urllib.request
from pathlib import Path
import pandas as pd
import pitindex
import yfinance as yf

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'config/symbols.csv'
CANADA_PER_EXCHANGE=500
MIN_CANADA_PER_EXCHANGE=500

def stockanalysis_companies(slug, market):
    """Load Canadian listings sorted by market cap from StockAnalysis.

    StockAnalysis exposes 800+ TSX and 1,500+ TSXV active listings.  Pagination
    is ?p=N.  We deliberately fetch enough pages and refuse to publish a short
    universe, so a source/layout failure cannot silently shrink Canada again.
    """
    rows=[]; seen=set()
    for page in range(1, 80):
        url=f'https://stockanalysis.com/list/{slug}/?p={page}'
        req=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0','Accept':'text/html'})
        try:
            with urllib.request.urlopen(req,timeout=30) as r:
                tables=pd.read_html(r.read())
        except Exception as exc:
            print(f'WARN {market} page {page}: {exc}')
            continue
        table=next((t for t in tables if 'Symbol' in t.columns and 'Company Name' in t.columns),None)
        if table is None or table.empty:
            break
        added=0
        for _,item in table.iterrows():
            symbol=str(item.get('Symbol','')).strip().upper()
            name=str(item.get('Company Name','')).strip()
            if not symbol or symbol=='NAN' or symbol in seen: continue
            upper=name.upper()
            if ' CDR ' in f' {upper} ' or upper.endswith(' CDR') or 'EXCHANGE TRADED FUND' in upper or upper.endswith(' ETF'):
                continue
            if any(x in symbol for x in ['.WT','.DB','.PR','.RT']): continue
            seen.add(symbol); rows.append((symbol,market,'CA','true',name)); added+=1
        if len(rows)>=CANADA_PER_EXCHANGE: break
        if added==0: break
    if len(rows)<MIN_CANADA_PER_EXCHANGE:
        raise RuntimeError(f'{market}: only {len(rows)} eligible listings found; refusing to publish short Canadian universe')
    return rows[:CANADA_PER_EXCHANGE]

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

    tsx=stockanalysis_companies('toronto-stock-exchange','XTSE')
    tsxv=stockanalysis_companies('tsx-venture-exchange','XTSX')
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
