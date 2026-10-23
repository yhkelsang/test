"""Optional UI check. Requires Playwright and a system Chromium; uses a temporary DB."""
import os
from pathlib import Path
import socket
import subprocess
import tempfile
import time
import urllib.request
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory() as tmp:
 with socket.socket() as sock:
  sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
 process=subprocess.Popen(['python3',str(ROOT/'radar.py'),'serve','--no-auto-collect','--port',str(port)],env={**os.environ,'RADAR_DB':str(Path(tmp)/'radar.sqlite3')},stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
 try:
  base=f'http://127.0.0.1:{port}'
  for _ in range(100):
   try:
    urllib.request.urlopen(base+'/api/state',timeout=1);break
   except Exception:time.sleep(.05)
  with sync_playwright() as p:
   browser=p.chromium.launch(headless=True,executable_path='/usr/bin/chromium',args=['--no-sandbox'])
   page=browser.new_page(viewport={'width':1440,'height':1100});errors=[]
   page.on('pageerror',lambda e:errors.append(str(e)))
   page.goto(base);page.wait_for_selector('.card');assert page.locator('.card').count()==5
   page.click('#newSignal');page.fill('[name=title]','测试线索：酒店希望做概念设计 <script>alert(1)</script>')
   page.select_option('[name=kind]','request');page.select_option('#formTopic','design');page.fill('[name=source]','测试访谈A');page.fill('[name=body]','这是一条临时测试证据，用户需要景观概念方案并希望先沟通报价。')
   page.click('#signalForm button[type=submit], #signalForm .full');page.wait_for_selector('#signalDialog',state='hidden')
   page.locator('[data-page=signals]').click();page.wait_for_selector('.signal');assert page.locator('.signal').count()==1;assert page.locator('.signal script').count()==0
   page.fill('#search','不存在的查询');assert page.locator('.signal').count()==0;page.fill('#search','酒店');assert page.locator('.signal').count()==1
   page.locator('[data-page=overview]').click();page.locator('[data-detail]').filter(has_text='查看').first.click()
   page.select_option('#opForm [name=stage]','presell');page.fill('#opForm [name=inquiries]','3');page.fill('#opForm [name=revenue]','600');page.fill('#opForm [name=cost]','100');page.click('#opForm .full');page.wait_for_selector('#detailDialog',state='hidden')
   page.reload();page.wait_for_selector('.card');assert '¥600' in page.locator('#stats').inner_text()
   # Confirm task editing and discovery-to-follow-up without manual evidence entry.
   page.locator('[data-page=sources]').click();page.wait_for_selector('[data-task-edit]');assert page.locator('[data-task-edit]').count()==6
   page.locator('[data-task-edit]').first.click();page.fill('#taskForm [name=query]','苏州 民宿 找设计师 -招聘');page.click('#taskForm button[type=submit], #taskForm .primary');page.wait_for_function("document.querySelector('#taskList').innerText.includes('苏州 民宿 找设计师')")
   # Seed an explicit test fixture in the temporary DB, never user data.
   import sqlite3
   with sqlite3.connect(str(Path(tmp)/'radar.sqlite3')) as c:
    c.execute("INSERT INTO leads(title,summary,url,topic,category,score,reason,query,discovered) VALUES(?,?,?,?,?,?,?,?,?)",('测试夹具：民宿寻找庭院设计师','这是测试数据，不是真实市场线索','https://example.com/test-demand','landscape','buyer',60,'测试匹配理由','测试关键词','2026-10-23T08:00:00+00:00'))
   page.reload();page.wait_for_selector('.auto-lead');assert '原文日期未知' in page.locator('.auto-lead').inner_text()
   page.click('[data-lead][data-status=saved]');page.wait_for_selector('.auto-lead',state='hidden');page.select_option('#leadFilter','saved');page.wait_for_selector('.auto-lead')
   page.reload();page.wait_for_selector('.card');page.select_option('#leadFilter','saved');page.wait_for_selector('.auto-lead')
   page.click('[data-lead][data-status=dismissed]');page.wait_for_selector('.auto-lead',state='hidden');page.select_option('#leadFilter','dismissed');page.wait_for_selector('.auto-lead');page.click('[data-lead][data-status=new]');page.wait_for_selector('.auto-lead',state='hidden')
   page.locator('[data-page=sources]').click()
   with page.expect_download() as dl:page.click('#report')
   assert dl.value.suggested_filename=='demand-radar-report.md'
   page.locator('[data-page=signals]').click();page.on('dialog',lambda d:d.accept());page.click('[data-delete]');page.wait_for_selector('.signal',state='hidden')
   page.locator('[data-page=overview]').click();assert not errors,errors
   page.screenshot(path='/workspace/outputs/demand-radar-desktop.png',full_page=True)
   mobile=browser.new_page(viewport={'width':390,'height':844},is_mobile=True,has_touch=True)
   mobile.goto(base);mobile.wait_for_selector('.card')
   assert mobile.evaluate('document.documentElement.scrollWidth <= window.innerWidth'), 'Mobile horizontal overflow'
   mobile.click('#newSignal');assert mobile.locator('#signalDialog').is_visible();mobile.locator('#signalDialog .close').click()
   mobile.screenshot(path='/workspace/outputs/demand-radar-mobile.png',full_page=True)
   browser.close();print('PASS: desktop/mobile, safe rendering, entry/search/delete, persisted follow-up, report download; no browser errors.')
 finally:process.terminate();process.wait(timeout=5)
