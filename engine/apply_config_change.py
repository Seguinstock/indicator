import csv, io, json, os, re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BODY = os.environ.get('ISSUE_BODY', '')

m = re.search(r'```json\s*(\{.*?\})\s*```', BODY, re.S)
if not m:
    raise SystemExit('No configuration JSON found in issue body')
req = json.loads(m.group(1))
action = req.get('action')

ALLOWED_MARKETS={'XTSE','XTSX','XCNQ','XNYS','XNAS','ARCX','XASE','BATS','NEOE'}
ALLOWED_COUNTRIES={'CA','US',''}


def read_csv(path):
    with path.open(encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f))


def write_csv(path, rows, fields):
    with path.open('w', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader(); w.writerows(rows)


def clean_symbol(v):
    s = str(v or '').strip().upper()
    if not s or len(s) > 20 or not re.fullmatch(r'[A-Z0-9.\-]+', s):
        raise ValueError('Invalid symbol')
    return s


def validate_market_country(market, country):
    market=str(market or '').strip().upper(); country=str(country or '').strip().upper()
    if market not in ALLOWED_MARKETS or country not in ALLOWED_COUNTRIES:
        raise ValueError('Invalid market/country')
    return market,country


def portfolio_path(pid):
    data = json.loads((ROOT/'config/portfolios.json').read_text(encoding='utf-8'))
    for p in data:
        if p['id'] == pid and p.get('active', True):
            path = (ROOT/p['file']).resolve()
            if ROOT not in path.parents:
                raise ValueError('Invalid portfolio path')
            return path
    raise ValueError('Unknown portfolio')


def ensure_scannable_symbol(symbol):
    path=ROOT/'config/symbols.csv'; fields=['symbol','market','country','enabled']; rows=read_csv(path)
    existing=next((r for r in rows if r.get('symbol','').upper()==symbol),None)
    if existing:
        if existing.get('enabled','true').lower()!='true':
            existing['enabled']='true'; write_csv(path,rows,fields)
        return
    market=req.get('market'); country=req.get('country')
    if not market:
        raise ValueError(f'{symbol} is not in the scan universe; market and country are required when adding this holding')
    market,country=validate_market_country(market,country)
    rows.append({'symbol':symbol,'market':market,'country':country,'enabled':'true'})
    write_csv(path,rows,fields)


def apply_parameter_change(cfg, defaults, path_key, raw_value):
    path_key=str(path_key or '')
    if path_key not in defaults:
        raise ValueError(f'Parameter is not editable: {path_key}')
    meta=defaults[path_key]
    value=float(raw_value)
    if value < float(meta['min']) or value > float(meta['max']):
        raise ValueError(f'Parameter outside allowed range: {path_key}')
    if float(meta.get('step',1)).is_integer() and value.is_integer():
        value=int(value)
    parts=path_key.split('.'); target=cfg
    for key in parts[:-1]:
        target=target[key]
    target[parts[-1]]=value


if action in ('add_symbol','remove_symbol'):
    path = ROOT/'config/symbols.csv'; fields=['symbol','market','country','enabled']; rows=read_csv(path); symbol=clean_symbol(req.get('symbol'))
    rows=[r for r in rows if r.get('symbol','').upper()!=symbol]
    if action=='add_symbol':
        market,country=validate_market_country(req.get('market'),req.get('country'))
        rows.append({'symbol':symbol,'market':market,'country':country,'enabled':'true'})
    write_csv(path,rows,fields)

elif action in ('add_holding','remove_holding'):
    path=portfolio_path(str(req.get('portfolio',''))); fields=['symbol','name','quantity','average_price','account']; rows=read_csv(path); symbol=clean_symbol(req.get('symbol'))
    rows=[r for r in rows if r.get('symbol','').upper()!=symbol]
    if action=='add_holding':
        ensure_scannable_symbol(symbol)
        name=str(req.get('name','')).strip()[:100]
        rows.append({'symbol':symbol,'name':name,'quantity':'','average_price':'','account':''})
    write_csv(path,rows,fields)

elif action in ('set_parameter','set_parameters'):
    defaults=json.loads((ROOT/'config/parameter_defaults.json').read_text(encoding='utf-8'))
    path=ROOT/'config/parameters.json'; cfg=json.loads(path.read_text(encoding='utf-8'))
    if action=='set_parameter':
        changes=[{'path':req.get('path'),'value':req.get('value')}]
    else:
        changes=req.get('changes')
        if not isinstance(changes,list) or not changes:
            raise ValueError('No parameter changes supplied')
        if len(changes)>100:
            raise ValueError('Too many parameter changes')
    seen=set()
    for change in changes:
        if not isinstance(change,dict):
            raise ValueError('Invalid parameter change')
        path_key=str(change.get('path',''))
        if path_key in seen:
            raise ValueError(f'Duplicate parameter change: {path_key}')
        seen.add(path_key)
        apply_parameter_change(cfg,defaults,path_key,change.get('value'))
    path.write_text(json.dumps(cfg,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
else:
    raise ValueError('Unsupported action')

print(f'Applied {action}')
