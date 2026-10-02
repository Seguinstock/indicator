import csv,json,time
from pathlib import Path
from datetime import datetime,timezone
import numpy as np
import pandas as pd
import yfinance as yf

ROOT=Path(__file__).resolve().parents[1]
SYMS=ROOT/'config/symbols.csv'
OUT=ROOT/'data/free_fundamentals_coverage.json'

def ys(row):
    s=row['symbol'].replace('.','-')
    return s+'.TO' if row['market']=='XTSE' else s+'.V' if row['market']=='XTSX' else s

def any_value(df,names):
    if df is None or getattr(df,'empty',True): return False
    idx={str(x).lower():x for x in df.index}
    for n in names:
        k=n.lower()
        if k in idx:
            vals=pd.to_numeric(df.loc[idx[k]],errors='coerce')
            if np.isfinite(vals).any(): return True
    return False

def audit(row):
    t=yf.Ticker(ys(row))
    flags={k:False for k in ['market_cap','cash','total_debt','net_debt','ebitda','free_cash_flow','revenue','equity']}
    try:
        fi=t.fast_info
        mc=fi.get('market_cap') if fi else None
        flags['market_cap']=mc is not None and np.isfinite(float(mc))
    except Exception: pass
    try: bs=t.quarterly_balance_sheet
    except Exception: bs=pd.DataFrame()
    try: inc=t.quarterly_income_stmt
    except Exception: inc=pd.DataFrame()
    try: cf=t.quarterly_cashflow
    except Exception: cf=pd.DataFrame()
    flags['cash']=any_value(bs,['Cash Cash Equivalents And Short Term Investments','Cash And Cash Equivalents','Cash Financial'])
    flags['total_debt']=any_value(bs,['Total Debt'])
    flags['net_debt']=any_value(bs,['Net Debt'])
    flags['equity']=any_value(bs,['Stockholders Equity','Total Equity Gross Minority Interest'])
    flags['ebitda']=any_value(inc,['EBITDA','Normalized EBITDA'])
    flags['revenue']=any_value(inc,['Total Revenue','Operating Revenue'])
    flags['free_cash_flow']=any_value(cf,['Free Cash Flow'])
    return flags

def main():
    with open(SYMS,encoding='utf-8-sig') as f: rows=list(csv.DictReader(f))
    groups={'ALL':rows,'US':[r for r in rows if r['country']=='US'],'TSX':[r for r in rows if r['market']=='XTSE'],'TSXV':[r for r in rows if r['market']=='XTSX']}
    fields=['market_cap','cash','total_debt','net_debt','ebitda','free_cash_flow','revenue','equity']
    counts={g:{k:0 for k in fields} for g in groups}; errors=[]; done=0
    for r in rows:
        try: flags=audit(r)
        except Exception as e:
            flags={k:False for k in fields}; errors.append({'symbol':r['symbol'],'market':r['market'],'error':str(e)[:180]})
        gs=['ALL','US' if r['country']=='US' else 'TSX' if r['market']=='XTSE' else 'TSXV']
        for g in gs:
            for k,v in flags.items(): counts[g][k]+=int(v)
        done+=1
        if done%100==0: print(f'AUDIT {done}/{len(rows)}',flush=True)
        time.sleep(.05)
    summary={}
    for g,rs in groups.items():
        n=len(rs); summary[g]={'n':n}
        for k in fields:
            summary[g][k]={'count':counts[g][k],'pct':round(100*counts[g][k]/n,1) if n else 0}
    payload={'generated_at':datetime.now(timezone.utc).isoformat(),'source':'Yahoo Finance via yfinance, no paid API key','universe':len(rows),'summary':summary,'request_errors':len(errors),'error_sample':errors[:50]}
    OUT.write_text(json.dumps(payload,indent=2,ensure_ascii=False),encoding='utf-8')
    print(json.dumps(summary,indent=2))

if __name__=='__main__': main()
