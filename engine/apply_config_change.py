import csv, io, json, os, re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BODY = os.environ.get('ISSUE_BODY', '')

m = re.search(r'```json\s*(\{.*?\})\s*```', BODY, re.S)
if not m:
    raise SystemExit('No configuration JSON found in issue body')
req = json.loads(m.group(1))
action = req.get('action')


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


def portfolio_path(pid):
    data = json.loads((ROOT/'config/portfolios.json').read_text(encoding='utf-8'))
    for p in data:
        if p['id'] == pid and p.get('active', True):
            path = (ROOT/p['file']).resolve()
            if ROOT not in path.parents:
                raise ValueError('Invalid portfolio path')
            return path
    raise ValueError('Unknown portfolio')

if action in ('add_symbol','remove_symbol'):
    path = ROOT/'config/symbols.csv'; fields=['symbol','market','country','enabled']; rows=read_csv(path); symbol=clean_symbol(req.get('symbol'))
    rows=[r for r in rows if r.get('symbol','').upper()!=symbol]
    if action=='add_symbol':
        market=str(req.get('market','')).strip().upper(); country=str(req.get('country','')).strip().upper()
        allowed={'XTSE','XTSX','XCNQ','XNYS','XNAS','ARCX','XASE','BATS','NEOE'}
        if market not in allowed or country not in {'CA','US',''}: raise ValueError('Invalid market/country')
        rows.append({'symbol':symbol,'market':market,'country':country,'enabled':'true'})
    write_csv(path,rows,fields)

elif action in ('add_holding','remove_holding'):
    path=portfolio_path(str(req.get('portfolio',''))); fields=['symbol','name','quantity','average_price','account']; rows=read_csv(path); symbol=clean_symbol(req.get('symbol'))
    rows=[r for r in rows if r.get('symbol','').upper()!=symbol]
    if action=='add_holding':
        name=str(req.get('name','')).strip()[:100]
        rows.append({'symbol':symbol,'name':name,'quantity':'','average_price':'','account':''})
    write_csv(path,rows,fields)

elif action=='set_parameter':
    path_key=str(req.get('path','')); value=req.get('value')
    defaults=json.loads((ROOT/'config/parameter_defaults.json').read_text(encoding='utf-8'))
    if path_key not in defaults: raise ValueError('Parameter is not editable')
    meta=defaults[path_key]; value=float(value)
    if value < float(meta['min']) or value > float(meta['max']): raise ValueError('Parameter outside allowed range')
    if float(meta.get('step',1)).is_integer() and value.is_integer(): value=int(value)
    path=ROOT/'config/parameters.json'; cfg=json.loads(path.read_text(encoding='utf-8'))
    parts=path_key.split('.'); target=cfg
    for key in parts[:-1]: target=target[key]
    target[parts[-1]]=value
    path.write_text(json.dumps(cfg,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
else:
    raise ValueError('Unsupported action')

print(f'Applied {action}')
