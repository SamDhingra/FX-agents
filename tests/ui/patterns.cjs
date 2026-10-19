/* chart pattern overlay on the trade chart and the full-screen chart. node tests/ui/patterns.cjs */
const {chromium}=require('playwright');const fs=require('node:fs');const path=require('node:path');const assert=require('node:assert/strict');
const {state,api}=require('./fixture.cjs');
const B=i=>new Date(Date.parse('2026-10-13T10:42:00-04:00')-3*3600000+i*60000).toISOString();
const pats=[{kind:'double_top',dir:-1,label:'Double top',status:'confirmed',t0:B(10),t1:B(70),t_break:B(90),
  segs:[[B(10),2664.5,B(40),2657],[B(40),2657,B(70),2664.6],[B(40),2657,B(90),2657]],target:2650},
 {kind:'bull_flag',dir:1,label:'Bull flag',status:'forming',t0:B(95),t1:B(130),t_break:null,segs:[[B(95),2658,B(110),2666],[B(111),2667,B(130),2665],[B(111),2664,B(130),2662]],target:null},
 {kind:'rising_wedge',dir:-1,label:'Rising wedge',status:'failed',t0:B(5),t1:B(60),t_break:B(65),segs:[[B(5),2660,B(60),2668],[B(5),2655,B(60),2665]],target:null}];
(async()=>{
const browser=await chromium.launch({headless:true,executablePath:process.env.CHROMIUM_PATH||undefined});
const out=path.resolve(process.env.OUT||'docs/ui-review');fs.mkdirSync(out,{recursive:true});const errors=[];let calls=0;
const ctx=await browser.newContext({viewport:{width:390,height:844}});const page=await ctx.newPage();
page.on('pageerror',e=>errors.push(e.stack));page.on('console',m=>{if(m.type()==='error')errors.push('console: '+m.text())});
await page.route('**/*',r=>{const u=new URL(r.request().url());
 if(u.pathname.startsWith('/lib/'))return r.fulfill({contentType:'application/javascript',body:fs.readFileSync('fxagents/dashboard/static'+u.pathname)});
 if(u.pathname==='/')return r.fulfill({contentType:'text/html',body:fs.readFileSync('fxagents/dashboard/static/index.html','utf8')});
 if(u.pathname.endsWith('/api/patterns')){calls++;return r.fulfill({json:{tf:+u.searchParams.get('tf'),patterns:pats}});}
 return r.fulfill({json:api(r.request().url())})});
await page.routeWebSocket('**/ws*',ws=>{setTimeout(()=>ws.send(JSON.stringify(state)),30)});
await page.goto('http://fx-ui.test/');await page.waitForTimeout(600);
await page.evaluate(()=>go('trades'));await page.waitForTimeout(400);await page.locator('#trades [data-i]').first().click();await page.waitForTimeout(1000);
await page.waitForFunction(()=>RP&&RP.view&&RP.view.candles>0);
const M=()=>page.evaluate(()=>RP.view.markers.join('|'));let svg=await M();
assert(!svg.includes('Double top'),'patterns off by default');assert((await page.locator('#replay .patbtn').textContent())==='Patterns');
await page.locator('#replay .patbtn').click();await page.waitForTimeout(600);svg=await M();
assert(svg.includes('Double top ✓'),'double top drawn');assert(svg.includes('Bull flag …'),'forming flag drawn');
assert(!svg.includes('Rising wedge'),'failed patterns hidden by default');
assert((await page.locator('#replay .patlist').textContent()).includes('Double top · confirmed'));
await page.locator('#replay').screenshot({path:path.join(out,'v9-patterns-replay.png')});
await page.locator('#replay .patbtn').click();await page.waitForTimeout(400);
svg=await M();assert(!svg.includes('Double top'),'toggle off hides');
assert(await page.evaluate(()=>localStorage.getItem('fx-patterns2'))==='off','remembered');
await page.locator('#replay .patbtn').click();await page.waitForTimeout(500);
assert((await M()).includes('Double top'),'toggle back on');
await page.locator('#lwFullBtn').click();await page.waitForTimeout(900);
assert((await page.evaluate(()=>LF.lw.view.markers.join('|'))).includes('Double top'),'full screen shows patterns');
assert(await page.locator('#lwFull .patbtn').count()===1,'full-screen toggle');
await page.screenshot({path:path.join(out,'v9-patterns-full.png')});
assert(calls>=3,'patterns fetched per view/candle size');
await browser.close();if(errors.length){console.error(errors.join('\n'));process.exit(1)}console.log('patterns ok');
})();
