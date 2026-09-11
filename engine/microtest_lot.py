import os
from pathlib import Path
import numpy as np
import pandas as pd

import microtest_explorer as base

LOT=os.environ.get('MICROTEST_LOT','A').upper().strip()
if LOT not in ('A','B','B1','B2'):
    raise ValueError('MICROTEST_LOT must be A, B, B1 or B2')

GENERAL_FAMILIES=list(base.FAMILIES)
RSI_FAMILIES=[
    'rsi14_only',
    'rsi21_only',
    'rsi14_rsi21',
    'rsi21_delta14',
    'rsi14_rsi21_delta14',
    'rsi21_low_rsi14_accel',
]


def select_all_periods():
    c=list(pd.bdate_range(base.START_MIN,base.START_MAX))
    import random
    random.Random(base.SEED).shuffle(c)
    out=[]
    for d in c:
        if all(abs((d-x).days)>=120 for x in out):
            out.append(d)
        if len(out)>=8:
            break
    return sorted(out)

ALL_PERIODS=select_all_periods()
if LOT=='A':
    LOT_PERIODS=ALL_PERIODS[:4]
elif LOT=='B1':
    LOT_PERIODS=ALL_PERIODS[4:6]
elif LOT=='B2':
    LOT_PERIODS=ALL_PERIODS[6:8]
else:
    LOT_PERIODS=ALL_PERIODS[4:8]
base.N_PERIODS=len(LOT_PERIODS)
base.pick_periods=lambda: LOT_PERIODS

orig_features=base.features
orig_score_family=base.score_family


def rsi_last(close,period):
    s=pd.Series(close,dtype=float)
    if len(s)<period+2:
        return 50.0
    d=s.diff()
    up=d.clip(lower=0).rolling(period).mean()
    dn=(-d.clip(upper=0)).rolling(period).mean()
    rs=up/dn.replace(0,np.nan)
    rsi=(100-100/(1+rs)).iloc[-1]
    return base.finite(rsi,50)


def low_rsi_quality(r):
    return base.clip((50-base.finite(r,50))/30)


def features_with_rsi21(row,h,cfg,asof):
    z=orig_features(row,h,cfg,asof)
    if not z:
        return None
    x,entry,extra=z
    hh=base.normalize_idx(h)
    hist=hh.loc[hh.index<=asof]
    c=hist['Close'].astype(float)
    extra['rsi21']=rsi_last(c,21)
    extra['rsi14_calc']=rsi_last(c,14)
    return x,entry,extra


def score_family(name,x,extra):
    if name not in RSI_FAMILIES:
        return orig_score_family(name,x,extra)
    r14=base.finite(extra.get('rsi14_calc',x.get('rsi',50)),50)
    r21=base.finite(extra.get('rsi21',50),50)
    d14=base.finite(x.get('delta_rsi',0),0)
    q14=low_rsi_quality(r14)
    q21=low_rsi_quality(r21)
    accel=base.qrebound(d14,-2,4)
    if name=='rsi14_only': return 100*q14
    if name=='rsi21_only': return 100*q21
    if name=='rsi14_rsi21': return base.weighted([(q14,50),(q21,50)])
    if name=='rsi21_delta14': return base.weighted([(q21,65),(accel,35)])
    if name=='rsi14_rsi21_delta14': return base.weighted([(q14,35),(q21,35),(accel,30)])
    if name=='rsi21_low_rsi14_accel': return base.weighted([(q21,60),(accel,40)])
    return 0

base.features=features_with_rsi21
base.score_family=score_family
base.FAMILIES=GENERAL_FAMILIES if LOT=='A' else GENERAL_FAMILIES+RSI_FAMILIES


def main():
    base.main()
    root=Path(__file__).resolve().parents[1]
    src=root/'data/microtest_explorer.json'
    suffix=LOT.lower()
    dst=root/f'data/microtest_lot_{suffix}.json'
    if src.exists():
        src.replace(dst)
        print(f'Published lot {LOT}: {dst.name}')

if __name__=='__main__':
    main()
