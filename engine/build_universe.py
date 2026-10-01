import csv, io, json, urllib.request
from pathlib import Path
import pandas as pd
import pitindex
import yfinance as yf

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'config/symbols.csv'
CANADA_TARGET=1500
SOURCE='https://raw.githubusercontent.com/adanos-software/free-ticker-database/main/data/core_listings.csv'

def load_canadian_stocks():
    req=urllib.request.Request(SOURCE,headers={'User-Agent':'Stockindicator universe builder'})
    with urllib.request.urlopen(req,timeout=120) as r:
        df=pd.read_csv(io.BytesIO(r.read()))
    required={'ticker','exchange','asset_type','country_code'}
    if not required.issubset(df.columns):
        raise RuntimeError(f'Canadian source schema changed: {sorted(df.columns)}')
    df=df[(df['exchange'].isin(['TSX','TSXV'])) & (df['asset_type']=='Stock') & (df['country_code']=='CA')].copy()
    df['ticker']=df['ticker'].astype(str).str.strip().str.upper()
    df=df[df['ticker'].ne('') & df['ticker'].ne('NAN')]
    df=df.drop_duplicates(subset=['exchange','ticker'])
    return [{'symbol':r.ticker,'market':'XTSE' if r.exchange=='TSX' else 'XTSX'} for r in df.itertuples()]

def yahoo_symbol(r):
    s=r['symbol'].replace('.','-')
    return s+('.TO' if r['market']=='XTSE' else '.V')

def rank_by_liquidity(rows):
    lookup={yahoo_symbol(r):r for r in rows}
    tickers=list(lookup); scores={}
    for start in range(0,len(tickers),75):
        batch=tickers[start:start+75]
        try:
            data=yf.download(batch,period='3mo',interval='1d',auto_adjust=True,progress=False,threads=True,group_by='column')
        except Exception as exc:
            print(f'WARN liquidity batch {start}: {exc}')
            continue
        for t in batch:
            try:
                close=data['Close'] if len(batch)==1 else data['Close'][t]
                volume=data['Volume'] if len(batch)==1 else data['Volume'][t]
                dv=(close*volume).replace([float('inf'),float('-inf')],pd.NA).dropna()
                if len(dv)>=10: scores[t]=float(dv.tail(60).median())
            except Exception: pass
    ranked=sorted((t for t in tickers if scores.get(t,0)>0),key=lambda t:scores[t],reverse=True)
    if len(ranked)<CANADA_TARGET:
        raise RuntimeError(f'Only {len(ranked)} Canadian stocks have valid liquidity; refusing to publish')
    return [lookup[t] for t in ranked[:CANADA_TARGET]]

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

    candidates=load_canadian_stocks()
    selected=rank_by_liquidity(candidates)
    ca=[(r['symbol'],r['market'],'CA','true') for r in selected]
    rows=us+ca; present={r[0] for r in rows}
    for r in portfolio_rows(existing):
        if r[0] not in present:
            rows.append(r); present.add(r[0])

    if len(ca)!=1500: raise RuntimeError(f'Canadian target mismatch: {len(ca)}')
    if not (1400<=len(us)<=1600): raise RuntimeError(f'S&P 1500 count unexpected: {len(us)}')
    if len({r[0] for r in rows})!=len(rows): raise RuntimeError('Duplicate symbols in final universe')

    with open(OUT,'w',newline='',encoding='utf-8') as f:
        w=csv.writer(f); w.writerow(['symbol','market','country','enabled']); w.writerows(rows)
    tsx=sum(r[1]=='XTSE' for r in ca); tsxv=sum(r[1]=='XTSX' for r in ca)
    print(f'FIXED UNIVERSE READY: total={len(rows)} Canada=1500 (TSX={tsx}, TSXV={tsxv}) US={len(us)} extras={len(rows)-len(us)-len(ca)} candidates={len(candidates)}')

if __name__=='__main__': main()
