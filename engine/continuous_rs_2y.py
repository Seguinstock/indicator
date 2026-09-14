import csv, json, math, time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf
import pitindex

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / 'data' / 'backtest_relative_strength_continuous_2y.json'
TRADING_DAYS = 252
INITIAL_CAPITAL = 100.0
PORTFOLIO_N = 10
BENCHMARK_N = 100
SELL_THRESHOLD = 70.0
BATCH = 80


def norm_ticker(t):
    return str(t).strip().upper().replace('.', '-')


def constituents(date, index):
    m = pitindex.get_constituents(pd.Timestamp(date).strftime('%Y-%m-%d'), index=index)
    return sorted({norm_ticker(x) for x in m['ticker'].tolist() if str(x).strip()})


def download_batch(tickers, start, end):
    out = {}
    if not tickers:
        return out
    for i in range(0, len(tickers), BATCH):
        batch = tickers[i:i+BATCH]
        try:
            raw = yf.download(batch, start=start, end=end, group_by='ticker', auto_adjust=True,
                              actions=False, threads=True, progress=False)
        except Exception as e:
            print('download batch failed', i, e)
            continue
        for t in batch:
            try:
                h = raw[t] if len(batch) > 1 else raw
                if h is None or h.empty or 'Close' not in h.columns:
                    continue
                h = h[['Open','High','Low','Close','Volume']].copy().dropna(subset=['Close'])
                idx = pd.to_datetime(h.index)
                if getattr(idx, 'tz', None) is not None:
                    idx = idx.tz_localize(None)
                h.index = idx
                out[t] = h.astype(float)
            except Exception:
                pass
        print(f'downloaded {min(i+BATCH,len(tickers))}/{len(tickers)}')
        time.sleep(0.25)
    return out


def wilder_rsi_series(close, period=14):
    c = np.asarray(close, dtype=float)
    out = np.full(len(c), np.nan)
    if len(c) < period + 1:
        return pd.Series(out, index=close.index)
    d = np.diff(c)
    up = np.where(d > 0, d, 0.0)
    dn = np.where(d < 0, -d, 0.0)
    ag = float(np.mean(up[:period])); al = float(np.mean(dn[:period]))
    out[period] = 100.0 if al == 0 else 100.0 - 100.0/(1.0 + ag/al)
    for j in range(period, len(d)):
        ag = (ag*(period-1) + float(up[j]))/period
        al = (al*(period-1) + float(dn[j]))/period
        out[j+1] = 100.0 if al == 0 else 100.0 - 100.0/(1.0 + ag/al)
    return pd.Series(out, index=close.index)


def feature_frame(h, market_ret20, cfg):
    c = h['Close'].astype(float)
    v = h['Volume'].astype(float)
    ret20 = (c / c.shift(20) - 1.0) * 100.0
    ret60 = (c / c.shift(60) - 1.0) * 100.0
    rel20 = ret20 - market_ret20.reindex(c.index).ffill()
    rsi = wilder_rsi_series(c, int(cfg['indicators']['rsi_period']))
    rvn = int(cfg['indicators']['rvol_period'])
    rvol = v / v.shift(1).rolling(rvn).mean()
    ma50 = c.rolling(50).mean(); ma200 = c.rolling(200).mean()
    ma200_prev = c.shift(20).rolling(200).mean()
    up = ma200 > ma200_prev; down = ma200 < ma200_prev
    trend = pd.Series(0.0, index=c.index)
    trend[(c > ma50) & (ma50 > ma200) & up] = 2.0
    trend[(c < ma50) & (c > ma200) & up] = 1.0
    trend[(c < ma50) & (ma50 < ma200) & down] = -2.0
    trend[(c > ma50) & (c < ma200) & down] = -1.0
    trend[(trend == 0) & (c > ma200) & up] = 0.5
    trend[(trend == 0) & (c < ma200) & down] = -0.5
    trend_q = trend.map({-2:0.0,-1:0.1,-0.5:0.25,0:0.5,0.5:0.65,1:0.8,2:1.0}).fillna(0.5)
    m = cfg['buy_model']
    q_rel = ((rel20 + 5.0) / 20.0).clip(0,1)
    q_ret = ((ret60 + 5.0) / 30.0).clip(0,1)
    rv0=float(m.get('rvol_floor',0.6)); rv1=max(float(m.get('rvol_full',2.0)),rv0+1e-6)
    q_rvol=((rvol-rv0)/(rv1-rv0)).clip(0,1).fillna(0)
    rt=float(m.get('rsi_target',58)); rr=max(float(m.get('rsi_range',22)),1e-6)
    q_rsi=(1-(rsi-rt).abs()/rr).clip(0,1).fillna(0)
    weights=np.array([float(m.get('relative_strength_20_weight',40)),float(m.get('return_60_weight',25)),float(m.get('trend_weight',20)),float(m.get('rvol_weight',10)),float(m.get('rsi_weight',5))])
    total=max(weights.sum(),1e-9)
    score=(weights[0]*q_rel+weights[1]*q_ret+weights[2]*trend_q+weights[3]*q_rvol+weights[4]*q_rsi)*100.0/total
    return pd.DataFrame({'score':score,'sell_score':100.0-score,'ret20':ret20,'ret60':ret60,'rel20':rel20,'rsi':rsi,'rvol':rvol,'trend':trend}, index=c.index)


def max_drawdown(values):
    a=np.asarray(values,dtype=float)
    if len(a)==0:return 0.0
    peak=np.maximum.accumulate(a)
    return float(np.min(a/peak-1.0)*100.0)


def main():
    cfg=json.loads((ROOT/'config/parameters.json').read_text(encoding='utf-8'))
    end=pd.Timestamp.utcnow().tz_localize(None).normalize()
    # Latest completed U.S. trading session will be inferred from downloaded market history.
    probe=yf.download('^GSPC',period='10d',auto_adjust=True,progress=False)
    pidx=pd.to_datetime(probe.index)
    if getattr(pidx,'tz',None) is not None:pidx=pidx.tz_localize(None)
    end_day=pidx.max().normalize()
    start_day=(end_day-pd.DateOffset(years=2)).normalize()
    history_start=(start_day-pd.Timedelta(days=420)).normalize()
    download_end=(end_day+pd.Timedelta(days=3)).normalize()
    print('period',start_day.date(),'to',end_day.date(),'history from',history_start.date())

    # Build point-in-time constituent union monthly, plus exact first/last dates.
    monthly=list(pd.date_range(history_start,end_day,freq='MS'))+[history_start,start_day,end_day]
    union=set(); membership_cache={}
    for k,d in enumerate(sorted(set(pd.Timestamp(x).normalize() for x in monthly)),1):
        try:
            u=set(constituents(d,'sp1500')); union.update(u); membership_cache[str(d.date())]=u
            print(f'PIT universe {k}/{len(monthly)} {d.date()} n={len(u)} union={len(union)}')
        except Exception as e:
            print('PIT monthly failed',d.date(),e)
    if len(union)<500:
        raise RuntimeError(f'Insufficient S&P1500 PIT universe: {len(union)}')

    market=download_batch(['^SP1500','^GSPC'],history_start,download_end)
    market_symbol='^SP1500' if '^SP1500' in market else '^GSPC'
    mc=market[market_symbol]['Close']
    market_ret20=(mc/mc.shift(20)-1.0)*100.0
    calendar=mc.loc[(mc.index>=start_day)&(mc.index<=end_day)].index
    if len(calendar)<450: raise RuntimeError('Insufficient trading calendar')
    start_exec=calendar[0]; end_exec=calendar[-1]

    histories=download_batch(sorted(union),history_start,download_end)
    print('usable histories',len(histories),'of',len(union))
    features={t:feature_frame(h,market_ret20,cfg) for t,h in histories.items()}

    # Exact point-in-time membership on every trading day, preserving auditability.
    daily_members={}
    for i,d in enumerate(calendar,1):
        try: daily_members[d]=set(constituents(d,'sp1500'))
        except Exception:
            # Conservative fallback to nearest earlier cached monthly universe.
            keys=[pd.Timestamp(k) for k in membership_cache if pd.Timestamp(k)<=d]
            daily_members[d]=membership_cache[str(max(keys).date())] if keys else set(union)
        if i%25==0: print(f'daily PIT {i}/{len(calendar)}')

    # Initial signal uses previous trading day's close; execution is at first-day open.
    signal_day=mc.index[mc.index<start_exec][-1]
    def score_on(t,d):
        f=features.get(t)
        if f is None:return np.nan
        z=f.loc[f.index<=d,'score'].dropna()
        return float(z.iloc[-1]) if len(z) else np.nan
    def px(t,d,field):
        h=histories.get(t)
        if h is None:return np.nan
        z=h.loc[h.index==d,field]
        return float(z.iloc[-1]) if len(z) else np.nan

    initial_universe=[t for t in daily_members[start_exec] if t in histories]
    ranked=sorted(((score_on(t,signal_day),t) for t in initial_universe),reverse=True)
    top10=[t for s,t in ranked if np.isfinite(s) and np.isfinite(px(t,start_exec,'Open'))][:PORTFOLIO_N]
    if len(top10)<PORTFOLIO_N: raise RuntimeError('Could not initialize 10-position portfolio')

    positions={}; trades=[]
    for t in top10:
        op=px(t,start_exec,'Open'); positions[t]={'shares':10.0/op,'entry_price':op,'entry_date':str(start_exec.date()),'capital':10.0}
        trades.append({'type':'BUY','date':str(start_exec.date()),'symbol':t,'price':op,'value':10.0,'reason':'initial_top10','signal_score':score_on(t,signal_day)})

    equity=[]; pending=[]
    for di,d in enumerate(calendar):
        # Execute prior-close sell/replacement instructions at today's open.
        if pending:
            held=set(positions)
            prior=calendar[di-1] if di>0 else signal_day
            candidates=[t for t in daily_members[d] if t in histories and t not in held]
            cand_rank=sorted(((score_on(t,prior),t) for t in candidates),reverse=True)
            for old in list(pending):
                if old not in positions: continue
                old_open=px(old,d,'Open')
                if not np.isfinite(old_open): continue
                pos=positions.pop(old); proceeds=pos['shares']*old_open
                ret=(old_open/pos['entry_price']-1.0)*100.0
                trades.append({'type':'SELL','date':str(d.date()),'symbol':old,'price':old_open,'value':proceeds,'return_pct':ret,'reason':'sell_score>=70'})
                held=set(positions)
                replacement=None; rep_score=None
                while cand_rank:
                    s,t=cand_rank.pop(0)
                    if t in held or not np.isfinite(s):continue
                    op=px(t,d,'Open')
                    if np.isfinite(op) and op>0:
                        replacement=t; rep_score=s; break
                if replacement:
                    op=px(replacement,d,'Open')
                    positions[replacement]={'shares':proceeds/op,'entry_price':op,'entry_date':str(d.date()),'capital':proceeds}
                    trades.append({'type':'BUY','date':str(d.date()),'symbol':replacement,'price':op,'value':proceeds,'reason':'replacement_best_score','signal_score':rep_score,'replaces':old})
                else:
                    # Extremely unlikely: keep cash as synthetic position until next replacement opportunity.
                    positions[f'CASH:{old}']={'shares':proceeds,'entry_price':1.0,'entry_date':str(d.date()),'capital':proceeds}
            pending=[]

        # Close valuation.
        value=0.0
        for t,pos in positions.items():
            if t.startswith('CASH:'): value+=pos['shares']; continue
            cp=px(t,d,'Close')
            if np.isfinite(cp): value+=pos['shares']*cp
            else: value+=pos['capital']
        equity.append({'date':str(d.date()),'value':value})

        # Generate sells at close, executed next session. Never sell on final day.
        if di < len(calendar)-1:
            pending=[]
            for t in list(positions):
                if t.startswith('CASH:'): continue
                s=score_on(t,d)
                sell=100.0-s if np.isfinite(s) else np.nan
                if np.isfinite(sell) and sell>=SELL_THRESHOLD:
                    pending.append(t)

    final_value=equity[-1]['value']
    total_return=(final_value/INITIAL_CAPITAL-1)*100.0
    years=(end_exec-start_exec).days/365.2425
    cagr=(final_value/INITIAL_CAPITAL)**(1/years)-1 if years>0 else np.nan

    # S&P500 top-100 benchmark: rank with same formula on signal day, buy $1 each at day-1 open and hold.
    sp500=set(constituents(start_exec,'sp500'))
    sp500_candidates=[t for t in sp500 if t in histories]
    bench_rank=sorted(((score_on(t,signal_day),t) for t in sp500_candidates),reverse=True)
    bench_names=[t for s,t in bench_rank if np.isfinite(s) and np.isfinite(px(t,start_exec,'Open'))][:BENCHMARK_N]
    bench_positions=[]
    for t in bench_names:
        op=px(t,start_exec,'Open'); bench_positions.append((t,1.0/op,op,score_on(t,signal_day)))
    bench_final=0.0
    bench_holdings=[]
    for t,sh,op,s in bench_positions:
        cp=px(t,end_exec,'Close')
        if np.isfinite(cp):
            val=sh*cp; bench_final+=val
            bench_holdings.append({'symbol':t,'initial_score':s,'entry_price':op,'final_price':cp,'final_value':val,'return_pct':(cp/op-1)*100.0})
    bench_return=(bench_final/len(bench_positions)-1)*100.0 if bench_positions else np.nan
    bench_cagr=(bench_final/len(bench_positions))**(1/years)-1 if bench_positions and years>0 else np.nan

    closed=[x for x in trades if x['type']=='SELL']
    win_rate=(sum(1 for x in closed if x.get('return_pct',0)>0)/len(closed)*100.0) if closed else 0.0
    out={
      'generated':datetime.now(timezone.utc).isoformat(),
      'methodology':{
        'period_start':str(start_exec.date()),'period_end':str(end_exec.date()),'years':years,
        'initial_capital_each':INITIAL_CAPITAL,'strategy_positions':PORTFOLIO_N,'strategy_initial_dollars_each':10.0,
        'strategy_universe':'S&P 1500 point-in-time via pitindex','benchmark_universe':'S&P 500 point-in-time at initial date via pitindex',
        'benchmark_positions':len(bench_positions),'benchmark_initial_dollars_each':1.0,
        'execution':'signals at close, trades at next session open; initial ranking uses prior close and executes first-day open',
        'sell_threshold':SELL_THRESHOLD,'transaction_costs':0.0,'slippage':0.0,
        'buy_formula':'40% relative strength 20d + 25% return 60d + 20% trend + 10% RVOL + 5% RSI',
        'sell_formula':'100 - current buy-quality score; sell when deterioration >= 70',
        'benchmark_definition':'Top 100 S&P500 names by same formula on initial signal day; buy $1 each and hold for entire period'
      },
      'strategy':{
        'initial_holdings':top10,'final_value':final_value,'total_return_pct':total_return,'cagr_pct':cagr*100.0,
        'max_drawdown_pct':max_drawdown([x['value'] for x in equity]),'sell_count':len(closed),'win_rate_pct':win_rate,
        'final_holdings':[t for t in positions if not t.startswith('CASH:')]
      },
      'benchmark_top100_sp500':{
        'initial_holdings':bench_names,'final_value':bench_final,'total_return_pct':bench_return,'cagr_pct':bench_cagr*100.0 if np.isfinite(bench_cagr) else None,
        'holdings':bench_holdings
      },
      'comparison':{
        'final_value_difference':final_value-bench_final,
        'total_return_difference_points':total_return-bench_return if np.isfinite(bench_return) else None,
        'cagr_difference_points':(cagr-bench_cagr)*100.0 if np.isfinite(bench_cagr) else None
      },
      'equity_curve':equity,'trades':trades
    }
    OUTPUT.write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in out.items() if k not in ('equity_curve','trades')},ensure_ascii=False,indent=2)[:12000])

if __name__=='__main__': main()
