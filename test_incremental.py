import unittest
from incremental import route,load_entries
class Routing(unittest.TestCase):
 def test_routes(self):
  c={'official_id':'a','source_url':'https://example.gov/a','title':'title'}
  e={**c,'candidate_id':'x','disposition':'ADD','source_fingerprints':[{'url':c['source_url'],'sha256':'a'*64}]}
  self.assertEqual(route('x',c,e,lambda u:'a'*64)[0],'REVIEWED_UNCHANGED')
  self.assertEqual(route('x',c,{**e,'disposition':'DEFER'},lambda u:'a'*64)[0],'DEFERRED_UNCHANGED')
  self.assertEqual(route('x',c,e,lambda u:'b'*64)[0],'SOURCE_CHANGED')
  self.assertEqual(route('x',c,None,lambda u:None)[0],'NEW')
  self.assertEqual(route('x',c,{**e,'quarantined':True},lambda u:None)[0],'QUARANTINE_REOPEN_REVIEW')
  self.assertEqual(route('x',c,{**e,'source_fingerprints':[]},lambda u:None)[0],'BASELINE_INCOMPLETE')
  self.assertEqual(route('x',{**c,'title':'new'},e,lambda u:None)[0],'METADATA_CHANGED')
  def fail(u): raise OSError('offline')
  self.assertEqual(route('x',c,e,fail)[0],'MONITOR_ERROR')
  self.assertEqual(load_entries({'schema_version':1,'entries':{'x':e}})['x'],e)
  with self.assertRaises(ValueError): load_entries({})
if __name__=='__main__':unittest.main()
