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
  if(u.pathname.startsWith('/lib/'))return r.fulfill({contentType:'application/javascript',body:fs.readFileSync('fxagents/dashboard/static'+u.pathname)});
  if(u.pathname==='/')return r.fulfill({contentType:'text/html',body:fs.readFileSync('fxagents/dashboard/static/index.html','utf8')});
  if(u.pathname.endsWith('/api/trades'))return r.fulfill({json:trades.map((t,i)=>i===0?{...t,draw}:t)});
  return r.fulfill({json:api(r.request().url())})});
 await page.routeWebSocket('**/ws*',ws=>{setTimeout(()=>ws.send(JSON.stringify(st)),30)});
 await page.goto('http://fx-ui.test/');await page.waitForTimeout(700);
 // a finished trade with a drawing
 await page.evaluate(()=>go('trades'));await page.waitForTimeout(400);await page.locator('#trades [data-i]').first().click();await page.waitForTimeout(900);
 const rp=await page.locator('#replay').textContent();
 assert(rp.includes("the setup's own levels are drawn"),'no drawing note: '+rp.slice(0,200));
 await page.waitForFunction(()=>RP&&RP.view&&RP.view.candles>0,null,{timeout:5000});
 const v=await page.evaluate(()=>RP.view);
 for(const k of ['impulse leg (BOS)','50% fib','invalidation','structural target']) assert(v.lines.includes(k),'missing '+k);
 for(const k of ['E','X']) assert(v.markers.includes(k),'marker '+k);
 assert(await page.locator('#lwSmall canvas').count()>0,'canvas chart');
 assert(await page.locator('#replay .chip').count()===1,'strategy chip');
 await page.locator('#replay').screenshot({path:path.join(out,`v9-replay-${w}.png`)});
 // the chart pans on drag (native), the drawer still scrolls on phones
 const r0=await page.evaluate(()=>RP.lw.chart.timeScale().getVisibleLogicalRange());
 const sb=await page.locator('#lwSmall').boundingBox();
 await page.mouse.move(sb.x+sb.width*.5,sb.y+sb.height*.5);await page.mouse.down();await page.mouse.move(sb.x+sb.width*.8,sb.y+sb.height*.5,{steps:6});await page.mouse.up();await page.waitForTimeout(200);
 const r1=await page.evaluate(()=>RP.lw.chart.timeScale().getVisibleLogicalRange());
 assert(r1.from<r0.from-1,`drag pans ${r0.from}→${r1.from}`);
 // full screen
 await page.locator('#lwFullBtn').click();await page.waitForTimeout(600);
 assert(await page.locator('#lwFull').isVisible(),'full screen opens');
 await page.waitForFunction(()=>LF.lw&&LF.lw.view.candles>0);
 const n0=await page.evaluate(()=>LF.lw.view.candles);
 assert((await page.evaluate(()=>LF.lw.view.lines)).includes('50% fib'),'drawing in full screen');
 await page.locator('#lfTf button[data-m="60"]').click();await page.waitForTimeout(500);
 const n1=await page.evaluate(()=>LF.lw.view.candles);assert(n1<n0,`bigger candles → fewer ${n0}→${n1}`);
 const fb=await page.locator('#lfChart').boundingBox();await page.mouse.move(fb.x+fb.width*.5,fb.y+fb.height*.5);await page.waitForTimeout(150);
 await page.screenshot({path:path.join(out,`v9-full-${w}.png`)});
 await page.locator('#lfBack').click();await page.waitForTimeout(400);
 assert(!(await page.locator('#lwFull').isVisible()),'back closes full screen');
 assert(await page.locator('#drawer').evaluate(d=>d.classList.contains('on')),'trade stays open under it');
 await page.keyboard.press('Escape');await page.waitForTimeout(300);
 // an open position opens the live trade view
 await page.evaluate(()=>go('home'));await page.waitForTimeout(400);
 await page.locator('#positions .pcard').first().click();await page.waitForTimeout(900);
 assert(await page.locator('#drawer').evaluate(d=>d.classList.contains('on')),'position opens the trade view');
 {const tx=await page.locator("#replay").textContent();assert(tx.includes("open"),"marked open: "+tx.slice(0,300));}
 await page.waitForFunction(()=>RP&&RP.view&&RP.view.candles>0,null,{timeout:5000});
 assert((await page.evaluate(()=>RP.view.prices)).includes('stop now'),'live stop line');
 await page.locator('#drawer').screenshot({path:path.join(out,`v9-open-${w}.png`)});
 assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),'overflow');
 await ctx.close();
}
await browser.close();if(errors.length){console.error(errors.join('\n'));process.exit(1)}console.log('chart7 ok');
})();
