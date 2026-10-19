/* trade analyst (shadow): verdict on the position card, on the trade's timeline, and the scorecard on Agents. node tests/ui/analyst.cjs */
const {chromium}=require('playwright');const fs=require('node:fs');const path=require('node:path');const assert=require('node:assert/strict');
const {state,trades,api}=require('./fixture.cjs');
const sc={n_trades:14,checks:[{check:'any_exit',label:'any exit advice',kind:'exit',n:14,avg_value_r:0.12,lo:-0.05,hi:0.3,helped:0.57},
 {check:'structure_break',label:'5m structure broke',kind:'exit',n:9,avg_value_r:0.2,lo:0.01,hi:0.41,helped:0.66}],
 recent:[{ts:'2026-10-19T10:05:00-04:00',pos_id:'a',symbol:'XAUUSD',strategy:'trend_pullback:15m@x',verdict:'exit',checks:['structure_break'],r_now:0.4,r_if_exit:0.35,why:'5m structure broke'}]};
(async()=>{
const browser=await chromium.launch({headless:true,executablePath:process.env.CHROMIUM_PATH||undefined});
const out=path.resolve(process.env.OUT||'docs/ui-review');fs.mkdirSync(out,{recursive:true});const errors=[];
const ctx=await browser.newContext({viewport:{width:390,height:844}});const page=await ctx.newPage();
page.on('pageerror',e=>errors.push(e.stack));page.on('console',m=>{if(m.type()==='error')errors.push('console: '+m.text())});
const st={...state,positions:state.positions.map((p,i)=>i===0?{...p,analyst:{verdict:'exit',checks:['structure_break','h1_against'],ts:'2026-10-19T10:05:00-04:00'}}:p)};
await page.route('**/*',r=>{const u=new URL(r.request().url());
 if(u.pathname.startsWith('/lib/'))return r.fulfill({contentType:'application/javascript',body:fs.readFileSync('fxagents/dashboard/static'+u.pathname)});
 if(u.pathname==='/')return r.fulfill({contentType:'text/html',body:fs.readFileSync('fxagents/dashboard/static/index.html','utf8')});
 if(u.pathname.endsWith('/api/analyst'))return r.fulfill({json:sc});
 if(u.pathname.endsWith('/api/trades'))return r.fulfill({json:trades.map((t,i)=>i===0?{...t,events:[...(t.events||[]),{ts:'2026-10-13T10:05:00-04:00',kind:'analyst',verdict:'exit',why:'5m structure broke',r:0.4,shadow:true}]}:t)});
 return r.fulfill({json:api(r.request().url())})});
await page.routeWebSocket('**/ws*',ws=>{setTimeout(()=>ws.send(JSON.stringify(st)),30)});
await page.goto('http://fx-ui.test/');await page.waitForTimeout(700);
const card=await page.locator('#positions .pcard').first().textContent();
assert(card.includes('Analyst: would exit')&&card.includes('5m structure broke')&&card.includes('1H trend against'),'card verdict: '+card);
await page.locator('#positions').screenshot({path:path.join(out,'analyst-card.png')});
await page.evaluate(()=>go('trades'));await page.waitForTimeout(400);await page.locator('#trades [data-i]').first().click();await page.waitForTimeout(900);
{const d=await page.locator('#drawer').textContent();assert(d.includes('analyst (shadow)')&&d.includes('would exit — 5m structure broke'),'timeline entry: '+d.slice(-600));}
await page.keyboard.press('Escape');await page.waitForTimeout(300);
await page.evaluate(()=>go('agents'));await page.waitForTimeout(700);
const body=await page.locator('#anlBody').textContent();
assert(body.includes('5m structure broke')&&body.includes('+0.20R')&&body.includes('14 closed trades'),'scorecard: '+body.slice(0,300));
await page.locator('#anlBody').screenshot({path:path.join(out,'analyst-scorecard.png')});
assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),'overflow');
await browser.close();if(errors.length){console.error(errors.join('\n'));process.exit(1)}console.log('analyst ok');
})();
