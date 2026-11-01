/* FX-Agents LIVE — the owner's additions to the dashboard (loaded only on the live site, only for the owner).
   Adds: LIVE badge · Desk (account, limits, one-tap controls per open trade, pre-trade checklist, latest setups,
   markets) · Journal & review (tags, grade, notes, lessons, weekly patterns) · Compare redesigned for live ·
   Members (invites, approvals, copy switch with authenticator code, audit) · Account security.
   Removes: Backtests and Backtester (their endpoints answer 404 on the live site). */
(() => {
"use strict";
const L = window.FX_LIVE || {};
document.body.classList.add("fxlive");

/* every state-changing request carries x-fx: 1 (the server refuses it otherwise — cross-site forms can't add it) */
const _fetch = window.fetch.bind(window);
window.fetch = (input, init = {}) => {
  const m = String((init && init.method) || (input && input.method) || "GET").toUpperCase();
  if(m !== "GET" && m !== "HEAD"){ init = {...init, headers: new Headers(init.headers || {})}; init.headers.set("x-fx", "1"); }
  return _fetch(input, init);
};
const J = async (url, body, method) => {
  const r = await fetch(url, body === undefined && !method ? {credentials:"same-origin"} :
    {method: method || "POST", credentials:"same-origin", headers:{"content-type":"application/json"}, body: JSON.stringify(body || {})});
  let d = null; try{ d = await r.json(); }catch(e){}
  if(!r.ok) throw new Error((d && d.detail) || ("HTTP " + r.status));
  return d;
};
const E = s => esc(s);
const R = (x, d=2) => sR(x, d);
const ago = iso => { if(!iso) return ""; const s = (Date.now() - new Date(iso)) / 1000; return s < 90 ? Math.round(s) + "s" : s < 5400 ? Math.round(s/60) + "m" : Math.round(s/3600) + "h"; };

/* ── remove research pages that don't belong on the live site ── */
for(const p of ["backtests", "bt"]){ $$(`[data-p="${p}"]`).forEach(x => x.remove()); const s = $("#p-" + p); if(s) s.remove(); delete titles[p]; }
const mi = MORE.indexOf("backtests"); if(mi >= 0) MORE.splice(mi, 1);
const mj = MORE.indexOf("bt"); if(mj >= 0) MORE.splice(mj, 1);

/* ── LIVE badge ── */
const tchips = $(".tchips");
if(tchips) tchips.insertAdjacentHTML("afterbegin", `<span class="livebadge" title="Real-money account"><i></i>LIVE</span>`);
const brand = $(".brand small"); if(brand) brand.textContent = "LIVE · REAL MONEY";

/* ── new pages ── */
const PAGES = {
  desk: ["Live desk", "Account, limits, open trades with one-tap controls, and the checklist before the next trade."],
  journal: ["Journal & review", "Tag, grade and annotate every live trade; see which habits make and cost money."],
  lcompare: ["Live vs paper", "The real account next to its paper books — by book, by instrument, over time."],
  members: ["Members", "Invites, approvals, copy switch and the audit log."],
  account: ["Account security", "Your sign-ins, password and sessions."]};
const main = $("#workspace");
for(const [p, [t, d]] of Object.entries(PAGES)){
  titles[p] = t; pageDescriptions[p] = d;
  main.insertAdjacentHTML("beforeend", `<section class="page" id="p-${p}"><div class="lv-grid" id="lv-${p}"><div class="lv-card">Loading…</div></div></section>`);
}
shortTitles.desk = "Desk"; shortTitles.journal = "Journal"; shortTitles.lcompare = "Compare"; shortTitles.members = "Members"; shortTitles.account = "Security";
const side = $("aside");
const firstLabel = side.querySelector(".nav-label");
firstLabel.insertAdjacentHTML("afterend", `<button class="nav" data-p="desk"><svg><use href="#i-target"/></svg>Live desk</button>`);
side.querySelector('[data-p="trades"]').insertAdjacentHTML("afterend", `<button class="nav" data-p="journal"><svg><use href="#i-list"/></svg>Journal &amp; review</button>`);
$$('[data-p="compare"]').forEach(b => b.dataset.p = "lcompare");
const mon = [...side.querySelectorAll(".nav-label")].pop();
mon.insertAdjacentHTML("beforebegin", `<div class="nav-label">LIVE</div><button class="nav" data-p="members"><svg><use href="#i-bot"/></svg>Members</button><button class="nav" data-p="account"><svg><use href="#i-sun"/></svg>Account security</button>`);
const sheet = $("#moreSheet");
sheet.insertAdjacentHTML("afterbegin", `<button data-p="journal"><svg><use href="#i-list"/></svg>Journal &amp; review</button><button data-p="home"><svg><use href="#i-home"/></svg>Overview</button><button data-p="members"><svg><use href="#i-bot"/></svg>Members</button><button data-p="account"><svg><use href="#i-sun"/></svg>Account security</button>`);
MORE.push("journal", "home", "members", "account");
const homeTab = $('.tabbar [data-p="home"]');
if(homeTab){ homeTab.dataset.p = "desk"; homeTab.lastChild.textContent = "Desk"; }
$$('[data-p="desk"],[data-p="journal"],[data-p="members"],[data-p="account"],[data-p="lcompare"],#moreSheet [data-p="home"]').forEach(b => b.onclick = () => go(b.dataset.p));

let timer = null;
const _go = go;
go = function(p){
  _go(p);
  clearInterval(timer); timer = null;
  if(!PAGES[p]) return;
  const load = {desk: loadDesk, journal: loadJournal, lcompare: loadCompare, members: loadMembers, account: loadAccount}[p];
  load();
  if(p === "desk") timer = setInterval(() => {
    const typing = document.activeElement && document.activeElement.closest && document.activeElement.closest("#lv-desk input");
    if(document.visibilityState === "visible" && page === "desk" && !typing) loadDesk(); }, 5000);
};
document.addEventListener("visibilitychange", () => { if(document.visibilityState === "visible" && page === "desk") loadDesk(); });

/* ════════════════ DESK ════════════════ */
let DESK = null, armed = {};
async function loadDesk(){
  try{ DESK = await J("api/live/desk"); }catch(e){ $("#lv-desk").innerHTML = `<div class="lv-card">Couldn't load the desk (${E(e.message)}).</div>`; return; }
  renderDesk();
}
function renderDesk(){
  const d = DESK, a = d.account, el = $("#lv-desk");
  const keepInputs = {}; el.querySelectorAll("input[data-keep]").forEach(i => keepInputs[i.dataset.keep] = i.value);
  const used = a.loss_cap ? Math.min(1, a.loss_used / a.loss_cap) : 0;
  const tradable = d.markets.filter(m => m.trade).map(m => m.symbol);
  const status = d.trading_enabled ? `<span class="lv-chip on">● Entries on</span>` : `<span class="lv-chip off">● Entries off — ${E(d.halt_reason || "paused")}</span>`;
  const head = `<div class="lv-card"><h3>Account <span class="sp"></span><span class="mut num" style="font-weight:500;font-size:12px">${E(hm(d.now))} NY · flat at ${E(d.flatten_at)}</span></h3>
    <div class="lv-kpis">
      <div class="lv-kpi"><div class="l">Equity</div><div class="v num">${money(a.equity, 0)}</div><div class="s">risk ${(a.risk_pct*100).toFixed(2)}% / trade</div></div>
      <div class="lv-kpi"><div class="l">Today</div><div class="v num ${cls(a.day_pnl)}">${smoney(a.day_pnl, 0)}</div><div class="s">${d.today.trades} trades · ${R(d.today.sum_r)}</div></div>
      <div class="lv-kpi"><div class="l">Daily loss limit</div><div class="v num">${money(a.loss_used, 0)} <small class="mut">/ ${money(a.loss_cap, 0)}</small></div>
        <div class="lv-bar ${used > .75 ? "hot" : ""}"><i style="width:${(used*100).toFixed(0)}%"></i></div></div>
      <div class="lv-kpi"><div class="l">Open</div><div class="v num">${d.positions.length} <small class="mut">/ ${a.max_open}</small></div><div class="s">trading ${E(tradable.join(", ") || "—")}</div></div>
    </div>
    <div class="lv-status">${status}<span class="sp" style="flex:1"></span>
      ${d.trading_enabled ? `<button class="lv-btn" data-ctl="pause">Pause entries</button>` : `<button class="lv-btn pri" data-ctl="resume">Resume entries</button>`}
      <button class="lv-btn danger ${armed.flatten ? "arm" : ""}" data-ctl="flatten">${armed.flatten ? "Tap again: close everything" : "Flatten all"}</button></div>
    <div class="lv-msg" id="ctlMsg"></div></div>`;
  const pos = d.positions.length ? d.positions.map(posCard).join("") : `<div class="mut" style="font-size:13px">No open trades. The desk refreshes every 5 seconds.</div>`;
  const posCardHtml = `<div class="lv-card s8"><h3>Open trades</h3>${pos}</div>`;
  const check = `<div class="lv-card s4"><h3>Before the next trade</h3>${checklist(d)}</div>`;
  const setups = `<div class="lv-card s6"><h3>Latest setups <span class="sp"></span><span class="mut" style="font-weight:500;font-size:12px">what the bot saw and did</span></h3><div class="lv-list">${
    d.signals.slice(0, 10).map(s => `<div class="lv-row"><span class="num mut">${E(hm(s.ts))}</span><b>${E(s.symbol)}</b><span class="side ${String(s.side||"")[0]}">${E(s.side)}</span>
      <span class="grow mut" title="${E(s.why || "")}">${E(s.action)}${s.why ? " · " + E(s.why) : ""}</span></div>`).join("") || `<div class="mut">No setups yet today.</div>`}</div></div>`;
  const mk = `<div class="lv-card s6"><h3>Markets</h3><div class="lv-list">${d.markets.map(m => { const b = m.bias || {};
      return `<div class="lv-row"><b style="min-width:62px">${E(m.symbol)}</b><span class="num">${m.price != null ? fmt(m.price, 2) : "—"}</span>
      <span class="grow mut">${E(b.label || "bias —")}${b.score != null ? ` (${b.score > 0 ? "+" : ""}${Number(b.score).toFixed(2)})` : ""} · D${b.d ?? "·"} 4H${b.h4 ?? "·"} 1H${b.h1 ?? "·"}</span>
      ${m.trade ? `<span class="lv-chip on" style="font-size:11px">trading</span>` : `<span class="lv-chip" style="font-size:11px">view only</span>`}</div>`; }).join("")}</div>
    <div class="mut" style="font-size:12px;margin-top:8px">Members copying: ${d.members.copy_enabled ? `<b class="up">on</b> · ${d.members.linked} account(s) connected` : `<b>off</b>`}</div></div>`;
  el.innerHTML = head + posCardHtml + check + setups + mk;
  el.querySelectorAll("input[data-keep]").forEach(i => { if(keepInputs[i.dataset.keep] != null) i.value = keepInputs[i.dataset.keep]; });
  wireDesk();
}
function posCard(p){
  const k = id => armed[p.id + ":" + id];
  const beDone = (p.be - p.stop) * (p.side === "LONG" ? 1 : -1) <= 0;
  return `<div class="lv-pos" data-id="${E(p.id)}">
    <div class="hd"><span class="side ${p.side[0]}">${p.side}</span><b>${E(p.symbol)}</b><span class="mut" style="font-size:12px">${E(String(p.strategy).split("@")[0])} · ${ago(p.opened)} ago</span>
      <span class="rnow num ${cls(p.r_now)}">${p.r_now == null ? "—" : R(p.r_now)}</span></div>
    <div class="meta num"><div><span>Size</span>${fmt(p.qty, p.qty < 10 ? 1 : 0)}</div><div><span>Entry</span>${fmt(p.entry, 2)}</div>
      <div><span>Stop</span>${fmt(p.stop, 2)}</div><div><span>1R target</span>${fmt(p.target_1r, 2)}</div>
      <div><span>Open P&amp;L</span><b class="${cls(p.unrealized)}">${smoney(p.unrealized, 0)}</b></div><div><span>At risk</span>${money(p.risk_usd, 0)}</div></div>
    ${p.pending_close ? `<div class="lv-msg down">Close pending at OANDA (${E(p.pending_close)}) — retrying every bar</div>` : ""}
    <div class="lv-acts">
      <button class="lv-btn ${k("close") ? "arm" : "danger"}" data-act="close">${k("close") ? "Tap again to close" : "Close"}</button>
      <button class="lv-btn" data-act="breakeven" ${beDone ? "disabled" : ""}>Stop → break-even</button>
      <button class="lv-btn" data-act="partial" data-frac="0.5">Bank 50%</button>
      <button class="lv-btn" data-act="partial" data-frac="0.25">Bank 25%</button></div>
    <div class="lv-inline"><input data-keep="stop:${E(p.id)}" inputmode="decimal" placeholder="New stop (only toward profit)" aria-label="New stop price">
      <button class="lv-btn" data-act="stop">Move stop</button></div>
    <div class="lv-inline"><input data-keep="note:${E(p.id)}" placeholder="Note for the journal" aria-label="Trade note" value="${E(p.note || "")}">
      <button class="lv-btn" data-act="note">Save note</button></div>
    <div class="lv-msg" data-msg></div></div>`;
}
function checklist(d){
  const out = [], sym = (d.markets.find(m => m.trade) || {}).symbol;
  const b = ((d.markets.find(m => m.symbol === sym) || {}).bias) || {};
  const row = (st, txt) => out.push(`<div class="${st}"><i>${st === "y" ? "✓" : st === "n" ? "✕" : "!"}</i><span>${txt}</span></div>`);
  row(d.trading_enabled ? "y" : "n", d.trading_enabled ? "Entries are on" : "Entries are off");
  const used = d.account.loss_cap ? d.account.loss_used / d.account.loss_cap : 0;
  row(used < .5 ? "y" : used < 1 ? "w" : "n", `Daily loss used ${(used*100).toFixed(0)}% of the limit`);
  row(d.positions.length < d.account.max_open ? "y" : "n", `${d.positions.length} of ${d.account.max_open} positions open`);
  if(d.news_block) row("n", `News blackout: ${E(d.news_block.title)} (${E(d.news_block.phase)})`);
  else { const n = (d.news || [])[0]; row(n && n.minutes_to != null && n.minutes_to < 60 ? "w" : "y", n ? `Next: ${E(n.title)} in ${Math.round(n.minutes_to)} min (${E(n.tier)})` : "No US news in the next 8 hours"); }
  row(b.label && b.label !== "NEUTRAL" ? "y" : "w", sym ? `${E(sym)} bias ${E(b.label || "—")} — D${b.d ?? "·"} 4H${b.h4 ?? "·"} 1H${b.h1 ?? "·"}` : "No tradable symbol");
  if(b.pdh != null) row("y", `${E(sym)} prior day high ${fmt(b.pdh, 2)} · low ${fmt(b.pdl, 2)}`);
  return `<div class="lv-check">${out.join("")}</div>`;
}
function wireDesk(){
  const el = $("#lv-desk"), msg = (t, ok) => { const m = $("#ctlMsg"); if(m){ m.textContent = t; m.className = "lv-msg " + (ok ? "up" : "down"); } };
  el.querySelectorAll("[data-ctl]").forEach(b => b.onclick = async () => {
    const a = b.dataset.ctl;
    if(a === "flatten" && !armed.flatten){ armed.flatten = true; renderDesk(); setTimeout(() => { armed.flatten = false; if(page === "desk") renderDesk(); }, 4000); return; }
    armed.flatten = false;
    try{ await J("api/control/" + a, {}); msg(a === "flatten" ? "Flatten sent — every position is being closed" : a === "pause" ? "New entries paused" : "Entries resumed", true); }
    catch(e){ msg(e.message, false); }
    loadDesk();
  });
  el.querySelectorAll(".lv-pos").forEach(card => {
    const id = card.dataset.id, m = card.querySelector("[data-msg]");
    const say = (t, ok) => { m.textContent = t; m.className = "lv-msg " + (ok ? "up" : "down"); };
    card.querySelectorAll("[data-act]").forEach(b => b.onclick = async () => {
      const act = b.dataset.act, key = id + ":" + act;
      if(act === "close" && !armed[key]){ armed[key] = true; renderDesk(); setTimeout(() => { delete armed[key]; if(page === "desk") renderDesk(); }, 4000); return; }
      delete armed[key];
      b.disabled = true;
      try{
        if(act === "note"){
          await J("api/trades/" + encodeURIComponent(id) + "/note", {note: card.querySelector('[data-keep^="note:"]').value});
          say("Note saved", true); b.disabled = false; return;
        }
        const body = {action: act, id};
        if(act === "stop"){ const v = parseFloat(card.querySelector('[data-keep^="stop:"]').value); if(!isFinite(v)){ say("Type a stop price first", false); b.disabled = false; return; } body.price = v; }
        if(act === "partial") body.frac = parseFloat(b.dataset.frac);
        const r = await J("api/live/manual", body);
        say(r.msg || (r.ok ? "Done" : "Not done"), r.ok);
        if(r.ok && act === "stop") card.querySelector('[data-keep^="stop:"]').value = "";
      }catch(e){ say(e.message, false); }
      b.disabled = false;
      setTimeout(loadDesk, 600);
    });
  });
}

/* ════════════════ JOURNAL & REVIEW ════════════════ */
let JR = null, jDays = 30, jOpen = null;
async function loadJournal(){
  try{ JR = await J("api/live/review?days=" + jDays); }catch(e){ $("#lv-journal").innerHTML = `<div class="lv-card">${E(e.message)}</div>`; return; }
  renderJournal();
}
function table(obj, label, sortByR){
  const rows = Object.entries(obj).sort((a, b) => sortByR ? a[1].r - b[1].r : 0);
  if(!rows.length) return `<div class="mut" style="font-size:13px">Nothing yet.</div>`;
  return `<table class="lv-tbl"><thead><tr><th>${label}</th><th>Trades</th><th>Win</th><th>Total R</th><th>Avg</th></tr></thead><tbody>${
    rows.map(([k, v]) => `<tr><td>${E(k)}</td><td class="num">${v.n}</td><td class="num">${Math.round(v.wins / v.n * 100)}%</td><td class="num ${cls(v.r)}">${R(v.r)}</td><td class="num ${cls(v.r)}">${R(v.r / v.n)}</td></tr>`).join("")}</tbody></table>`;
}
function renderJournal(){
  const d = JR, el = $("#lv-journal");
  const seg = `<div class="lv-seg">${[7, 30, 90].map(n => `<button data-days="${n}" class="${n === jDays ? "on" : ""}">${n} days</button>`).join("")}</div>`;
  const hours = Object.entries(d.by_hour).sort((a, b) => +a[0] - +b[0]);
  const worst = Object.entries(d.by_tag).filter(([, v]) => v.r < 0).sort((a, b) => a[1].r - b[1].r)[0];
  const insight = worst ? `Trades tagged <b>${E(worst[0])}</b> cost ${R(worst[1].r)} over ${worst[1].n} trades.` :
    d.reviewed ? "No losing habit stands out yet." : "Tag a few trades to see which habits make and cost money.";
  el.innerHTML = `<div class="lv-card"><h3>Review ${seg}</h3>
      <div class="lv-kpis"><div class="lv-kpi"><div class="l">Trades</div><div class="v num">${d.n}</div></div>
      <div class="lv-kpi"><div class="l">Total</div><div class="v num ${cls(d.sum_r)}">${R(d.sum_r)}</div></div>
      <div class="lv-kpi"><div class="l">Win rate</div><div class="v num">${Math.round(d.win_rate * 100)}%</div></div>
      <div class="lv-kpi"><div class="l">Reviewed</div><div class="v num">${d.reviewed}<small class="mut"> / ${d.n}</small></div></div></div>
      <p style="font-size:13.5px;margin:12px 0 0">${insight}</p></div>
    <div class="lv-card s6"><h3>By habit (your tags)</h3>${table(d.by_tag, "Tag", true)}</div>
    <div class="lv-card s6"><h3>By setup</h3>${table(d.by_setup, "Setup", true)}</div>
    <div class="lv-card"><h3>By hour (NY)</h3>${hours.length ? `<table class="lv-tbl"><thead><tr><th>Hour</th><th>Trades</th><th>Total R</th></tr></thead><tbody>${hours.map(([h, v]) => `<tr><td>${String(h).padStart(2, "0")}:00</td><td class="num">${v.n}</td><td class="num ${cls(v.r)}">${R(v.r)}</td></tr>`).join("")}</tbody></table>` : `<div class="mut">Nothing yet.</div>`}</div>
    <div class="lv-card"><h3>Trades <span class="sp"></span><span class="mut" style="font-weight:500;font-size:12px">tap one to review it</span></h3><div class="lv-list">${
      d.trades.map(t => `<div class="lv-row" data-tid="${E(t.id)}" style="cursor:pointer"><span class="num mut">${E(md(t.closed))} ${E(hm(t.closed))}</span>
        <b>${E(t.symbol)}</b><span class="side ${String(t.side)[0]}">${E(t.side)}</span><span class="grow mut">${t.tags.length ? E(t.tags.join(", ")) : (t.note ? E(t.note) : "not reviewed")}</span>
        <b class="num ${cls(t.r)}">${R(t.r)}</b></div>${jOpen === t.id ? editor(t) : ""}`).join("") || `<div class="mut">No closed trades in this period.</div>`}</div></div>`;
  el.querySelectorAll("[data-days]").forEach(b => b.onclick = () => { jDays = +b.dataset.days; loadJournal(); });
  el.querySelectorAll("[data-tid]").forEach(r => r.onclick = () => { jOpen = jOpen === r.dataset.tid ? null : r.dataset.tid; renderJournal(); });
  wireEditor();
}
function editor(t){
  return `<div class="lv-card" data-ed="${E(t.id)}" style="margin:6px 0 10px;background:var(--card-2)">
    <div class="mut" style="font-size:12px;margin-bottom:8px">${E(t.strategy)} · exit ${E(t.exit || "")} · ${smoney(t.pnl, 0)}</div>
    <div class="lv-tags">${JR.tags.map(g => `<button type="button" data-tag="${E(g)}" aria-pressed="${t.tags.includes(g)}">${E(g)}</button>`).join("")}</div>
    <div class="lv-stars" style="margin-top:8px" aria-label="Grade">${[1,2,3,4,5].map(n => `<button type="button" data-g="${n}" class="${(t.grade||0) >= n ? "on" : ""}" aria-label="${n} of 5">★</button>`).join("")}</div>
    <div class="lv-inline"><input data-f="note" placeholder="What happened" value="${E(t.note)}"></div>
    <div class="lv-inline"><input data-f="lesson" placeholder="Lesson for next time" value="${E(t.lesson)}"></div>
    <div class="lv-acts" style="margin-top:8px"><button class="lv-btn pri" data-save>Save review</button><button class="lv-btn" data-chart>Open chart</button></div>
    <div class="lv-msg" data-m></div></div>`;
}
function wireEditor(){
  const ed = $("#lv-journal [data-ed]"); if(!ed) return;
  const t = JR.trades.find(x => x.id === ed.dataset.ed);
  let grade = t.grade || null;
  ed.onclick = e => e.stopPropagation();
  ed.querySelectorAll("[data-tag]").forEach(b => b.onclick = () => b.setAttribute("aria-pressed", b.getAttribute("aria-pressed") !== "true"));
  ed.querySelectorAll("[data-g]").forEach(b => b.onclick = () => { grade = +b.dataset.g; ed.querySelectorAll("[data-g]").forEach(x => x.classList.toggle("on", +x.dataset.g <= grade)); });
  ed.querySelector("[data-save]").onclick = async () => {
    const body = {tags: [...ed.querySelectorAll('[data-tag][aria-pressed="true"]')].map(b => b.dataset.tag), grade,
      note: ed.querySelector('[data-f="note"]').value, lesson: ed.querySelector('[data-f="lesson"]').value};
    try{ await J("api/live/review/" + encodeURIComponent(t.id), body); Object.assign(t, body); ed.querySelector("[data-m]").textContent = "Saved"; ed.querySelector("[data-m]").className = "lv-msg up"; }
    catch(e){ ed.querySelector("[data-m]").textContent = e.message; ed.querySelector("[data-m]").className = "lv-msg down"; }
  };
  ed.querySelector("[data-chart]").onclick = async () => {
    try{ const rows = await J("api/trades?limit=1000"); const full = rows.find(x => x.id === t.id); if(full) openTrade(full); }catch(e){}
  };
}

/* ════════════════ COMPARE (live) ════════════════ */
let LC = null, lcRange = "month";
async function loadCompare(){
  try{ LC = await J("api/live/compare?range=" + lcRange); }catch(e){ $("#lv-lcompare").innerHTML = `<div class="lv-card">${E(e.message)}</div>`; return; }
  const el = $("#lv-lcompare"), d = LC;
  const name = b => b.book === "live" ? "Live account" : ModeName(b.mode || b.book);
  const seg = `<div class="lv-seg">${[["week","Week"],["month","Month"],["quarter","Quarter"],["all","All"]].map(([k, t]) => `<button data-r="${k}" class="${k === lcRange ? "on" : ""}">${t}</button>`).join("")}</div>`;
  const cards = d.books.map(b => `<div class="lv-book"><div class="nm"><i class="dot" style="background:${bookColor(b.book)}"></i>${E(name(b))}${b.paper ? `<span class="paper">PAPER</span>` : `<span class="real">REAL</span>`}</div>
    <div class="big num ${cls(b.sum_r)}">${R(b.sum_r)}</div>
    <div class="mut num" style="font-size:12px">${b.trades} trades · ${Math.round(b.win_rate * 100)}% win · avg ${R(b.avg_r)}</div>
    <div class="mut num" style="font-size:12px">best day ${R(b.best_day)} · worst ${R(b.worst_day)}</div></div>`).join("");
  el.innerHTML = `<div class="lv-card"><h3>Books ${seg}</h3><div class="lv-books">${cards}</div>
      <div class="mut" style="font-size:12px;margin-top:10px">Paper books trade the same prices with simulated fills (no slippage, no rejections), so the real account usually trails them a little. Under ~20 trades a lead is mostly luck.</div></div>
    <div class="lv-card"><h3>Cumulative R</h3>${curve(d.books, name)}</div>
    ${instrumentTable(d.books.map(b => ({...b, symbols: b.symbols})))}
    ${d.copies ? `<div class="lv-card"><h3>Members' copies</h3><div class="lv-kpis">
      <div class="lv-kpi"><div class="l">Copied</div><div class="v num">${d.copies.copied}</div></div>
      <div class="lv-kpi"><div class="l">Closed, total R</div><div class="v num ${cls(d.copies.sum_r)}">${R(d.copies.sum_r)}</div><div class="s">${d.copies.closed} trades, all members</div></div>
      <div class="lv-kpi"><div class="l">Skipped</div><div class="v num">${d.copies.skipped}</div><div class="s">limits, size, late</div></div>
      <div class="lv-kpi"><div class="l">Failed</div><div class="v num ${d.copies.failed ? "down" : ""}">${d.copies.failed}</div><div class="s">see Members</div></div></div></div>` : ""}`;
  el.querySelectorAll("[data-r]").forEach(b => b.onclick = () => { lcRange = b.dataset.r; loadCompare(); });
}
function curve(books, name){
  const all = books.flatMap(b => b.curve.map(c => c[0])); const days = [...new Set(all)].sort();
  if(days.length < 2) return `<div class="mut" style="font-size:13px">The curve appears after two trading days.</div>`;
  const W = 700, H = 200, P = 28, vals = books.flatMap(b => b.curve.map(c => c[1])).concat([0]);
  const lo = Math.min(...vals), hi = Math.max(...vals), sy = v => H - P - (v - lo) / ((hi - lo) || 1) * (H - 2 * P), sx = i => P + i / (days.length - 1) * (W - 2 * P);
  const lines = books.map(b => { const m = Object.fromEntries(b.curve); let last = 0;
    const pts = days.map((dd, i) => { if(m[dd] != null) last = m[dd]; return `${sx(i).toFixed(1)},${sy(last).toFixed(1)}`; });
    return `<polyline fill="none" stroke="${bookColor(b.book)}" stroke-width="${b.book === "live" ? 3 : 1.8}" ${b.book === "live" ? "" : 'stroke-dasharray="5 4"'} points="${pts.join(" ")}"><title>${E(name(b))}</title></polyline>`; }).join("");
  return `<svg class="lv-curve" viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" role="img" aria-label="Cumulative R by book">
    <line x1="${P}" x2="${W - P}" y1="${sy(0)}" y2="${sy(0)}" stroke="var(--line-2)"/>${lines}</svg>
    <div class="mut" style="font-size:12px;display:flex;gap:12px;flex-wrap:wrap">${books.map(b => `<span><i class="dot" style="background:${bookColor(b.book)}"></i>${E(name(b))}</span>`).join("")}</div>`;
}

/* ════════════════ MEMBERS ════════════════ */
let MB = null, lastInvite = null;
async function loadMembers(){
  try{ MB = await J("api/live/members"); }catch(e){ $("#lv-members").innerHTML = `<div class="lv-card">${E(e.message)}</div>`; return; }
  let audit = []; try{ audit = (await J("api/live/audit?limit=60")).rows; }catch(e){}
  const el = $("#lv-members"), s = MB.settings;
  const users = MB.users.filter(u => u.role === "member");
  el.innerHTML = `<div class="lv-card"><h3>Copying onto members' accounts</h3>
      <div class="lv-switch"><div style="flex:1"><b>${s.copy_enabled ? "On" : "Off"} for everyone</b><small>Members' trades copy only when this is on, you approved them, and they switched it on themselves. Symbols: ${E((s.copy_symbols || []).join(", "))}. Member risk cap ${(s.max_member_risk_pct * 100).toFixed(2)}% / trade.</small></div>
        <button class="lv-btn ${s.copy_enabled ? "danger" : "pri"}" id="mbSwitch">${s.copy_enabled ? "Switch off" : "Switch on"}</button></div>
      <div class="lv-inline" id="mbCodeRow" hidden><input id="mbCode" inputmode="numeric" autocomplete="one-time-code" placeholder="Authenticator code to confirm"><button class="lv-btn pri" id="mbConfirm">Confirm</button></div>
      <div class="lv-msg" id="mbMsg"></div>
      <p class="mut" style="font-size:12px;margin:8px 0 0">Placing trades on other people's accounts may need registration with your securities regulator. Check before switching this on for anyone but yourself.</p></div>
    <div class="lv-card"><h3>Members <span class="sp"></span><button class="lv-btn" id="mbInvite">New invite</button></h3>
      ${lastInvite ? `<div class="lv-msg up">Invite for ${E(lastInvite.note || "a member")} — valid ${lastInvite.hours} h, shown once:</div><div class="lv-oncecode" id="mbLink">${E(location.origin + location.pathname.replace(/\/$/, "") + "/" + lastInvite.link)}</div><button class="lv-btn" id="mbCopy" style="margin-top:8px">Copy link</button>` : ""}
      <div class="lv-inline" id="mbNoteRow" hidden><input id="mbNote" placeholder="Who is it for? (only you see this)"><button class="lv-btn pri" id="mbMake">Create</button></div>
      <div style="overflow-x:auto;margin-top:10px"><table class="lv-tbl"><thead><tr><th>Member</th><th>Key</th><th>Their switch</th><th>Risk</th><th>Copied R</th><th>Approved</th></tr></thead><tbody>${
        users.map(u => { const m = u.member || {}; return `<tr><td><b>${E(u.name)}</b>${u.disabled ? ` <span class="mut">(disabled)</span>` : ""}${m.last_error ? `<div class="down" style="font-size:11.5px">${E(m.last_error)}</div>` : ""}</td>
          <td>${m.has_key ? `${E(m.environment)} ${E(m.token_mask)}` : `<span class="mut">none</span>`}</td><td>${m.copy_on ? "on" : "off"}</td>
          <td class="num">${((m.risk_pct || 0) * 100).toFixed(2)}%</td><td class="num ${cls(u.copies && u.copies.sum_r)}">${u.copies ? R(u.copies.sum_r) + ` <span class="mut">(${u.copies.trades})</span>` : "—"}</td>
          <td style="white-space:nowrap"><button class="lv-btn" data-appr="${u.id}" data-v="${m.approved ? 0 : 1}">${m.approved ? "Approved" : "Approve"}</button>
              <button class="lv-btn danger" data-dis="${u.id}" data-v="${u.disabled ? 0 : 1}">${u.disabled ? "Enable" : "Disable"}</button></td></tr>`; }).join("") ||
        `<tr><td colspan="6" class="mut">No members yet — create an invite.</td></tr>`}</tbody></table></div></div>
    <div class="lv-card"><h3>Audit log</h3><div class="lv-list">${audit.map(a => `<div class="lv-row"><span class="num mut">${new Date(a.ts * 1000).toLocaleString([], {month:"short", day:"numeric", hour:"2-digit", minute:"2-digit"})}</span><b>${E(a.name || "—")}</b><span class="grow mut">${E(a.action)} ${E(a.detail || "")}</span></div>`).join("")}</div></div>`;
  const msg = (t, ok) => { const m = $("#mbMsg"); m.textContent = t; m.className = "lv-msg " + (ok ? "up" : "down"); };
  $("#mbSwitch").onclick = () => { $("#mbCodeRow").hidden = false; $("#mbCode").focus(); };
  $("#mbConfirm").onclick = async () => {
    try{ await J("api/live/settings", {copy_enabled: !s.copy_enabled, code: $("#mbCode").value}); loadMembers(); }catch(e){ msg(e.message, false); } };
  $("#mbInvite").onclick = () => { $("#mbNoteRow").hidden = false; $("#mbNote").focus(); };
  $("#mbMake").onclick = async () => { try{ lastInvite = await J("api/live/invite", {note: $("#mbNote").value}); lastInvite.note = $("#mbNote").value; loadMembers(); }catch(e){ msg(e.message, false); } };
  if($("#mbCopy")) $("#mbCopy").onclick = () => { try{ navigator.clipboard.writeText($("#mbLink").textContent); $("#mbCopy").textContent = "Copied"; }catch(e){} };
  el.querySelectorAll("[data-appr]").forEach(b => b.onclick = async () => { try{ await J("api/live/members/" + b.dataset.appr, {approved: b.dataset.v === "1"}); }catch(e){ msg(e.message, false); } loadMembers(); });
  el.querySelectorAll("[data-dis]").forEach(b => b.onclick = async () => { try{ await J("api/live/members/" + b.dataset.dis, {disabled: b.dataset.v === "1"}); }catch(e){ msg(e.message, false); } loadMembers(); });
}

/* ════════════════ ACCOUNT SECURITY ════════════════ */
async function loadAccount(){
  let me = null; try{ me = await J("api/live/me"); }catch(e){}
  const el = $("#lv-account");
  el.innerHTML = `<div class="lv-card s6"><h3>Signed in as ${E(me ? me.user : L.user)}</h3><div class="lv-list">${(me ? me.sessions : []).map(s => `<div class="lv-row"><span class="grow">${E((s.ua || "").replace(/\).*$/, ")").slice(0, 60))}</span><span class="mut num">${E(s.ip || "")}</span><span class="mut">${ago(new Date(s.seen * 1000).toISOString())} ago</span></div>`).join("")}</div>
      <a class="lv-btn" href="logout" style="display:inline-flex;margin-top:12px;text-decoration:none">Sign out on this device</a></div>
    <div class="lv-card s6"><h3>Change password</h3>
      <div class="lv-inline"><input id="pwOld" type="password" autocomplete="current-password" placeholder="Current password"></div>
      <div class="lv-inline"><input id="pwNew" type="password" autocomplete="new-password" placeholder="New password (12+ characters)"></div>
      <button class="lv-btn pri" id="pwSave" style="margin-top:8px">Change password</button><div class="lv-msg" id="pwMsg"></div>
      <p class="mut" style="font-size:12px">Lost your phone? On the server: <code>./fx.sh live reset-2fa ${E(L.user || "name")}</code></p></div>`;
  $("#pwSave").onclick = async () => { const m = $("#pwMsg");
    try{ const r = await J("api/live/password", {old: $("#pwOld").value, new: $("#pwNew").value}); m.textContent = r.msg; m.className = "lv-msg up"; setTimeout(() => location.href = "./", 1500); }
    catch(e){ m.textContent = e.message; m.className = "lv-msg down"; } };
}

document.addEventListener("click", e => { if(e.target.closest("#symUnit button") && page === "lcompare") setTimeout(loadCompare, 0); });

/* land on the desk */
const h = location.hash.slice(1);
go(PAGES[h] || titles[h] ? h : "desk");
})();
