/* Run: node tests/ui/smoke.cjs (requires Playwright + installed Chromium).
   All HTTP and WebSocket traffic is intercepted. Never connects to a broker. */
const {chromium}=require('playwright');
const fs=require('node:fs');const path=require('node:path');const assert=require('node:assert/strict');
const {state,trades,api}=require('./fixture.cjs');
(async()=>{
const options={headless:true};if(process.env.CHROMIUM_PATH){options.executablePath=process.env.CHROMIUM_PATH;options.args=['--no-sandbox','--disable-dev-shm-usage'];}
const browser=await chromium.launch(options);const errors=[];const posts=[];
const out=path.resolve('docs/ui-review');fs.mkdirSync(out,{recursive:true});
for(const width of [1440,390,768]){
 const context=await browser.newContext({viewport:{width,height:width===390?844:1000},colorScheme:'light'});
 const page=await context.newPage();let socket;page.on('pageerror',e=>errors.push(e.stack));
 await page.route('**/*',async route=>{
  const req=route.request(),u=new URL(req.url());
  if(u.pathname.startsWith('/lib/'))return route.fulfill({contentType:'application/javascript',body:fs.readFileSync('fxagents/dashboard/static'+u.pathname)});
  if(u.pathname==='/')return route.fulfill({contentType:'text/html',body:fs.readFileSync('fxagents/dashboard/static/index.html','utf8')});
  if(req.method()==='POST'){posts.push(u.pathname);return route.fulfill({json:{ok:true}})}
  return route.fulfill({json:api(req.url())});
 });
 await page.routeWebSocket('**/ws*',ws=>{socket=ws;const book=new URL(ws.url()).searchParams.get('book')||'live';setTimeout(()=>ws.send(JSON.stringify({...state,book})),30)});
 await page.goto('http://fx-ui.test/');await page.waitForFunction(()=>document.querySelector('#hero').textContent.includes('71,482'));
 await page.waitForTimeout(300);await page.screenshot({animations:'disabled',path:path.join(out,`overview-${width}.png`),fullPage:true});
 assert(await page.locator('#pause').isEnabled());
 await page.locator('#flatten').click();await page.locator('#controlDialog button[value=cancel]').click();assert.equal(posts.length,0);
 await page.locator('#flatten').click();await page.locator('#confirmFlatten').click();await page.waitForTimeout(400);assert.equal(posts.pop(),'/api/control/flatten');
 await page.locator('#pause').click();await page.waitForTimeout(400);assert.equal(posts.pop(),'/api/control/pause');
 for(const dest of ['trades','calendar','compare','playbook','strategies','backtests','news','agents']){
  await page.evaluate(dest=>go(dest),dest);await page.waitForTimeout(110);
  assert.equal(await page.locator('.page.on').getAttribute('id'),'p-'+dest);
  assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),`overflow ${dest} at ${width}`);
  if(dest==='trades'){
   await page.locator('#tradeSearch').fill('XAUUSD');assert.equal(await page.locator('#trades [data-i]').count(),4);
   await page.locator('#tradeSort').selectOption('best');await page.locator('#trades [data-i]').first().click();await page.waitForTimeout(50);assert(await page.locator('#drawer').evaluate(x=>x.classList.contains('on')));
   await page.keyboard.press('Escape');await page.waitForTimeout(80);assert(!(await page.locator('#drawer').evaluate(x=>x.classList.contains('on'))));
   await page.locator('#tradeSearch').fill('');await page.locator('#tradeSearch').blur();await page.evaluate(()=>document.querySelector('#toasts').replaceChildren());await page.waitForTimeout(300);await page.screenshot({animations:'disabled',path:path.join(out,`trades-${width}.png`),fullPage:true});
  }
 }
 await page.evaluate(()=>go('home'));await page.locator('#theme').click();await page.waitForTimeout(300);await page.screenshot({animations:'disabled',path:path.join(out,`dark-${width}.png`),fullPage:true});
 await page.locator('#bookBtn').click();await page.locator('[data-b="playbook"]').click();await page.waitForTimeout(100);assert(await page.locator('#pause').isHidden());assert((await page.locator('#bookName').textContent()).includes('Playbook'));
 await page.locator('#bookBtn').click();await page.locator('[data-b="live"]').click();await page.waitForTimeout(100);
 await page.evaluate(()=>{LAST_RECEIVED=Date.now()-20000;freshness()});assert(await page.locator('#pause').isDisabled());assert(await page.locator('#connectionBanner').isVisible());assert.equal(await page.locator('#status').textContent(),'Status unverified');
 await page.evaluate(s=>receive({...s,positions:[],equity_curve:[],trading_enabled:false,halt_reason:'Paused for review'}),state);assert((await page.locator('#positions').textContent()).includes('No open positions'));assert(await page.locator('#equityEmpty').isVisible());
 await page.locator('#pause').click();await page.waitForTimeout(400);assert.equal(posts.pop(),'/api/control/resume');
 if(width===390){await page.locator('.tabbar [data-p=more]').click();await page.locator('#moreSheet [data-p=news]').click();assert.equal(await page.locator('.page.on').getAttribute('id'),'p-news');}
 await context.close();
}
await browser.close();assert.deepEqual(errors,[]);console.log('PASS: 9 pages at 1440, 390 and 768 px; search, sort, trade drawer, themes, book switching, pause/resume, cancel/confirm flatten, stale and empty states. No browser errors.');
})().catch(e=>{console.error(e);process.exit(1)});
