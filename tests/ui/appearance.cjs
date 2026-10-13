/* Targeted appearance checks; uses only local fixtures and intercepted requests. */
const {chromium}=require('playwright'),fs=require('node:fs'),assert=require('node:assert/strict');
const {state,api}=require('./fixture.cjs');
(async()=>{
const browser=await chromium.launch({headless:true,...(process.env.CHROMIUM_PATH?{executablePath:process.env.CHROMIUM_PATH,args:['--no-sandbox']}: {})});
const errors=[];
for(const width of [1440,390]){
 const context=await browser.newContext({viewport:{width,height:width===390?844:1050},colorScheme:'light'}),page=await context.newPage();
 page.on('pageerror',e=>errors.push(e.stack));
 await page.route('**/*',r=>r.fulfill(r.request().url()==='http://fx-ui.test/'?{contentType:'text/html',body:fs.readFileSync('fxagents/dashboard/static/index.html','utf8')}:{json:api(r.request().url())}));
 await page.routeWebSocket('**/ws*',ws=>setTimeout(()=>ws.send(JSON.stringify(state)),30));
 await page.goto('http://fx-ui.test/');await page.waitForSelector('#hero .kpi');
 await page.locator('#appearance').click();
 for(const preset of ['aurora','frost','studio']){
  await page.locator(`[data-preset=${preset}]`).click();
  assert.equal(await page.locator(`[data-preset=${preset}]`).getAttribute('aria-pressed'),'true');
  assert.equal(await page.locator('html').getAttribute('data-surface'),preset==='studio'?'solid':'glass');
  await page.locator('#appearanceDone').click();await page.waitForTimeout(250);
  assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),`page overflow ${preset} ${width}`);
  await page.screenshot({path:`docs/ui-review/${preset}-${width}.png`,animations:'disabled',fullPage:width!==390});
  await page.locator('#appearance').click();
 }
 await page.locator('[data-preset=aurora]').click();
 await page.screenshot({path:`docs/ui-review/appearance-${width}.png`,animations:'disabled'});
 for(const accent of ['iris','ocean','amber']){await page.locator(`[data-accent-choice=${accent}]`).click();assert.equal(await page.locator('html').getAttribute('data-accent'),accent)}
 await page.locator('#motionEnabled').uncheck();await page.locator('#appearanceDone').click();
 await page.reload();await page.waitForSelector('#hero .kpi');
 assert.equal(await page.locator('html').getAttribute('data-accent'),'amber');assert.equal(await page.locator('html').getAttribute('data-theme'),'dark');assert.equal(await page.locator('html').getAttribute('data-motion'),'off');
 await page.evaluate(()=>go('trades'));assert.equal(await page.locator('#p-trades').evaluate(el=>getComputedStyle(el).animationName),'none');
 await page.locator('#appearance').click();await page.locator('#motionEnabled').check();await page.keyboard.press('Escape');assert(await page.locator('#appearance').evaluate(el=>el===document.activeElement));
 await page.emulateMedia({reducedMotion:'reduce'});await page.evaluate(()=>go('home'));assert.equal(await page.locator('#p-home').evaluate(el=>getComputedStyle(el).animationName),'none');
 await page.locator('#appearance').click();assert.equal(await page.locator('#appearanceDialog').evaluate(el=>getComputedStyle(el).animationName),'none');
 await page.keyboard.press('Escape');await page.emulateMedia({reducedMotion:'no-preference'});
 await page.evaluate(s=>receive(s),state);assert.equal(await page.locator('#hero .kpi').first().evaluate(el=>getComputedStyle(el).animationName),'none');
 await context.close();
}
await browser.close();assert.deepEqual(errors,[]);console.log('PASS: Frost/Aurora/Studio at 1440 and 390 px; accent changes, saved preferences, motion-off, OS reduced motion, Escape focus return, no card animation on data updates.');
})().catch(e=>{console.error(e);process.exit(1)});
