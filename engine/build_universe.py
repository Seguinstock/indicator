import csv, json, re
from pathlib import Path
import pandas as pd
import pitindex

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'config/symbols.csv'
CANADA_N=1000

def cap_value(v):
    s=str(v).strip().replace(',','').replace('$','')
    if not s or s in {'-','nan','None'}: return -1.0
    m=re.fullmatch(r'([0-9.]+)\s*([KMBT]?)',s,re.I)
    if not m: return -1.0
    mult={'':1,'K':1e3,'M':1e6,'B':1e9,'T':1e12}
    return float(m.group(1))*mult[m.group(2).upper()]

def canada(exchange,market):
    rows=[]
    base={'XTSE':'https://stockanalysis.com/list/toronto-stock-exchange/',
          'XTSX':'https://stockanalysis.com/list/tsx-venture-exchange/'}[market]
    for page in range(1,5):
        url=base if page==1 else f'{base}?page={page}'
        try: tables=pd.read_html(url)
        except Exception: continue
        for df in tables:
            cols={str(c).strip().lower():c for c in df.columns}
            if 'symbol' not in cols or 'market cap' not in cols: continue
            for _,r in df.iterrows():
                symbol=str(r[cols['symbol']]).strip().upper()
                cap=cap_value(r[cols['market cap']])
                if symbol and symbol!='NAN' and cap>=0:
                    rows.append((cap,symbol,market,'CA','true'))
            break
    return rows

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

    ca=canada('TSX','XTSE')+canada('TSXV','XTSX')
    best={}
    for cap,s,m,c,e in ca:
        if s not in best or cap>best[s][0]: best[s]=(cap,s,m,c,e)
    ca_top=sorted(best.values(),reverse=True)[:CANADA_N]

    rows=us+[(s,m,c,e) for _,s,m,c,e in ca_top]
    present={r[0] for r in rows}
    extras=[r for r in portfolio_symbols(existing) if r[0] not in present]
    rows+=extras
    with open(OUT,'w',newline='',encoding='utf-8') as f:
        w=csv.writer(f); w.writerow(['symbol','market','country','enabled']); w.writerows(rows)
    print(f'Universe: {len(us)} S&P 1500 + {len(ca_top)} Canada + {len(extras)} portfolio extras = {len(rows)}')

if __name__=='__main__': main()
