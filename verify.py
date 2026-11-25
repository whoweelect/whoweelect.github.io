from identity import name_present
from incremental import load_entries, route
from adapters import quarantine
import os
import json, hashlib, pathlib, re, subprocess, tempfile, datetime, shutil
from urllib.error import URLError
from http.client import HTTPException
from urllib.parse import urlsplit,urljoin,urlunsplit
from urllib.request import Request,build_opener,HTTPRedirectHandler
from html.parser import HTMLParser
P=pathlib.Path('.')
class NoRedirect(HTTPRedirectHandler):
 def redirect_request(self,*a,**k): return None
class Page(HTMLParser):
 def __init__(self): super().__init__(); self.links=[]; self.text=[]; self.skip=0
 def handle_starttag(self,t,a):
  if t in ('script','style'): self.skip+=1
  if t=='a': self.links.append(dict(a).get('href',''))
 def handle_endtag(self,t):
  if t in ('script','style'): self.skip=max(0,self.skip-1)
 def handle_data(self,d):
  if not self.skip:self.text.append(d)
def normalize(u,hosts):
 p=urlsplit(u)
 if p.netloc.lower() in ('www.gpo.gov','gpo.gov') and p.path.startswith('/fdsys/pkg/'):
  p=urlsplit('https://www.govinfo.gov/content/pkg/'+p.path.removeprefix('/fdsys/pkg/'))
 if p.scheme not in ('http','https') or p.netloc.lower() not in hosts: raise ValueError('Unapproved source host')
 return urlunsplit(('https',p.netloc.lower(),p.path,p.query,''))
class ApprovedRedirect(HTTPRedirectHandler):
 def __init__(self,hosts): self.hosts=hosts
 def redirect_request(self,req,fp,code,msg,headers,newurl):
  return super().redirect_request(req,fp,code,msg,headers,normalize(urljoin(req.full_url,newurl),self.hosts))
def fetch(u,hosts,max_bytes=100000000):
 u=normalize(u,hosts)
 with build_opener(ApprovedRedirect(hosts)).open(Request(u,headers={'User-Agent':'WhoWeElect research/1.1'}),timeout=45) as r:
  normalize(r.geturl(),hosts)
  b=r.read(max_bytes+1)
  if len(b)>max_bytes:raise ValueError('Document too large')
  return b
def digest(b):return hashlib.sha256(b).hexdigest()
def save(name,obj):
 p=P/name; tmp=p.with_suffix('.tmp'); tmp.write_text(json.dumps(obj,indent=2,ensure_ascii=False)+'\n');tmp.replace(p)
def classify(text,rules):
 return [k for k,patterns in rules.items() if any(re.search(p,text,re.I) for p in patterns)]
def run(fetcher=fetch):
 if not shutil.which('pdftotext'): raise RuntimeError('Required dependency pdftotext is missing')
 rules=json.loads((P/'verification_rules.json').read_text()); hosts=rules['hosts']; history=json.loads((P/'candidate-history.json').read_text()); roster=json.loads(fetcher(rules['roster'],['raw.githubusercontent.com'])); ids={r['id']:r for r in roster}; queue=[]; quarantined=[]; groups={}; errors=[]; archive=P/'verification-documents';archive.mkdir(exist_ok=True)
 pdf_cache={}; extracted={}; unique_hashes=set()
 if fetcher is fetch:
  fetcher=lambda u,h:fetch(u,h,rules.get('max_document_bytes',100000000))
 mode=os.environ.get("VERIFY_MODE","incremental")
 if mode not in ("full","incremental"): raise ValueError("Unsupported verification mode")
 entries=load_entries(json.loads((P/"review-ledger.json").read_text())) if mode=="incremental" else {}
 monitoring=[]; hash_cache={}
 def fingerprint(url):
  if url not in hash_cache: hash_cache[url]=digest(fetcher(url,hosts))
  return hash_cache[url]
 selected=set(history)
 for key,c in sorted(history.items()):
  if key not in selected: continue
  row={'candidate_id':key,'official_id':c['official_id'],'name':c['name'],'source_url':c['source_url'],'title':c['title'],'status':'requires_human_review','publication_allowed':False,'documents':[],'issues':[],'possible_event_types':[]}
  official=ids.get(c['official_id']); row['roster_match']=bool(official and official['name'].casefold()==c['name'].casefold())
  if not row['roster_match']:row['issues'].append('Roster identifier/name mismatch')
  reason=quarantine(c,roster) or c.get('quarantine_reason')
  if not row['roster_match']: reason=reason or 'Roster identifier/name mismatch'
  if reason:
   row['issues'].append(reason); row['status']='quarantined'; quarantined.append(row); monitoring.append({'candidate_id':key,'route':'QUARANTINED','reason':reason}); continue
  if mode=='incremental':
   decision,checked=route(key,c,entries.get(key),fingerprint)
   monitoring.append({'candidate_id':key,'route':decision,'checked':checked})
   if decision in ('REVIEWED_UNCHANGED','DEFERRED_UNCHANGED'): continue
   row['incremental_reason']=decision
   if decision=='MONITOR_ERROR': row['issues'].append('Prior source monitoring failed; review required')
  try:
   b=fetcher(c['source_url'],hosts); h=digest(b);
   if b.startswith(b'%PDF-'):
    f=archive/(h+'.pdf'); f.write_bytes(b); unique_hashes.add(h)
    row['documents'].append({'url':c['source_url'],'sha256':h,'file':f.name})
    result=subprocess.run(['pdftotext','-layout',str(f),'-'],capture_output=True,timeout=90,check=True); txt=result.stdout.decode('utf-8','replace'); (archive/(h+'.txt')).write_text(txt)
    row['documents'][0]['text_file']=h+'.txt'; row['possible_event_types']=classify(txt,rules['patterns']); row['excerpt']=txt[:12000]; row['name_in_page']=name_present(c['name'],txt)
    if not txt.strip(): row['issues'].append('PDF needs manual transcription')
    links=[]
   else:
    pass
   if not b.startswith(b'%PDF-'):
    (archive/(h+'.html')).write_bytes(b); page=Page();page.feed(b.decode('utf-8','replace')); body=' '.join(' '.join(page.text).split()); row['documents'].append({'url':c['source_url'],'sha256':h,'file':h+'.html'}); row['name_in_page']=name_present(c['name'],body); row['possible_event_types']=classify(body,rules['patterns']); row['excerpt']=body[:12000]
    links=sorted({urljoin(c['source_url'],u).split('#')[0] for u in page.links if urlsplit(urljoin(c['source_url'],u)).path.lower().endswith('.pdf')});
    if len(links)>12:row['issues'].append('Attachment limit reached')
   for u in links[:12]:
    try:
     u=normalize(u,hosts)
     pdf=pdf_cache[u].read_bytes() if u in pdf_cache else fetcher(u,hosts)
     if not pdf.startswith(b'%PDF-'):raise ValueError('Not PDF')
     h=digest(pdf); unique_hashes.add(h); f=archive/(h+'.pdf');
     if not f.exists(): f.write_bytes(pdf)
     pdf_cache[u]=f
     d={'url':u,'sha256':h,'file':f.name};row['documents'].append(d)
     if h not in extracted:
      result=subprocess.run(['pdftotext','-layout',str(f),'-'],capture_output=True,timeout=90,check=True); txt=result.stdout.decode('utf-8','replace'); (archive/(h+'.txt')).write_text(txt); extracted[h]=txt
     txt=extracted[h];d['text_file']=h+'.txt';d['possible_event_types']=classify(txt,rules['patterns'])
     if not txt.strip():row['issues'].append('PDF needs manual transcription: '+u)
    except (URLError, HTTPException, TimeoutError, ConnectionError, ValueError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:row['issues'].append('Attachment failure: '+u+' '+str(e));errors.append({'candidate_id':key,'url':u,'error':str(e)})
   if not links and not b.startswith(b'%PDF-'):row['issues'].append('No direct PDF links found; check underlying report manually')
  except (URLError, HTTPException, TimeoutError, ConnectionError, ValueError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:row['issues'].append('Source retrieval failed: '+str(e));errors.append({'candidate_id':key,'url':c['source_url'],'error':str(e)})
  if not row.get('name_in_page'): row['issues'].append('Name reference not confirmed in primary document')
  queue.append(row);groups.setdefault(c['official_id'],[]).append({'candidate_id':key,'source_url':c['source_url'],'title':c['title'],'first_seen':c.get('first_seen')})
 source_count=sum(bool(r['documents']) for r in queue)
 warning_count=sum(bool(r['issues']) for r in queue)
 critical=bool(queue and not source_count)
 status='failed' if critical else ('success_with_warnings' if warning_count else 'success')
 from collections import Counter
 save('incremental-report.json',{'mode':mode,'inventory_total':len(history),'routing_counts':dict(Counter(r['route'] for r in monitoring)),'ledger_entries_missing_from_inventory':sorted(set(entries)-set(history)),'publication_allowed':False,'monitoring':monitoring})
 save('quarantine.json',quarantined);save('review_queue.json',queue);save('case_history.json',{'status':'provisional official-level groups, not confirmed cases','groups':groups});save('verification-report.json',{'time':datetime.datetime.now(datetime.timezone.utc).isoformat(),'candidates':len(queue),'inventory_total':len(history),'quarantined':len(quarantined),'mode':mode,'retrieval_errors':len(errors),'approved':0,'error_details':errors,'unique_pdfs':len(unique_hashes),'status':status,'candidates_with_issues':warning_count,'sources_retrieved':source_count});print(f'{len(queue)} candidates prepared; {len(errors)} retrieval errors; 0 approved')
 if critical: print('::error::No candidate source pages could be retrieved')
 elif warning_count: print(f'::warning::{warning_count} candidates require follow-up; see verification-report.json and review_queue.json')
 return 1 if critical else 0
if __name__=='__main__':raise SystemExit(run())
