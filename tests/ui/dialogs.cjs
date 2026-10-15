/* Phone dialogs (Appearance, Ask the bot): fully on screen, scroll inside, Back button and phone back close them,
   the page behind can't scroll. node tests/ui/dialogs.cjs */
const {chromium}=require('playwright');const fs=require('node:fs');const path=require('node:path');const assert=require('node:assert/strict');
const {state,api}=require('./fixture.cjs');
(async()=>{
const browser=await chromium.launch({headless:true,executablePath:process.env.CHROMIUM_PATH||undefined});const errors=[];
const out=path.resolve(process.env.OUT||'docs/ui-review');fs.mkdirSync(out,{recursive:true});
const ctx=await browser.newContext({viewport:{width:390,height:844},isMobile:true,hasTouch:true,deviceScaleFactor:2});
const page=await ctx.newPage();page.on('pageerror',e=>errors.push(e.stack));
await page.route('**/*',r=>{const u=new URL(r.request().url());if(u.pathname==='/')return r.fulfill({contentType:'text/html',body:fs.readFileSync('fxagents/dashboard/static/index.html','utf8')});return r.fulfill({json:api(r.request().url())})});
await page.routeWebSocket('**/ws*',ws=>setTimeout(()=>ws.send(JSON.stringify(state)),30));
await page.goto('http://fx-ui.test/');await page.waitForTimeout(500);
await page.evaluate(()=>window.scrollTo(0,600));await page.waitForTimeout(100);           // opened from a scrolled page
const onScreen=async sel=>{const b=await page.locator(sel).boundingBox();return b&&b.y>=0&&b.y+b.height<=844&&b.x>=0&&b.x+b.width<=390};
// Appearance from the top bar
await page.locator('#appearance').click();await page.waitForTimeout(250);
assert(await onScreen('#appearanceDialog [data-dlgback]'),'appearance Back visible');
assert(await page.locator('#appearanceDialog').evaluate(d=>d.classList.contains('sheetdlg')&&!d.matches(':modal')),'phone uses a plain panel, not a modal');
const ad=page.locator('#appearanceDialog');const sh=await ad.evaluate(d=>[d.scrollHeight,d.clientHeight]);
await ad.evaluate(d=>d.scrollTop=d.scrollHeight);await page.waitForTimeout(80);
assert(await onScreen('#appearanceDialog [data-dlgback]'),'Back stays visible after scrolling to the bottom');
await page.screenshot({path:path.join(out,'dlg-appearance-390.png')});
await ad.evaluate(d=>d.scrollTop=0);
await page.locator('#appearanceDialog [data-dlgback]').click();await page.waitForTimeout(150);
assert(!(await ad.evaluate(d=>d.open)),'Back closes appearance');
assert.equal(await page.evaluate(()=>document.documentElement.classList.contains('dlg-open')||document.body.classList.contains('noscroll')),false,'page scroll unlocked after closing');
await page.evaluate(()=>window.scrollTo(0,0));assert.equal(await page.evaluate(()=>scrollY),0,'page scrolls back to the top');
// phone back gesture closes it too, without leaving the app
await page.locator('#appearance').click();await page.waitForTimeout(150);await page.goBack();await page.waitForTimeout(200);
assert(!(await ad.evaluate(d=>d.open)),'history back closes appearance');assert.equal(new URL(page.url()).host,'fx-ui.test');
// Ask the bot
await page.locator('#askFab').click();await page.waitForTimeout(200);
assert(await onScreen('#askDialog [data-dlgback]'));assert(await onScreen('#askIn'));
for(let k=0;k<4;k++){await page.locator('#askIdeas button').first().click();await page.waitForTimeout(250);}
const log=page.locator('#askLog');assert(await log.evaluate(l=>l.scrollHeight>l.clientHeight),'conversation scrolls');
await log.evaluate(l=>l.scrollTop=0);await page.waitForTimeout(50);assert.equal(await log.evaluate(l=>l.scrollTop),0,'can scroll back to the top');
assert(await onScreen('#askDialog [data-dlgback]'));
await page.screenshot({path:path.join(out,'dlg-ask-390.png')});
await page.setViewportSize({width:390,height:500});await page.waitForTimeout(200);              // keyboard up
assert(await onScreen('#askIn'),'input visible with the keyboard up');assert(await onScreen('#askDialog [data-dlgback]'));
await page.screenshot({path:path.join(out,'dlg-ask-keyboard-390.png')});
await page.setViewportSize({width:390,height:844});
await page.goBack();await page.waitForTimeout(200);assert(!(await page.locator('#askDialog').evaluate(d=>d.open)),'phone back closes Ask');
await page.locator('#askFab').click();await page.waitForTimeout(150);await page.locator('#askDialog [data-dlgback]').click();await page.waitForTimeout(150);
assert(!(await page.locator('#askDialog').evaluate(d=>d.open)));
await page.evaluate(()=>go('agents'));await page.waitForTimeout(100);assert.equal(await page.locator('.page.on').getAttribute('id'),'p-agents','app still navigates');
await browser.close();
if(errors.length){console.error(errors.join('\n'));process.exit(1)}console.log('dialogs ok');
})();
