/* Jev verdict on the trade page reads the real grade (Jev stores {value, confidence}). node tests/ui/jevstamp.cjs */
const {chromium}=require('playwright');const fs=require('node:fs');const assert=require('node:assert/strict');
const {state,trades,api}=require('./fixture.cjs');
const cases=[ // [jev quality on the trade, R, raw decision outputs, expected word, expected stamp]
 [0.55, 0.48, {quality:{value:0.55,confidence:0.4}}, 'Acceptable', 'Jev called it'],
 [0.30, -1.0, {quality:{value:0.30,confidence:0.5}}, "I'd pass", 'Jev called it'],
 [0.70, -1.0, {quality:{value:0.70,confidence:0.6}}, 'I like it', 'Jev missed'],
 [null, 0.6, {quality:{value:0.42,confidence:0.5}}, 'Doubtful', 'Jev missed'],   // no stored grade: unwrap the object
];
(async()=>{
const browser=await chromium.launch({headless:true,executablePath:process.env.CHROMIUM_PATH||undefined});const errors=[];
for(const [jq,R,outs,word,stamp] of cases){
 const ctx=await browser.newContext({viewport:{width:390,height:844}});const page=await ctx.newPage();
 page.on('pageerror',e=>errors.push(e.stack));
 await page.route('**/*',r=>{const u=new URL(r.request().url());
  if(u.pathname.startsWith('/lib/'))return r.fulfill({contentType:'application/javascript',body:fs.readFileSync('fxagents/dashboard/static'+u.pathname)});
  if(u.pathname==='/')return r.fulfill({contentType:'text/html',body:fs.readFileSync('fxagents/dashboard/static/index.html','utf8')});
  const j=api(r.request().url());
  if(u.pathname.includes('/api/story/')){j.trade={...j.trade,jev_quality:jq,jev_confidence:jq==null?null:0.4,r_multiple:R};
   j.jev={ts:j.trade.opened,kind:'signal_rating',source:'jev',outputs:outs,question:null};}
  return r.fulfill({json:j})});
 await page.routeWebSocket('**/ws*',ws=>{setTimeout(()=>ws.send(JSON.stringify(state)),30)});
 await page.goto('http://fx-ui.test/');await page.waitForTimeout(600);
 await page.evaluate(()=>go('trades'));await page.waitForTimeout(400);await page.locator('#trades [data-i]').first().click();await page.waitForTimeout(800);
 const txt=await page.locator('#court').textContent();
 assert(txt.includes(word),`word ${word}: `+txt.slice(0,400));assert(txt.includes(stamp),`stamp ${stamp}`);
 assert(!/I'd pass: —/.test(txt),'empty grade shown');
 await ctx.close();
}
await browser.close();if(errors.length){console.error(errors.join('\n'));process.exit(1)}console.log('jevstamp ok');
})();
