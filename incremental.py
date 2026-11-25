"""Conservative review routing; never authorizes publication."""
import re

def load_entries(ledger):
    if ledger.get('schema_version') != 1 or not isinstance(ledger.get('entries'), dict) or not ledger['entries']:
        raise ValueError('Missing or unsupported review ledger')
    for key, entry in ledger['entries'].items():
        if entry.get('candidate_id') != key or entry.get('disposition') not in {'ADD','UPDATE','ALREADY PUBLISHED','DUPLICATE','EXCLUDE','DEFER'}:
            raise ValueError('Invalid ledger entry: '+key)
    return ledger['entries']

def route(key, candidate, entry, fingerprint):
    if entry is None: return 'NEW', []
    if any(candidate.get(k)!=entry.get(k) for k in ('official_id','source_url','title')):
        return 'METADATA_CHANGED', []
    if entry.get('quarantined'): return 'QUARANTINE_REOPEN_REVIEW', []
    old=entry.get('source_fingerprints',[])
    if not old or not any(d.get('url')==candidate['source_url'] for d in old): return 'BASELINE_INCOMPLETE', []
    checked=[]
    for d in old:
        url=d.get('url'); expected=d.get('sha256','')
        if not url or not re.fullmatch('[0-9a-f]{64}',expected): return 'BASELINE_INCOMPLETE',checked
        try: actual=fingerprint(url)
        except Exception as e: return 'MONITOR_ERROR',checked+[{'url':url,'error':str(e)}]
        checked.append({'url':url,'sha256':actual})
        if actual!=expected: return 'SOURCE_CHANGED',checked
    return ('DEFERRED_UNCHANGED' if entry['disposition']=='DEFER' else 'REVIEWED_UNCHANGED'),checked
