"""Directory import only. Aggregated sources are not official verification."""
import csv, io, json, datetime, pathlib, urllib.request
ROOT=pathlib.Path(__file__).parent
STATES=dict(zip('AL AK AZ AR CA CO CT DE FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY DC AS GU MP PR VI'.split(), 'Alabama|Alaska|Arizona|Arkansas|California|Colorado|Connecticut|Delaware|Florida|Georgia|Hawaii|Idaho|Illinois|Indiana|Iowa|Kansas|Kentucky|Louisiana|Maine|Maryland|Massachusetts|Michigan|Minnesota|Mississippi|Missouri|Montana|Nebraska|Nevada|New Hampshire|New Jersey|New Mexico|New York|North Carolina|North Dakota|Ohio|Oklahoma|Oregon|Pennsylvania|Rhode Island|South Carolina|South Dakota|Tennessee|Texas|Utah|Vermont|Virginia|Washington|West Virginia|Wisconsin|Wyoming|District of Columbia|American Samoa|Guam|Northern Mariana Islands|Puerto Rico|U.S. Virgin Islands'.split('|')))
def get(url):
 with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'WhoWeElect directory pilot'}),timeout=30) as r:
  b=r.read(20_000_001)
  if len(b)>20_000_000: raise ValueError('oversized response')
  return b.decode('utf-8-sig')
def row(id,name,state,office,district,party,source,level):
 return dict(id=id,name=name,state=state,office=office,district=district,party=party or 'Not supplied',source=source,level=level,review='Not yet reviewed',identity_checked='Not independently verified',imported_on=str(datetime.date.today()))
def main():
 old=json.loads((ROOT/'officials.json').read_text()); evidence=json.loads((ROOT/'evidence.json').read_text()); rows=[]; errors=[]
 federal='https://raw.githubusercontent.com/unitedstates/congress-legislators/main/legislators-current.json'
 try:
  for p in json.loads(get(federal)):
   t=p['terms'][-1]; s=t['state']; office={'rep':'House','sen':'Senate'}[t['type']]; district=f'{s}-{t.get("district",0):02}' if office=='House' else 'Statewide'; n=p['name']; name=n.get('official_full') or n['first']+' '+n['last']; rows.append(row('bioguide-'+p['id']['bioguide'],name,STATES[s],office,district,t.get('party'), 'https://bioguide.congress.gov/search/bio/'+p['id']['bioguide'],'Federal'))
  if not 500<=len(rows)<=550: raise ValueError('unexpected federal count')
 except Exception as e:
  print('Federal import failed:',e); raise SystemExit(1)
 for s,state in list(STATES.items())[:50]:
  url=f'https://data.openstates.org/people/current/{s.lower()}.csv'
  try:
   batch=[]
   for p in csv.DictReader(io.StringIO(get(url))):
    chamber=p['current_chamber']; office={'upper':'State Senate','lower':'State House','legislature':'State Legislature'}.get(chamber)
    if not office: continue
    batch.append(row(p['id'],p['name'],state,office,p.get('current_district') or 'Not supplied',p.get('current_party'),url,'State'))
   if not 20<=len(batch)<=500: raise ValueError('unexpected state count')
   rows.extend(batch)
  except Exception as e:
   errors.append(f'{state}: {e}'); rows.extend(r for r in old if r['level']=='State' and r['state']==state)
 # Preserve original IDs for exact matching existing Ohio profiles; do not orphan published evidence.
 def key(r): return (r['level'],r['state'],r['office'],r['district'])
 oldkeys={key(r):r for r in old};
 for r in rows:
  o=oldkeys.get(key(r))
  if o and o['name'].casefold()==r['name'].casefold(): r['id']=o['id']; r['review']=o['review']; r['identity_checked']=o['identity_checked']
 if len({r['id'] for r in rows})!=len(rows): raise ValueError('duplicate IDs')
 if not {e['official_id'] for e in evidence}<={r['id'] for r in rows}: raise ValueError('would orphan evidence; manual reconciliation required')
 (ROOT/'officials.json').write_text(json.dumps(rows,indent=2)+'\n'); (ROOT/'coverage.json').write_text(json.dumps({'imported':str(datetime.date.today()),'count':len(rows),'errors':errors,'limitations':'Aggregated roster sources; executive offices not included; no accountability review implied.'},indent=2)+'\n'); print(len(rows),'profiles;',len(errors),'state import failures'); print('\n'.join(errors))
if __name__=='__main__': main()
