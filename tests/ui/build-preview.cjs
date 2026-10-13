// Build an offline, synthetic-data preview of the exact dashboard source.
const fs=require('node:fs'),path=require('node:path');
const output=process.argv[2]||'docs/ui-review/FX-agents-design-preview.html';
let html=fs.readFileSync('fxagents/dashboard/static/index.html','utf8');
let fixture=fs.readFileSync('tests/ui/fixture.cjs','utf8').replace('module.exports={state,trades,api};','');
const script=`<script>(()=>{${fixture}
window.__previewState=state;
window.fetch=async (url,options={})=>{
 if(options.method==='POST'){
   const action=String(url).split('/').pop();
   if(String(url).includes('api/control/')){
     state.trading_enabled=action==='resume';state.halt_reason=action==='resume'?'':action==='flatten'?'Sample positions flattened':'Sample entries paused';
     if(action==='flatten'){state.positions=[];state.unrealized=0;state.open_risk=0}
     return new Response(JSON.stringify({ok:true}),{status:200});
   }
   return new Response(JSON.stringify({detail:'Research changes are disabled in this design preview.'}),{status:403});
 }
 return new Response(JSON.stringify(api(String(url))),{status:200,headers:{'content-type':'application/json'}});
};
window.WebSocket=class{
 constructor(url){this.url=url;setTimeout(()=>{this.onopen?.();this.sendSnapshot()},30);this.timer=setInterval(()=>this.sendSnapshot(),3000)}
 sendSnapshot(){for(const k of Object.keys(state.heartbeats))state.heartbeats[k]=Date.now()/1000;const book=new URL(this.url,'http://preview.local').searchParams.get('book')||'live';this.onmessage?.({data:JSON.stringify({...state,book,equity:book==='live'?state.equity:70326.4})})}
 close(){clearInterval(this.timer);this.onclose?.()}
};
document.addEventListener('click',e=>{const a=e.target.closest('a');if(!a)return;
 if(a.getAttribute('href')==='logout'){e.preventDefault();alert('Design preview only. No signed-in account.');}
 if(a.getAttribute('href')?.includes('api/journal.csv')){e.preventDefault();const exportLink=document.createElement('a');exportLink.href='data:text/csv;charset=utf-8,'+encodeURIComponent('sample_data,symbol,pnl\\n'+trades.map(t=>'true,'+t.symbol+','+t.realized).join('\\n'));exportLink.download='sample-trades.csv';exportLink.click();}
});
})();</script>`;
html=html.replace('<script>\nconst $',script+'\n<script>\nconst $');
html=html.replace('<body>','<body><div class="preview-notice" role="note"><b>DESIGN PREVIEW</b> · Synthetic sample data · Controls affect this preview only · No broker connection</div>');
html=html.replace('</style>','.preview-notice{padding:10px 16px;text-align:center;background:#eaf0ff;color:#264eae;font:11px/1.6 system-ui;border-bottom:1px solid #cbd8f6}.preview-notice b{letter-spacing:1px;font-size:10px}body:before{content:none}</style>');
fs.mkdirSync(path.dirname(output),{recursive:true});fs.writeFileSync(output,html);console.log(output);
