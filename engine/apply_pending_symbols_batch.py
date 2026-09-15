import csv, json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
path=ROOT/'config/symbols.csv'
pending=json.loads((ROOT/'config/pending_symbols_batch.json').read_text())['symbols']
with path.open(encoding='utf-8-sig',newline='') as f: rows=list(csv.DictReader(f))
by={r['symbol'].upper():r for r in rows}
for item in pending:
    s=item['symbol'].upper()
    by[s]={'symbol':s,'market':item['market'],'country':item['country'],'enabled':'true'}
with path.open('w',encoding='utf-8',newline='') as f:
    w=csv.DictWriter(f,fieldnames=['symbol','market','country','enabled']); w.writeheader(); w.writerows(by.values())
print('Added/updated:', ', '.join(x['symbol'] for x in pending))
