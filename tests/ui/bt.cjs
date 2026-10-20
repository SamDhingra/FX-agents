/* Backtester page: catalog, run list, result (gates, equity, histogram, tables) and a trade on the chart. node tests/ui/bt.cjs
   bt_fixture.json is real API output (vol_breakout_v1 no-bias variant on synthetic gold, generated through the app). */
const {chromium}=require('playwright');const fs=require('node:fs');const path=require('node:path');const assert=require('node:assert/strict');
const {state,api}=require('./fixture.cjs');
const F=JSON.parse(fs.readFileSync(path.join(__dirname,'bt_fixture.json'),'utf8'));
(async()=>{
const browser=await chromium.launch({headless:true,executablePath:process.env.CHROMIUM_PATH||undefined});
const out=path.resolve(process.env.OUT||'docs/ui-review');fs.mkdirSync(out,{recursive:true});const errors=[];const posted=[];
for(const vp of [{width:390,height:844},{width:1366,height:900}]){
const ctx=await browser.newContext({viewport:vp});const page=await ctx.newPage();
page.on('pageerror',e=>errors.push(e.stack));page.on('console',m=>{if(m.type()==='error')errors.push('console: '+m.text())});
page.on('dialog',d=>d.accept());
await page.route('**/*',r=>{const u=new URL(r.request().url());
 if(u.pathname.startsWith('/lib/'))return r.fulfill({contentType:'application/javascript',body:fs.readFileSync('fxagents/dashboard/static'+u.pathname)});
 if(u.pathname==='/')return r.fulfill({contentType:'text/html',body:fs.readFileSync('fxagents/dashboard/static/index.html','utf8')});
 if(u.pathname==='/api/bt')return r.fulfill({json:F.catalog});
 if(u.pathname==='/api/bt/run'){posted.push(JSON.parse(r.request().postData()));return r.fulfill({json:{id:F.run.run.id}});}
 if(u.pathname.startsWith('/api/bt/run/'))return r.fulfill({json:F.run});
 if(u.pathname==='/api/bt/bars')return r.fulfill({json:F.bars});
 return r.fulfill({json:api(r.request().url())})});
await page.routeWebSocket('**/ws*',ws=>{setTimeout(()=>ws.send(JSON.stringify(state)),30)});
await page.goto('http://fx-ui.test/#bt');await page.waitForTimeout(900);
if(errors.length)console.error(errors.join('\n'));const opts=await page.locator('#bxPlugin option').allTextContents();
assert(opts.includes('vol_breakout_v1')&&opts.includes('h4_donchian_trend_v1'),'plugins: '+opts);
await page.selectOption('#bxPlugin','vol_breakout_v1.py');await page.waitForTimeout(100);
assert((await page.locator('#bxParams').inputValue()).includes('"box_bars": 12'),'params prefilled');
assert((await page.locator('#bxRuns').textContent()).includes('queued'),'queued run listed');
// vault selection shows why it is closed
await page.selectOption('#bxData','vault');await page.waitForTimeout(100);
assert((await page.locator('#bxVault').textContent()).includes('Vault closed'),'vault note');
await page.selectOption('#bxData','seen');
// run with one changed parameter → only the override is sent
await page.locator('#bxParams').fill((await page.locator('#bxParams').inputValue()).replace('"box_bars": 12','"box_bars": 10'));
await page.click('#bxRun');await page.waitForTimeout(900);
assert.deepEqual(posted.at(-1),{plugin:'vol_breakout_v1.py',dataset:'seen',symbol:'XAUUSD',params:{box_bars:10}});
const res=await page.locator('#bxResult').textContent();
assert(res.includes('no pass')&&res.includes('≥ 100 trades')&&res.includes('Look-ahead audit')&&res.includes('Funnel'),'result: '+res.slice(0,400));
assert(await page.locator('#bxEq canvas').count()>0,'equity chart');
assert(await page.locator('#bxHist rect').count()===36,'histogram');
await page.locator('#bxTrades tbody tr').first().click();await page.waitForTimeout(1200);
assert(await page.locator('#bxTradeChart canvas').count()>0,'trade chart');
const note=await page.locator('#bxTradeNote').textContent();
assert(/1-minute candles/.test(note)&&/spread/.test(note),'trade note: '+note);
await page.click('#bxSortSeg button[data-s="worst"]');await page.waitForTimeout(200);
const rs=(await page.locator('#bxTrades tbody tr td:last-child').allTextContents()).slice(0,3).map(x=>parseFloat(x.replace('−','-')));
assert(rs[0]<=rs[1]&&rs[1]<=rs[2],'sorted worst first: '+rs);
assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),'horizontal overflow at '+vp.width);
await page.locator('#p-bt').screenshot({path:path.join(out,`bt-${vp.width}.png`)});
await ctx.close();}
await browser.close();if(errors.length){console.error(errors.join('\n'));process.exit(1)}console.log('bt ok');
})();
