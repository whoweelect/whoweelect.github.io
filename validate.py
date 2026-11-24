import json
from pathlib import Path
from urllib.parse import urlparse
root=Path(__file__).parent
rows=json.loads((root/'officials.json').read_text()); evidence=json.loads((root/'evidence.json').read_text())
ids={r['id'] for r in rows}; assert len(ids)==len(rows) and rows
for r in rows:
 for k in ('id','name','district','office','party','state','level','source','review','identity_checked'): assert isinstance(r[k],str) and r[k]
for e in evidence:
 assert e['official_id'] in ids and e['approval']=='approved'
 for k in ('id','title','category','authority','event_date','status','outcome','summary','source','verified_date'): assert isinstance(e[k],str) and e[k]
 u=urlparse(e['source']); assert u.scheme=='https' and u.hostname and (u.hostname.endswith('.gov') or u.hostname.endswith('.mil'))
assert len({e['id'] for e in evidence})==len(evidence)
print(f'Validated {len(rows)} officials and {len(evidence)} evidence entries; structural checks only.')
