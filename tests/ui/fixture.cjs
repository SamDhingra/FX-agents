// Synthetic UI fixtures only. Never account history, signals or recommendations.
const stamp='2026-10-13T10:42:00-04:00';
const symbols=['XAUUSD','NDQ','US30'];
const prices={XAUUSD:2674.8,NDQ:20382.5,US30:42860.2};
const state={mode:'paper',book:'live',now:stamp,equity:71482.65,day_pnl:682.65,realized_today:426.4,unrealized:256.25,open_risk:142.5,trading_enabled:true,halt_reason:'',today:{trades:4,win_rate:.75,sum_r:3.45,avg_r:.8625},prices,positions:[{id:'demo-gold',symbol:'XAUUSD',side:'LONG',strategy:'ict_fvg_sweep:5m@v1',bias_mode:'aligned',entry:2668.2,avg_entry:2668.2,initial_stop:2663.4,stop:2668.68,qty:25,lots:.25,unrealized:165,r_now:1.375,pips_now:66,locked_pips:4.8,stop_pips:48,stop_in_profit:true,stage:1,adds:0,jev_quality:.8,jev_confidence:.82,risk_mult:1},{id:'demo-nasdaq',symbol:'NDQ',side:'LONG',strategy:'dtfx_zone:15m@v1',bias_mode:'aligned',entry:20346,avg_entry:20346,initial_stop:20289,stop:20289,qty:2.5,lots:.025,unrealized:91.25,r_now:.64,pips_now:36.5,locked_pips:-57,stop_pips:57,stop_in_profit:false,stage:0,adds:0,jev_quality:.75,jev_confidence:.8,risk_mult:1}],selections:Object.fromEntries(symbols.map((sym,i)=>[sym,[{id:['ict_fvg_sweep:5m@v1','dtfx_zone:15m@v1','ema21_rsi55:15m@v1'][i],selected:i<2,jev:.8,jev_conf:.82,quant:.69,combined:[.78,.72,.48][i]}]])),bias:Object.fromEntries(symbols.map((sym,i)=>[sym,{state:i===2?'NEUTRAL':'BULLISH',score:i===2?.1:.75,d:1,h4:i===2?-1:1,h1:1,price:prices[sym],pd_pos:.64,pdh:prices[sym]*1.003,pdl:prices[sym]*.991,accuracy:.62,accuracy_n:48}])),equity_curve:Array.from({length:72},(_,i)=>({ts:new Date(Date.parse(stamp)-(71-i)*3600000).toISOString(),equity:69970+i*19+Math.sin(i*.55)*100+Math.cos(i*.19)*140})),heartbeats:Object.fromEntries(['market_data','risk','position_manager','selector','journal','monitor'].map(x=>[x,Date.now()/1000])),alerts:[{ts:stamp,level:'info',msg:'Sample activity: XAUUSD stop moved into profit.'}],learner:[],decisions:[{ts:stamp,kind:'signal_rating',source:'heuristic',symbol:'XAUUSD',strategy:'ict_fvg_sweep',outputs:{quality:.8,confidence:.82}}],board:symbols.map((symbol,i)=>({symbol,id:['ict_fvg_sweep:5m@v1','dtfx_zone:15m@v1','ema21_rsi55:15m@v1'][i],status:'live',n:56-i*7,win_rate:.62-i*.03,expectancy:.32-i*.08,pf:1.7-i*.1,recent_exp:.21,rr:2,tf:i?'15m':'5m',hour:{exp:.3,n:14}})),registry:[],jev_live:false,news_source:'Sample calendar',news_block:null,news:[{ts:'2026-10-14T08:30:00-04:00',title:'Illustrative high-impact USD event',tier:'high',country:'USD',blackout:[15,15],minutes_to:1308,forecast:null}],min_align:.25,selection_mode:'setup_first',shadow:{enabled:true,books:['playbook','ema21_rsi55'],mode:'playbook'}};
state.equity_curve[state.equity_curve.length-1].equity=state.equity;
const trades=Array.from({length:12},(_,i)=>({id:'sample-'+i,symbol:symbols[i%3],side:i%4===0?'SHORT':'LONG',strategy:['ict_fvg_sweep:5m@v1','dtfx_zone:15m@v1','ema21_rsi55:15m@v1'][i%3],tf:i%3?'15m':'5m',opened:`2026-10-${String(13-Math.floor(i/4)).padStart(2,'0')}T09:35:00-04:00`,closed:`2026-10-${String(13-Math.floor(i/4)).padStart(2,'0')}T10:${String(40-i).padStart(2,'0')}:00-04:00`,entry:prices[symbols[i%3]]-10,exit_price:prices[symbols[i%3]],initial_stop:prices[symbols[i%3]]-20,realized:[186.4,-72.5,124.8,187.7][i%4],r_multiple:[1.55,-1,1.2,1.7][i%4],pips:[32,-17,64,48][i%4],risk_pips:20,lots:.1,lots_max:.1,adds:0,mfe_r:1.8,jev_quality:.8,jev_source:'heuristic',bias_mode:'aligned',exit_reason:i%4===1?'stop':'trail_stop',reason:'Illustrative fixture for interface review',events:[{ts:stamp,kind:'entry',price:prices[symbols[i%3]]-10},{ts:stamp,kind:'stop_move',stop:prices[symbols[i%3]]-2},{ts:stamp,kind:'closed',reason:'trail_stop'}]}));

// v3 panels (synthetic)
const T0=Date.parse(stamp);
const bars=Array.from({length:150},(_,i)=>{const t=new Date(T0-3*3600000+i*60000);const o=2660+Math.sin(i/9)*4+i*.05,c=o+Math.sin(i/3)*1.2;return [t.toISOString(),o,Math.max(o,c)+.6,Math.min(o,c)-.6,c]});
const rnd=(()=>{let x=7;return()=>((x=x*16807%2147483647)/2147483647)})();
const mk=(n,mu)=>{const r=Array.from({length:n},()=>+(mu+(rnd()-.5)*2.2).toFixed(3));let c=0;return {r,cum:r.map(v=>+(c+=v).toFixed(2))}};
const evBook=(book,n,mu,ci,verdict)=>{const {r,cum}=mk(n,mu);return {book,mode:book,n,avg_r:+(r.reduce((a,b)=>a+b,0)/n).toFixed(3),sum_r:cum[n-1],win:.5,ci,verdict,cum,r,
  strategies:[{name:'trend_breakout',n:Math.round(n*.6),avg_r:.05,sum_r:2,win:.5,ci:[-.2,.3],verdict:'unproven'},{name:'ict_fvg_sweep',n:Math.round(n*.4),avg_r:-.1,sum_r:-3,win:.4,ci:[-.4,.15],verdict:'unproven'}],
  days:Array.from({length:Math.min(60,n)},(_,i)=>({date:`2026-08-${String(1+i%28).padStart(2,'0')}`,r:+((rnd()-.45)*3).toFixed(2),trades:2}))}};
const evidence={books:[evBook('live',23,-.12,[-.55,.3],'early'),evBook('playbook',140,-.02,[-.12,.08],'unproven'),evBook('ema21_rsi55',64,.09,[-.08,.27],'unproven'),evBook('gold_breakout',3,.2,null,'none')]};
const now={now:stamp,items:[{key:'window_end',label:'Entry window 08:30–11:30 closes',at:'2026-10-13T11:30:00-04:00',live:true},{key:'window',label:'Entry window 13:30–15:30 opens',at:'2026-10-13T13:30:00-04:00'},{key:'flatten',label:'Day-trading flatten',at:'2026-10-13T15:50:00-04:00'},{key:'gold_range',label:'Gold overnight range closes',at:'2026-10-14T00:00:00-04:00',range:{high:2681.2,low:2662.4}},{key:'news',label:'Illustrative high-impact USD event',tier:'high',at:'2026-10-14T08:30:00-04:00'}],
 weather:[{symbol:'XAUUSD',price:2674.8,sky:'trend',chop:31.4,vol_pct:.71,bias:.75,news:null},{symbol:'NDQ',price:20382.5,sky:'chop',chop:66.2,vol_pct:.35,bias:.3,news:null},{symbol:'US30',price:42860.2,sky:'storm',chop:48,vol_pct:.9,bias:-.35,news:{title:'CPI',minutes:22,tier:'tier1'}}],
 fuel:{budget:1400,used:310,left_pct:.78,dd_limit_pct:.06,dd_now_pct:.012,blackout:null}};
const story=t=>({trade:{...t,initial_stop:t.entry-8,final_stop:t.entry+1,events:[{ts:'2026-10-13T09:35:00-04:00',kind:'entry',price:t.entry,qty:1.75,stop:t.entry-8,risk_ccy:172.9,bias:'aligned',bias_score:.3,risk_mult:.5},{ts:'2026-10-13T09:41:00-04:00',kind:'partial',price:t.entry+8,qty:.87,r:1},{ts:'2026-10-13T09:41:00-04:00',kind:'stop_moved',stop:t.entry+1,stage:1},{ts:t.closed,kind:'exit',price:t.exit_price,reason:'breakeven_plus_stop'}]},
 signal:{ts:'2026-10-13T09:34:00-04:00',action:'taken',why:'qty 1.75, risk 0.5%'},jev:{ts:'2026-10-13T09:34:30-04:00',kind:'signal_rating',source:'jev',outputs:{quality:.62,confidence:.55,htf_aligned:.7},question:null}});
state.flow={events:[],counts:{}};
const days={};for(const t of trades){let d=days[t.closed.slice(0,10)]??={trades:0,wins:0,pnl:0,r:0};d.trades++;d.wins+=+(t.realized>0);d.pnl+=t.realized;d.r+=t.r_multiple;}
function api(path){
 const u=new URL(path,'http://fixture.local/'), book=u.searchParams.get('book')||'live';
 if(u.pathname.endsWith('/api/state'))return {...state,book,equity:book==='live'?state.equity:70326.4};
 if(u.pathname.endsWith('/api/trades'))return trades;
 if(u.pathname.endsWith('/api/now'))return now;
 if(u.pathname.endsWith('/api/evidence'))return evidence;
 if(u.pathname.includes('/api/story/'))return story(trades.find(t=>t.id===decodeURIComponent(u.pathname.split('/').pop()))||trades[0]);
 if(u.pathname.endsWith('/api/bars'))return {bars};
 if(u.pathname.includes('/api/day/'))return {trades:trades.filter(t=>t.closed.startsWith(u.pathname.split('/').pop())),events:[]};
 if(u.pathname.endsWith('/api/calendar'))return {days,events:[]};
 if(u.pathname.endsWith('/api/compare'))return {enabled:false,league:{since:stamp,rows:[]}};
 if(u.pathname.endsWith('/api/setup_map'))return {symbols,status:{state:'missing'}};
 if(u.pathname.endsWith('/api/learner'))return {rows:[],min_trades_promote:30,promote_margin_r:.1,live_requires_vetting:true};
 if(u.pathname.endsWith('/api/research'))return null;
 if(u.pathname.endsWith('/api/backtests'))return {runs:[],history_ready:false};
 if(u.pathname.endsWith('/api/lab'))return {criteria:{min_n:30,min_t:2},setups:{ict_fvg_sweep:{params:{},grid:{}}},symbols,candidates:[]};
 return {};
}
module.exports={state,trades,api};
