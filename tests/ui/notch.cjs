/* iPhone home-screen app with a translucent status bar that reports no safe-area inset: the top bar (and Appearance)
   must sit below the status bar, scroll with the page, and Appearance must also be reachable from the page heading. */
const {chromium}=require('playwright');const fs=require('node:fs');const path=require('node:path');const assert=require('node:assert/strict');
const {state,api}=require('./fixture.cjs');
(async()=>{
const browser=await chromium.launch({headless:true,executablePath:process.env.CHROMIUM_PATH||undefined});const errors=[];
const out=path.resolve(process.env.OUT||'docs/ui-review');fs.mkdirSync(out,{recursive:true});
const ctx=await browser.newContext({viewport:{width:393,height:852},screen:{width:393,height:852},isMobile:true,hasTouch:true,deviceScaleFactor:3,
  userAgent:'Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148'});
await ctx.addInitScript(()=>Object.defineProperty(navigator,'standalone',{get:()=>true}));
const page=await ctx.newPage();page.on('pageerror',e=>errors.push(e.stack));
await page.route('**/*',r=>{const u=new URL(r.request().url());if(u.pathname==='/')return r.fulfill({contentType:'text/html',body:fs.readFileSync('fxagents/dashboard/static/index.html','utf8')});return r.fulfill({json:api(r.request().url())})});
await page.routeWebSocket('**/ws*',ws=>setTimeout(()=>ws.send(JSON.stringify(state)),30));
await page.goto('http://fx-ui.test/');await page.waitForTimeout(500);
assert.equal(await page.evaluate(()=>getComputedStyle(document.documentElement).getPropertyValue('--sat').trim()),'54px');
const top=await page.locator('.top').boundingBox();assert(top.y>=54,'top bar below the status bar: '+top.y);
const ap=await page.locator('#appearance').boundingBox();assert(ap.y>=54);
await page.screenshot({path:path.join(out,'notch-top.png')});
await page.evaluate(()=>window.scrollTo(0,800));await page.waitForTimeout(100);
assert((await page.locator('.top').boundingBox()).y<0,'top bar scrolls away instead of sitting under the island');
await page.evaluate(()=>window.scrollTo(0,0));await page.waitForTimeout(100);
await page.locator('#appearance').click();await page.waitForTimeout(200);assert(await page.locator('#appearanceDialog').evaluate(d=>d.open));
const back=await page.locator('#appearanceDialog [data-dlgback]').boundingBox();assert(back.y>=54,'Back below the island');
await page.screenshot({path:path.join(out,'notch-appearance.png')});
await page.locator('#appearanceDialog [data-dlgback]').click();await page.waitForTimeout(150);
await page.locator('#moreAppearance').evaluate(b=>b.click());await page.waitForTimeout(150);assert(await page.locator('#appearanceDialog').evaluate(d=>d.open),'More → Appearance');
await browser.close();if(errors.length){console.error(errors.join('\n'));process.exit(1)}console.log('notch ok');
})();
