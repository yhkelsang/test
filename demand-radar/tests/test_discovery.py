import datetime as dt
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import urllib.error
import discovery
import radar

class DiscoveryTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.old=radar.DB_PATH;radar.DB_PATH=Path(self.tmp.name)/'radar.sqlite3';radar.init()
 def tearDown(self):radar.DB_PATH=self.old;self.tmp.cleanup()
 def task(self):
  with radar.connect() as c:return dict(c.execute('SELECT * FROM search_tasks LIMIT 1').fetchone())
 def run_items(self,items,task=None):
  with patch.object(discovery,'search',return_value=items):return discovery.run(task or self.task(),radar.connect,radar.now,None,None,radar.clean)
 def item(self,**overrides):
  return {'title':'民宿庭院寻找景观设计师，预算需要沟通','summary':'希望找人完成庭院概念方案，请有经验的设计师提供报价。','url':'https://example.com/project/1?utm_source=feed','published':None,**overrides}
 def test_seller_recruiting_and_closed_filtered(self):
  for t in ['承接景观设计效果图，欢迎咨询','景观设计师招聘','庭院设计招标中标公告','低价接单 景观外包','景观设计外包平台推荐']:
   self.assertIsNone(discovery.classify(t,'','design'),t)
  self.assertIsNotNone(discovery.classify('民宿寻找庭院设计师','预算 3000 元','landscape'))
  self.assertEqual(discovery.classify('酒店景观设计采购公告','','design')['category'],'tender')
 def test_automatic_save_dedup_and_no_fabricated_dates(self):
  self.assertEqual(self.run_items([self.item()])['added'],1)
  self.assertEqual(self.run_items([self.item(url='https://example.com/project/1?utm_source=other')])['added'],0)
  s=radar.snapshot();self.assertEqual(len(s['leads']),1);self.assertEqual(s['leads'][0]['published'],None)
  self.assertEqual(s['signals'],[]);self.assertTrue(all(o['score']==0 for o in s['opportunities']))
 def test_old_results_not_treated_as_new_requests(self):
  old=(dt.datetime.now(dt.timezone.utc)-dt.timedelta(days=90)).isoformat()
  result=self.run_items([self.item(published=old)]);self.assertEqual(result['added'],0);self.assertEqual(result['filtered'],1)
 def test_failure_is_not_zero_results(self):
  with patch.object(discovery,'search',side_effect=urllib.error.URLError('403 Forbidden')):
   result=discovery.run(self.task(),radar.connect,radar.now,None,None,radar.clean)
  self.assertIn('403',result['error']);self.assertIsNone(result['total'])
  stored=self.task();self.assertIn('403',stored['error']);self.assertIsNotNone(stored['last_run']);self.assertIsNone(stored['last_total'])
  result=self.run_items([]);self.assertIsNone(result['error']);self.assertEqual(result['total'],0)
  stored=self.task();self.assertIsNone(stored['error']);self.assertEqual(stored['last_total'],0);self.assertIsNotNone(stored['last_ok'])
 def test_migration_preserves_edits_and_rejected_leads(self):
  self.run_items([self.item()])
  with radar.connect() as c:
   c.execute("UPDATE search_tasks SET query='自定义关键词',enabled=0 WHERE id=1")
   c.execute("UPDATE leads SET status='dismissed'")
  radar.init();self.assertEqual(len(radar.snapshot()['search_tasks']),6);self.assertEqual(self.task()['query'],'自定义关键词');self.assertEqual(self.task()['enabled'],0)
  self.run_items([self.item()]);self.assertEqual(radar.snapshot()['leads'][0]['status'],'dismissed')
 def test_rss_transport_and_html_rejection(self):
  payload=b'<rss><channel><item><title>garden</title><description>request</description><link>https://example.com/request</link></item></channel></rss>'
  class Opener:
   def open(self,request,timeout):
    self.url=request.full_url;return io.BytesIO(payload)
  opener=Opener()
  with patch.dict(os.environ,{'RADAR_SEARCH_PROVIDER':'bing'}):items=discovery.search(self.task(),opener,lambda _:None,radar.clean)
  self.assertIn('/search?',opener.url);self.assertNotIn('/news/',opener.url);self.assertIsNone(items[0]['published'])
  payload=b'<html><body>blocked</body></html>'
  with self.assertRaises(ValueError):discovery.search(self.task(),opener,lambda _:None,radar.clean)
 def test_brave_api_requires_key_not_silent_switch(self):
  with patch.dict(os.environ,{'RADAR_SEARCH_PROVIDER':'brave','BRAVE_SEARCH_API_KEY':''}):
   with self.assertRaises(ValueError):discovery.search(self.task(),None,None,None)
 def test_collect_discovers_without_manual_entry(self):
  with radar.connect() as c:c.execute('UPDATE sources SET enabled=0')
  with patch.object(discovery,'search',return_value=[self.item()]):result=radar.collect()
  self.assertFalse(result['busy']);self.assertEqual(result['added'],1)
  self.assertEqual(len(radar.snapshot()['leads']),1);self.assertEqual(radar.snapshot()['signals'],[])
 def test_shared_link_associated_with_multiple_tasks(self):
  self.run_items([self.item()]);task=self.task();task['id']=2
  self.run_items([self.item()],task);self.assertEqual(radar.snapshot()['leads'][0]['matches'],[1,2])
if __name__=='__main__':unittest.main(verbosity=2)
