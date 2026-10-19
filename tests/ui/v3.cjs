/* v3 panels: screenshots + error/overflow checks. node tests/ui/v3.cjs  (synthetic fixtures; no network) */
const {chromium}=require('playwright');const fs=require('node:fs');const path=require('node:path');const assert=require('node:assert/strict');
const {state,trades,api}=require('./fixture.cjs');
(async()=>{
const browser=await chromium.launch({headless:true,executablePath:process.env.CHROMIUM_PATH||undefined});
const out=path.resolve(process.env.OUT||'docs/ui-review');fs.mkdirSync(out,{recursive:true});const errors=[];
for(const [width,scheme] of [[1440,'dark'],[390,'light'],[390,'dark']]){
 const ctx=await browser.newContext({viewport:{width,height:width===390?844:1000},colorScheme:scheme});const page=await ctx.newPage();
 page.on('pageerror',e=>errors.push(width+': '+e.stack));page.on('console',m=>{if(m.type()==='error')errors.push(width+' console: '+m.text())});
 await page.route('**/*',r=>{const u=new URL(r.request().url());if(u.pathname.startsWith('/lib/'))return r.fulfill({contentType:'application/javascript',body:fs.readFileSync('fxagents/dashboard/static'+u.pathname)});if(u.pathname==='/')return r.fulfill({contentType:'text/html',body:fs.readFileSync('fxagents/dashboard/static/index.html','utf8')});return r.fulfill({json:api(r.request().url())})});
 let sock;await page.routeWebSocket('**/ws*',ws=>{sock=ws;setTimeout(()=>ws.send(JSON.stringify(state)),30)});
 await page.goto('http://fx-ui.test/');await page.waitForTimeout(700);
 const tag=`${width}-${scheme}`;
 await page.screenshot({path:path.join(out,`v3-home-${tag}.png`),fullPage:true});
 assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),'overflow home '+tag);
 await page.evaluate(()=>go('agents'));await page.waitForTimeout(300);
 for(let k=0;k<6;k++){const t=Date.now()/1000;const ev=['bar','bar_1m','entry_request','decision','position_opened','position_updated','alert','clock'].map((tp,i)=>({t:t+i*.01,topic:tp,symbol:'XAUUSD'}));
  state.flow.events.push(...ev);sock.send(JSON.stringify(state));await page.waitForTimeout(350);}
 await page.locator('#mcSvg .node[data-n="risk"]').click();await page.waitForTimeout(500);
 await page.screenshot({path:path.join(out,`v3-agents-${tag}.png`),fullPage:true});
 assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),'overflow agents '+tag);
 await page.evaluate(()=>go('compare'));await page.waitForTimeout(600);await page.locator('#evBody .evrow').nth(1).click();await page.waitForTimeout(200);
 await page.screenshot({path:path.join(out,`v3-compare-${tag}.png`),fullPage:true});
 assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),'overflow compare '+tag);
 assert((await page.locator('#scBody').textContent()).includes('Bias rule'));
 await page.evaluate(()=>go('backtests'));await page.waitForTimeout(300);await page.locator('#journey .jrow').first().click();
 await page.screenshot({path:path.join(out,`v3-journey-${tag}.png`),fullPage:true});
 await page.evaluate(()=>go('trades'));await page.waitForTimeout(400);await page.locator('#trades [data-i]').first().click();await page.waitForTimeout(900);
 assert((await page.locator('#court').textContent()).includes('Risk'));await page.waitForFunction(()=>RP&&RP.view&&RP.view.candles>50);
 await page.locator('#drawer').screenshot({path:path.join(out,`v3-trade-${tag}.png`)});
 assert(await page.evaluate(()=>RP.ghosts.length)>=3,'ghosts');
 await page.locator('#lwPlay').click();await page.waitForTimeout(2500);
 await page.keyboard.press('Escape');await page.waitForTimeout(200);
 await page.locator('#askFab').click();await page.waitForTimeout(200);await page.locator('#askIdeas button').first().click();await page.waitForTimeout(600);
 assert((await page.locator('#askLog').textContent()).includes('bias rule'));
 await page.screenshot({path:path.join(out,`v4-ask-${tag}.png`)});await page.evaluate(()=>document.querySelector('#askDialog').close());
 await ctx.close();
}
await browser.close();
if(errors.length){console.error(errors.join('\n'));process.exit(1)}console.log('v3 ok');
})();
