/* TradingView button in the trade view: copies the Pine script and links the right chart. node tests/ui/tradingview.cjs */
const {chromium}=require('playwright');const fs=require('node:fs');const assert=require('node:assert/strict');
const {state,api}=require('./fixture.cjs');
(async()=>{
const browser=await chromium.launch({headless:true,executablePath:process.env.CHROMIUM_PATH||undefined});const errors=[];
const ctx=await browser.newContext({viewport:{width:390,height:844},permissions:['clipboard-read','clipboard-write']});const page=await ctx.newPage();
page.on('pageerror',e=>errors.push(e.stack));
const pine='//@version=6\nindicator("FX-Agents · XAUUSD · live (2 trades)", overlay=true)';
await page.route('**/*',r=>{const u=new URL(r.request().url());
 if(u.pathname==='/')return r.fulfill({contentType:'text/html',body:fs.readFileSync('fxagents/dashboard/static/index.html','utf8')});
 if(u.pathname.endsWith('/api/tradingview'))return r.fulfill({json:{symbol:u.searchParams.get('symbol'),tv_symbol:'OANDA:XAUUSD',script:pine}});
 return r.fulfill({json:api(r.request().url())})});
await page.routeWebSocket('**/ws*',ws=>{setTimeout(()=>ws.send(JSON.stringify(state)),30)});
await page.goto('http://fx-ui.test/');await page.waitForTimeout(600);
await page.evaluate(()=>go('trades'));await page.waitForTimeout(400);await page.locator('#trades [data-i]').first().click();await page.waitForTimeout(700);
await page.locator('#dTv').click();await page.waitForTimeout(500);
const txt=await page.locator('#tvBox').textContent();
assert(/Script copied|Copy the script/.test(txt),'box: '+txt);
assert((await page.locator('#tvBox a').getAttribute('href')).includes('OANDA%3AXAUUSD'),'chart link');
const clip=await page.evaluate(()=>navigator.clipboard?navigator.clipboard.readText().catch(()=>''):'');if(!clip)assert((await page.locator('#tvBox textarea').inputValue()).startsWith('//@version=6'),'fallback textarea');
assert(clip===''||clip.startsWith('//@version=6'),'clipboard holds the script');
await browser.close();if(errors.length){console.error(errors.join('\n'));process.exit(1)}console.log('tradingview ok');
})();
