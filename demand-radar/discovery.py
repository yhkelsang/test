"""Automatic public-web discovery. No login scraping; heuristic leads are unverified."""
import datetime as dt
import email.utils
import json
import os
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

DEFAULT_TASKS=[
 ('民宿 / 庭院找设计师','民宿 庭院 找设计师 -招聘 -接单','landscape'),
 ('庭院设计求助','庭院 求推荐 设计师 -招聘 -承接','landscape'),
 ('景观效果图外包','景观 效果图 外包 需求 -招聘 -接单','design'),
 ('酒店概念方案采购','酒店 景观 概念设计 采购 招标公告','design'),
 ('民宿摄影委托','民宿 寻找 摄影师 -招聘 -接单','photo'),
 ('插画定制委托','插画 约稿 需求 -招聘 -接稿','art'),
]
DEMAND=[r'找.{0,10}(设计师|设计团队|摄影师|插画师|画师)',r'(求|寻找|需要|求推荐).{0,15}(设计|方案|效果图|摄影|插画|画师)',r'(景观|效果图|庭院|设计).{0,10}(外包|委托|采购)',r'(招标公告|采购公告|征集公告|约稿需求|求约稿|征稿启事)']
SELLER=[r'承接.{0,12}(设计|效果图|摄影|插画|业务)',r'(专业提供|我们提供|欢迎咨询|接单中|接稿中|长期接稿|低价接单|接单平台|外包平台|服务商推荐)']
CLOSED=['中标公告','成交公告','结果公告','已结束','已找到','已解决','终止公告','废标公告','招聘','诚聘','求职']

def classify(title,summary,topic):
 t=re.sub(r'\s+',' ',title+' '+summary)
 relevant={'landscape':['景观','庭院','民宿','酒店','花园','园林'],'design':['景观','庭院','民宿','酒店','效果图','概念方案','园林'],'photo':['摄影','拍摄','照片'],'art':['插画','画师','装饰画','壁画','约稿','绘画'],'reading':['空间','品牌','策划','文案']}
 if not any(x in t for x in relevant.get(topic,[])):return None
 if any(x in title for x in ['教程','攻略','案例欣赏','课程','如何选择','怎么选择']):return None
 if any(x in title for x in CLOSED):return None
 if any(re.search(p,title) for p in SELLER):return None
 matches=[m.group(0) for p in DEMAND for m in re.finditer(p,t)]
 if not matches:return None
 if any(re.search(p,t) for p in SELLER) and not any(re.search(p,title) for p in DEMAND):return None
 tender=any(x in t for x in ['招标公告','采购公告','征集公告'])
 score=min(90,45+len(set(matches))*8+(10 if re.search(r'预算|[¥￥]|\d+\s*(元|万元)',t) else 0))
 return {'category':'tender' if tender else 'buyer','score':score,'reason':'公开标题/摘要包含：'+ '、'.join(dict.fromkeys(matches))[:180]+('。可能需要资质，须核对截止日期。' if tender else '。这是自动识别的意向，尚未核实客户和项目。')}

def canonical_url(url):
 p=urllib.parse.urlsplit(url)
 if p.scheme not in ('https','http') or not p.hostname or p.username or p.password:raise ValueError('结果链接无效')
 query=urllib.parse.parse_qsl(p.query,keep_blank_values=True)
 query=[(k,v) for k,v in query if not k.lower().startswith('utm_') and k.lower() not in ('spm','fbclid','gclid')]
 return urllib.parse.urlunsplit((p.scheme.lower(),p.netloc.lower(),p.path,urllib.parse.urlencode(sorted(query)),''))

def parsed_date(value):
 if not value:return None
 try: stamp=email.utils.parsedate_to_datetime(value)
 except (TypeError,ValueError):
  try:stamp=dt.datetime.fromisoformat(value.replace('Z','+00:00'))
  except (TypeError,ValueError):return None
 if stamp.tzinfo is None:stamp=stamp.replace(tzinfo=dt.timezone.utc)
 return stamp.astimezone(dt.timezone.utc).isoformat()

def search(task,opener,validate,clean):
 provider=os.environ.get('RADAR_SEARCH_PROVIDER','bing').lower()
 headers={'User-Agent':'PersonalDemandRadar/2.0 (public search RSS reader)'}
 if provider=='brave':
  token=os.environ.get('BRAVE_SEARCH_API_KEY','').strip()
  if not token:raise ValueError('Brave 搜索未配置 API 密钥，请在本机设置 BRAVE_SEARCH_API_KEY；不要在聊天或 GitHub 填写')
  url='https://api.search.brave.com/res/v1/web/search?'+urllib.parse.urlencode({'q':task['query'],'count':10,'search_lang':'zh-hans'})
  headers['X-Subscription-Token']=token
 elif provider=='bing':
  url='https://www.bing.com/search?'+urllib.parse.urlencode({'q':task['query'],'format':'rss','mkt':'zh-CN'})
 else:raise ValueError('未知搜索提供方，请使用 bing 或 brave')
 validate(url)
 with opener.open(urllib.request.Request(url,headers=headers),timeout=15) as response:
  payload=response.read(2_000_001)
 if len(payload)>2_000_000:raise ValueError('搜索响应超过 2 MB')
 if provider=='brave':
  data=json.loads(payload)
  if 'web' not in data:raise ValueError('搜索 API 未返回网页结果，不能视为零需求')
  return [{'title':clean(x.get('title'),240),'summary':clean(x.get('description')),'url':x.get('url',''),'published':parsed_date(x.get('page_age'))} for x in data['web'].get('results',[])][:20]
 if b'<!DOCTYPE' in payload.upper() or b'<!ENTITY' in payload.upper():raise ValueError('搜索未返回可用 RSS（可能被拦截或接口改变）')
 root=ET.fromstring(payload)
 if root.tag != 'rss':raise ValueError('搜索未返回 RSS，不能视为零需求')
 out=[]
 for item in root.findall('.//item')[:20]:
  def value(tag):return item.findtext(tag,'')
  out.append({'title':clean(value('title'),240),'summary':clean(value('description')),'url':value('link'),'published':parsed_date(value('pubDate'))})
 return out

def init(c):
 c.executescript('''
 CREATE TABLE IF NOT EXISTS search_tasks(id INTEGER PRIMARY KEY,name TEXT NOT NULL,query TEXT UNIQUE NOT NULL,topic TEXT NOT NULL,enabled INTEGER NOT NULL DEFAULT 1,last_run TEXT,last_ok TEXT,error TEXT,last_total INTEGER,last_filtered INTEGER,last_added INTEGER);
 CREATE TABLE IF NOT EXISTS leads(id INTEGER PRIMARY KEY,title TEXT NOT NULL,summary TEXT NOT NULL,url TEXT UNIQUE NOT NULL,topic TEXT NOT NULL,category TEXT NOT NULL,score INTEGER NOT NULL,reason TEXT NOT NULL,query TEXT NOT NULL,published TEXT,discovered TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'new');
 CREATE TABLE IF NOT EXISTS lead_matches(lead_id INTEGER NOT NULL,task_id INTEGER NOT NULL,PRIMARY KEY(lead_id,task_id));
 CREATE TABLE IF NOT EXISTS radar_meta(key TEXT PRIMARY KEY,value TEXT NOT NULL);
 ''')
 # One-time migration, not reinserted after user edits keywords.
 if not c.execute("SELECT 1 FROM radar_meta WHERE key='search_defaults_v2'").fetchone():
  for name,query,topic in DEFAULT_TASKS:c.execute('INSERT OR IGNORE INTO search_tasks(name,query,topic) VALUES(?,?,?)',(name,query,topic))
  c.execute("INSERT INTO radar_meta VALUES('search_defaults_v2','done')")

def run(task,connect,now,opener,validate,clean):
 added=filtered=0;total=None;error=None
 try:
  items=search(task,opener,validate,clean);total=len(items)
  with connect() as c:
   for item in items:
    verdict=classify(item['title'],item['summary'],task['topic'])
    if not verdict:filtered+=1;continue
    published=item.get('published')
    if published:
     age=(dt.datetime.now(dt.timezone.utc)-dt.datetime.fromisoformat(published)).total_seconds()
     if age>30*86400 or age < -86400:filtered+=1;continue
    try:url=canonical_url(item['url'])
    except ValueError:filtered+=1;continue
    cur=c.execute('INSERT OR IGNORE INTO leads(title,summary,url,topic,category,score,reason,query,published,discovered) VALUES(?,?,?,?,?,?,?,?,?,?)',(item['title'],item['summary'],url,task['topic'],verdict['category'],verdict['score'],verdict['reason'],task['query'],published,now()))
    added+=cur.rowcount
    row=c.execute('SELECT id FROM leads WHERE url=?',(url,)).fetchone()
    c.execute('INSERT OR IGNORE INTO lead_matches VALUES(?,?)',(row['id'],task['id']))
 except Exception as e:error=(type(e).__name__+': '+str(e))[:300]
 with connect() as c:
  c.execute('UPDATE search_tasks SET last_run=?,last_ok=CASE WHEN ? IS NULL THEN ? ELSE last_ok END,error=?,last_total=?,last_filtered=?,last_added=? WHERE id=?',(now(),error,now(),error,total,filtered,added,task['id']))
 return {'source':'自动搜索 · '+task['name'],'added':added,'error':error,'total':total,'filtered':filtered,'type':'search'}
