/* v7 trade chart: the setup's drawing, full-screen zoom/pan/crosshair, open positions open live. node tests/ui/chart7.cjs */
const {chromium}=require('playwright');const fs=require('node:fs');const path=require('node:path');const assert=require('node:assert/strict');
const {state,trades,api}=require('./fixture.cjs');
const B=(i)=>new Date(Date.parse('2026-10-13T10:42:00-04:00')-3*3600000+i*60000).toISOString();
const draw=[{k:'box',lo:2655.5,hi:2667.0,t0:B(20),t1:B(60),label:'impulse leg (BOS)',role:'leg'},
 {k:'line',px:2661.2,t0:B(30),t1:B(60),label:'50% fib',role:'level'},{k:'line',px:2655.5,t0:B(20),t1:B(60),label:'invalidation',role:'invalid'},
 {k:'line',px:2667.0,t0:B(60),label:'structural target',role:'target'},{k:'mark',px:2661,t0:B(60),label:'signal bar',role:'signal'}];
(async()=>{
const browser=await chromium.launch({headless:true,executablePath:process.env.CHROMIUM_PATH||undefined});
const out=path.resolve(process.env.OUT||'docs/ui-review');fs.mkdirSync(out,{recursive:true});const errors=[];
for(const [w,h] of [[390,844],[1280,900]]){
 const ctx=await browser.newContext({viewport:{width:w,height:h},hasTouch:w<500});const page=await ctx.newPage();
 page.on('pageerror',e=>errors.push(w+': '+e.stack));page.on('console',m=>{if(m.type()==='error')errors.push(w+' console: '+m.text())});
 const st={...state,positions:state.positions.map(p=>({...p,opened:B(40),draw,events:[{ts:B(40),kind:'entry',price:p.entry,qty:1}],pips_now:12,stop_pips:48,lots:.17}))};
 await page.route('**/*',r=>{const u=new URL(r.request().url());
  if(u.pathname==='/')return r.fulfill({contentType:'text/html',body:fs.readFileSync('fxagents/dashboard/static/index.html','utf8')});
  if(u.pathname.endsWith('/api/trades'))return r.fulfill({json:trades.map((t,i)=>i===0?{...t,draw}:t)});
  return r.fulfill({json:api(r.request().url())})});
 await page.routeWebSocket('**/ws*',ws=>{setTimeout(()=>ws.send(JSON.stringify(st)),30)});
 await page.goto('http://fx-ui.test/');await page.waitForTimeout(700);
 // a finished trade with a drawing
 await page.evaluate(()=>go('trades'));await page.waitForTimeout(400);await page.locator('#trades [data-i]').first().click();await page.waitForTimeout(900);
 const rp=await page.locator('#replay').textContent();
 assert(rp.includes("the setup's own levels are drawn"),'no drawing note: '+rp.slice(0,200));
 const svgTxt=await page.locator('#rpSvg').textContent();
 for(const k of ['impulse leg (BOS)','50% fib','invalidation','structural target']) assert(svgTxt.includes(k),'missing '+k);
 assert(await page.locator('#replay .chip').count()===1,'strategy chip');
 await page.locator('#replay').screenshot({path:path.join(out,`v7-replay-${w}.png`)});
 // full screen
 await page.locator('#rpSvg').click();await page.waitForTimeout(400);
 assert(await page.locator('#chartFull').isVisible(),'full screen opens');
 const n0=await page.locator('#cfSvg rect').count();
 await page.locator('#cfIn').click();await page.locator('#cfIn').click();await page.waitForTimeout(200);
 const n1=await page.locator('#cfSvg rect').count();assert(n1<n0,`zoom in shows fewer candles ${n0}→${n1}`);
 const box=await page.locator('#cfSvg').boundingBox();
 await page.mouse.move(box.x+box.width*.5,box.y+box.height*.5);await page.mouse.down();await page.mouse.up();await page.waitForTimeout(200);
 assert(await page.locator('#cfTip').isVisible(),'crosshair tip');assert((await page.locator('#cfTip').textContent()).includes('O '),'OHLC');
 await page.locator('#cfTf button').nth(1).click();await page.waitForTimeout(200);
 await page.screenshot({path:path.join(out,`v7-full-${w}.png`)});
 await page.locator('#cfBack').click();await page.waitForTimeout(400);
 assert(!(await page.locator('#chartFull').isVisible()),'back closes full screen');
 assert(await page.locator('#drawer').evaluate(d=>d.classList.contains('on')),'trade stays open under it');
 await page.keyboard.press('Escape');await page.waitForTimeout(300);
 // an open position opens the live trade view
 await page.evaluate(()=>go('home'));await page.waitForTimeout(400);
 await page.locator('#positions .pcard').first().click();await page.waitForTimeout(900);
 assert(await page.locator('#drawer').evaluate(d=>d.classList.contains('on')),'position opens the trade view');
 {const tx=await page.locator("#replay").textContent();assert(tx.includes("open"),"marked open: "+tx.slice(0,300));}
 assert((await page.locator('#rpSvg').textContent()).includes('stop now'),'live stop line');
 await page.locator('#drawer').screenshot({path:path.join(out,`v7-open-${w}.png`)});
 assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),'overflow');
 await ctx.close();
}
await browser.close();if(errors.length){console.error(errors.join('\n'));process.exit(1)}console.log('chart7 ok');
})();
