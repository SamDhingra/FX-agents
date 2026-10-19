/* v5: time machine, edge atlas, recap, trade notes, slide to flatten, home-screen app tags. node tests/ui/v5.cjs */
const {chromium}=require('playwright');const fs=require('node:fs');const path=require('node:path');const assert=require('node:assert/strict');
const {state,api}=require('./fixture.cjs');
(async()=>{
const browser=await chromium.launch({headless:true,executablePath:process.env.CHROMIUM_PATH||undefined});const errors=[];
const out=path.resolve(process.env.OUT||'docs/ui-review');fs.mkdirSync(out,{recursive:true});
for(const [width,touch] of [[1440,false],[390,true]]){
 const ctx=await browser.newContext({viewport:{width,height:width===390?844:1000},isMobile:touch,hasTouch:touch,colorScheme:'dark'});const page=await ctx.newPage();const posts=[];
 page.on('pageerror',e=>errors.push(width+': '+e.stack));
 await page.route('**/*',r=>{const req=r.request(),u=new URL(req.url());if(u.pathname.startsWith('/lib/'))return r.fulfill({contentType:'application/javascript',body:fs.readFileSync('fxagents/dashboard/static'+u.pathname)});if(u.pathname==='/')return r.fulfill({contentType:'text/html',body:fs.readFileSync('fxagents/dashboard/static/index.html','utf8')});
  if(req.method()==='POST'){posts.push([u.pathname,req.postData()]);if(u.pathname.endsWith('/api/ask'))return r.fulfill({json:api(req.url())});return r.fulfill({json:{ok:true}})}return r.fulfill({json:api(req.url())})});
 await page.routeWebSocket('**/ws*',ws=>setTimeout(()=>ws.send(JSON.stringify(state)),30));
 await page.goto('http://fx-ui.test/');await page.waitForTimeout(500);const tag=String(width);
 assert.equal(await page.locator('link[rel=manifest]').count(),1);assert.equal(await page.locator('link[rel=apple-touch-icon]').count(),1);
 // time machine
 await page.evaluate(()=>go('machine'));await page.waitForTimeout(500);
 await page.locator('#tmSlider').evaluate(s=>{s.value=String(Date.parse('2026-10-13T05:30:00-04:00'));s.dispatchEvent(new Event('input'))});await page.waitForTimeout(150);
 assert.equal(await page.locator('#tmClock').textContent(),'05:30 NY');assert((await page.locator('#tmPos').textContent()).includes('XAUUSD'),'open trade at 05:30');
 assert((await page.locator('#tmFeed').textContent()).includes('Jev'));
 await page.screenshot({path:path.join(out,`v5-machine-${tag}.png`),fullPage:true});
 assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),'overflow machine');
 await page.locator('#tmPlayBtn').click();await page.waitForTimeout(400);await page.locator('#tmPlayBtn').click();
 // atlas
 await page.evaluate(()=>go('strategies'));await page.waitForTimeout(400);assert(await page.locator('#atlas .atc').count()>50);
 await page.locator('#atlas .atc').first().click();assert((await page.locator('#atlInfo').textContent()).includes('trades'));
 await page.locator('#atlas').screenshot({path:path.join(out,`v5-atlas-${tag}.png`)});
 assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),'overflow atlas');
 // recap
 await page.evaluate(()=>go('home'));await page.waitForTimeout(300);await page.locator('#recapBtn').click();await page.waitForTimeout(300);
 assert((await page.locator('#rcBody').textContent()).includes('+3.45R'));await page.screenshot({path:path.join(out,`v5-recap-${tag}.png`)});
 if(touch){await page.locator('#recapDialog [data-dlgback]').click()}else{await page.locator('#recapClose').click()}await page.waitForTimeout(150);
 assert(!(await page.locator('#recapDialog').evaluate(d=>d.open)));
 // notes
 await page.evaluate(()=>go('trades'));await page.waitForTimeout(300);await page.locator('#trades [data-i]').first().click();await page.waitForTimeout(500);
 await page.locator('#notes [data-tag="#fomo"]').click();await page.locator('#noteSave').click();await page.waitForTimeout(200);
 const np=posts.find(p=>p[0].includes('/note'));assert(np&&JSON.parse(np[1]).note.includes('#fomo'),'note posted');
 assert.equal(await page.locator('#noteMsg').textContent(),'Saved ✓');
 await page.keyboard.press('Escape');await page.evaluate(()=>hideDrawer());await page.waitForTimeout(200);
 // slide to flatten (touch) / button (mouse)
 await page.evaluate(()=>go('home'));await page.waitForTimeout(200);await page.locator('#flatten').click();await page.waitForTimeout(150);
 if(touch){assert(await page.locator('#slideFlat').isVisible());assert(await page.locator('#confirmFlatten').isHidden());
  const k=await page.locator('#slideFlat .knob').boundingBox(),tr=await page.locator('#slideFlat').boundingBox();
  await page.mouse.move(k.x+10,k.y+10);await page.mouse.down();await page.mouse.move(k.x+60,k.y+10,{steps:4});await page.mouse.up();await page.waitForTimeout(150);
  assert(await page.locator('#controlDialog').evaluate(d=>d.open),'half a slide does nothing');
  await page.mouse.move(k.x+10,k.y+10);await page.mouse.down();await page.mouse.move(tr.x+tr.width-5,k.y+10,{steps:8});await page.mouse.up();await page.waitForTimeout(200);
 }else{await page.locator('#confirmFlatten').click();await page.waitForTimeout(200);}
 assert(posts.some(p=>p[0]==='/api/control/flatten'),'flatten sent');
 await ctx.close();
}
await browser.close();if(errors.length){console.error(errors.join('\n'));process.exit(1)}console.log('v5 ok');
})();
