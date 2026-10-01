import csv, json, urllib.request
from pathlib import Path
import pandas as pd
import pitindex
import yfinance as yf

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'config/symbols.csv'
CANADA_TARGET=1600
MIN_CANADA=1600

def cap_value(v):
    if pd.isna(v): return 0.0
    s=str(v).replace(',','').replace('$','').strip().upper()
    mult=1.0
    if s.endswith('T'): mult=1e12; s=s[:-1]
    elif s.endswith('B'): mult=1e9; s=s[:-1]
    elif s.endswith('M'): mult=1e6; s=s[:-1]
    elif s.endswith('K'): mult=1e3; s=s[:-1]
    try: return float(s)*mult
    except Exception: return 0.0

def canadian_list(slug, market):
    rows=[]; seen=set()
    for page in range(1,10):
        url=f'https://stockanalysis.com/list/{slug}/?page={page}'
        req=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0','Accept':'text/html'})
        try:
            with urllib.request.urlopen(req,timeout=30) as r:
                tables=pd.read_html(r.read())
        except Exception as exc:
            print(f'WARN {market} page {page}: {exc}')
            continue
        table=next((t for t in tables if 'Symbol' in t.columns and 'Company Name' in t.columns),None)
        if table is None or table.empty: break
        added=0
        for _,item in table.iterrows():
            symbol=str(item.get('Symbol','')).strip().upper()
            name=str(item.get('Company Name','')).strip()
            if not symbol or symbol=='NAN' or symbol in seen: continue
            upper=name.upper()
            if ' CDR ' in f' {upper} ' or upper.endswith(' CDR') or 'EXCHANGE TRADED FUND' in upper or upper.endswith(' ETF'): continue
            if any(x in symbol for x in ['.WT','.DB','.PR','.RT']): continue
            seen.add(symbol); added+=1
            rows.append({'symbol':symbol,'market':market,'name':name,'market_cap':cap_value(item.get('Market Cap'))})
        if added==0: break
    return rows

def yahoo_symbol(symbol, market):
    s=symbol.replace('.','-')
    return s+'.TO' if market=='XTSE' else s+'.V'

def rank_canada(rows):
    # Combine TSX and TSXV. Market cap is the primary quality/size criterion;
    # recent median dollar volume breaks ties and penalizes illiquid listings.
    by_symbol={}
    for r in rows:
        old=by_symbol.get(r['symbol'])
        if old is None or r['market_cap']>old['market_cap']: by_symbol[r['symbol']]=r
    rows=list(by_symbol.values())
    tickers=[yahoo_symbol(r['symbol'],r['market']) for r in rows]
    liquidity={}
    for start in range(0,len(tickers),100):
        batch=tickers[start:start+100]
        try:
            data=yf.download(batch,period='3mo',interval='1d',auto_adjust=True,progress=False,threads=True,group_by='column')
        except Exception:
            continue
        for t in batch:
            try:
                close=data['Close'] if len(batch)==1 else data['Close'][t]
                volume=data['Volume'] if len(batch)==1 else data['Volume'][t]
                dv=(close*volume).dropna()
                if len(dv)>=10: liquidity[t]=float(dv.tail(60).median())
            except Exception: pass
    for r in rows:
        r['liquidity']=liquidity.get(yahoo_symbol(r['symbol'],r['market']),0.0)
        # Cap dominates; liquidity is a secondary preference among similarly sized names.
        r['rank_key']=(r['market_cap'],r['liquidity'])
    eligible=[r for r in rows if r['liquidity']>0]
    eligible.sort(key=lambda r:r['rank_key'],reverse=True)
    if len(eligible)<MIN_CANADA:
        raise RuntimeError(f'Only {len(eligible)} liquid Canadian listings found; refusing to replace universe')
    return eligible[:CANADA_TARGET]

def portfolio_rows(existing):
    out=[]
    portfolios=json.loads((ROOT/'config/portfolios.json').read_text(encoding='utf-8'))
    for p in portfolios:
        path=ROOT/p['file']
        if not p.get('active',True) or not path.exists(): continue
        with open(path,encoding='utf-8-sig') as f:
            for row in csv.DictReader(f):
                s=str(row.get('symbol','')).strip().upper()
                if s and s in existing: out.append(existing[s])
    return out

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

    candidates=canadian_list('toronto-stock-exchange','XTSE')+canadian_list('tsx-venture-exchange','XTSX')
    selected=rank_canada(candidates)
    ca=[(r['symbol'],r['market'],'CA','true') for r in selected]

    rows=us+ca; present={r[0] for r in rows}
    for r in portfolio_rows(existing):
        if r[0] not in present:
            rows.append(r); present.add(r[0])

    ca_count=sum(1 for r in rows if r[2]=='CA')
    if ca_count<MIN_CANADA: raise RuntimeError(f'Canadian safety check failed: {ca_count} < {MIN_CANADA}')

    with open(OUT,'w',newline='',encoding='utf-8') as f:
        w=csv.writer(f); w.writerow(['symbol','market','country','enabled']); w.writerows(rows)
    tsx=sum(1 for r in ca if r[1]=='XTSE'); tsxv=sum(1 for r in ca if r[1]=='XTSX')
    print(f'Universe built: {len(us)} S&P1500 + {len(ca)} Canada ({tsx} TSX, {tsxv} TSXV) + {len(rows)-len(us)-len(ca)} portfolio extras = {len(rows)}')

if __name__=='__main__': main()
