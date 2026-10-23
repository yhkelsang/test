import datetime as dt
import importlib.util
import json
from pathlib import Path
import tempfile
import threading
import unittest
import urllib.request
import urllib.error
import io
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('radar',Path(__file__).resolve().parents[1]/'radar.py')
r=importlib.util.module_from_spec(spec);spec.loader.exec_module(r)
class RadarTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();r.DB_PATH=Path(self.tmp.name)/'test.sqlite3';r.init()
 def tearDown(self):self.tmp.cleanup()
 def add(self,title,kind='trend',source='访谈A',published=None):
  return r.add_signal({'title':title,'topic':'design','kind':kind,'source':source,'body':'用户明确说明需要酒店景观设计，正在询价。','published':published or r.now()})
 def design(self):return next(o for o in r.snapshot()['opportunities'] if o['topic']=='design')
 def test_fresh_install_is_hypothesis(self):
  s=r.snapshot();self.assertEqual(s['total_signals'],0);self.assertEqual(len(s['opportunities']),5);self.assertTrue(all(o['score']==0 for o in s['opportunities']))
 def test_dedup_and_evidence_cap(self):
  self.assertEqual(self.add('一个案例'),1);self.assertEqual(self.add('一个案例'),0)
  for i in range(30):self.add(f'热度线索{i}')
  self.assertEqual(self.design()['score'],25)
 def test_strong_evidence_independence_cap(self):
  for i in range(4):self.add(f'委托{i}','request')
  self.assertEqual(self.design()['score'],55)
  self.add('另一个买家','paid','访谈B');self.assertEqual(self.design()['score'],97)
 def test_old_evidence_excluded(self):
  self.add('旧需求','paid',published=(dt.datetime.now(dt.timezone.utc)-dt.timedelta(days=40)).isoformat());self.assertEqual(self.design()['score'],0)
 def test_invalid_claim_and_link_rejected(self):
  with self.assertRaises(ValueError):r.add_signal({'title':'求购','source':'test','kind':'paid','body':'嗯'})
  with self.assertRaises(ValueError):r.valid_url('javascript:alert(1)')
  with self.assertRaises(ValueError):r.public_url('https://127.0.0.1/feed')
 def test_rss_atom_and_entities(self):
  feed=b'<rss><channel><item><title>Garden demand</title><link>https://example.com/post</link><description>hello</description><pubDate>Fri, 23 Oct 2026 08:00:00 GMT</pubDate></item></channel></rss>'
  items=r.parse_feed(feed);self.assertEqual(len(items),1);self.assertEqual(items[0]['url'],'https://example.com/post')
  atom=b'<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>Design</title><link href="https://example.com/a"/><updated>2026-10-23T08:00:00Z</updated></entry></feed>'
  self.assertEqual(r.parse_feed(atom)[0]['url'],'https://example.com/a')
  with self.assertRaises(ValueError):r.parse_feed(b'<!DOCTYPE foo><rss/>')
 def test_collection_ingestion_dedup_and_failure_status(self):
  with r.connect() as c:source=dict(c.execute('SELECT * FROM sources LIMIT 1').fetchone())
  payload=b'<rss><channel><item><title>Hotel landscape demand</title><link>https://example.com/p</link></item></channel></rss>'
  class Opener:
   def open(self,*args,**kwargs):return io.BytesIO(payload)
  with patch.object(r,'public_url',return_value=source['url']),patch.object(r.urllib.request,'build_opener',return_value=Opener()):
   self.assertEqual(r.fetch_source(source)['added'],1);self.assertEqual(r.fetch_source(source)['added'],0)
  self.assertEqual(r.snapshot()['signals'][0]['kind'],'trend')
  self.assertTrue(r.snapshot()['sources'][0]['last_ok'])
  with patch.object(r,'public_url',side_effect=urllib.error.URLError('测试：网络不可用')):
   self.assertEqual(r.fetch_source(source)['added'],0)
  self.assertIn('网络不可用',r.snapshot()['sources'][0]['error'])
  self.assertTrue(r.snapshot()['sources'][0]['last_ok'])
 def test_api_full_workflow_and_origin_rejection(self):
  server=r.ThreadingHTTPServer(('127.0.0.1',0),r.Handler);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start();base=f'http://127.0.0.1:{server.server_port}'
  def post(path,data,origin=None):
   headers={'Content-Type':'application/json'}
   if origin:headers['Origin']=origin
   req=urllib.request.Request(base+path,data=json.dumps(data).encode(),headers=headers)
   with urllib.request.urlopen(req) as result:return json.load(result)
  try:
   post('/api/signals',{'title':'概念设计需求','topic':'design','source':'访谈A','kind':'request','body':'希望做民宿庭院概念方案，预算需要进一步确认。'})
   o=self.design();post('/api/opportunity',{'id':o['id'],'stage':'presell','price':1200,'inquiries':2,'orders':1,'revenue':500,'cost':80})
   o=self.design();self.assertEqual(o['revenue'],500);self.assertEqual(o['profit'],420);self.assertEqual(o['stage'],'presell')
   with urllib.request.urlopen(base+'/api/report') as response:self.assertIn('500.00',response.read().decode())
   with self.assertRaises(urllib.error.HTTPError) as e:post('/api/signals',{'title':'x'},'https://evil.example')
   self.assertEqual(e.exception.code,403)
   post('/api/signal/delete',{'id':r.snapshot()['signals'][0]['id']});self.assertEqual(self.design()['score'],0)
  finally:server.shutdown();server.server_close();thread.join()
if __name__=='__main__':unittest.main(verbosity=2)
