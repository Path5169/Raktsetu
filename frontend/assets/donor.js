const $=s=>document.querySelector(s), app=$("#app");
const esc=t=>String(t??"").replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
const G=g=>g.slice(0,-1)+"<sup>"+(g.endsWith("+")?"+":"\u2212")+"</sup>";
const fmt=d=>new Date(d+"T00:00").toLocaleDateString("en-IN",{day:"numeric",month:"short",year:"numeric"});
const NAME={RBC:"whole blood",PLT:"platelets"};
let token=sessionStorage.getItem("rs_token"), phone="", timer=null, presenceWatch=null, step="phone";

function toast(m,err){const t=$("#toast");t.textContent=m;t.className="on"+(err?" err":"");clearTimeout(t.h);t.h=setTimeout(()=>t.className="",3600)}
async function api(url,body){
  const r=await fetch(url,{method:body?"POST":"GET",headers:token?{Authorization:"Bearer "+token}:{},body:body?JSON.stringify(body):undefined});
  let d={};try{d=await r.json()}catch(e){}
  if(r.status===401&&token){logout(true)}
  return[r.ok,d]
}
function logout(expired){token=null;sessionStorage.removeItem("rs_token");clearInterval(timer);if(presenceWatch!==null&&navigator.geolocation)navigator.geolocation.clearWatch(presenceWatch);presenceWatch=null;step="phone";$("#out").hidden=true;if(expired)toast("Please log in again.",true);login()}
$("#out").onclick=()=>logout();

/* ---------- login ---------- */
async function login(demo){
  if(step==="phone"){
    app.innerHTML=`<div class="card"><h2>Donor login</h2><h3>Enter your mobile number</h3><p class="soft">We send a one-time code. In this demo the code is shown on screen instead of by SMS.</p>
      <form id="pf"><label class="soft" for="ph">Mobile number</label><input id="ph" inputmode="numeric" autocomplete="tel" placeholder="10-digit number" value="${esc(phone)}">
      <div class="row"><button class="btn red">Send code</button></div><div class="err" id="e" role="alert"></div></form>
      <details id="dm"><summary>Demo donors (tap to fill in)</summary><div id="dl" class="soft" style="margin-top:6px">Loading...</div></details></div>`;
    $("#pf").onsubmit=async e=>{e.preventDefault();phone=$("#ph").value;const[ok,d]=await api("/api/donor/otp/send",{phone});
      if(!ok)return $("#e").textContent=d.error;phone=d.phone;step="otp";demoCode=d.demo_otp;login()};
    $("#dm").addEventListener("toggle",async()=>{if(!$("#dm").open||$("#dl").dataset.on)return;$("#dl").dataset.on=1;
      const[ok,l]=await api("/api/donor/demo");$("#dl").innerHTML=ok?l.map(x=>`<button type="button" data-p="${esc(x.phone)}">${esc(x.name)} <span>${esc(x.blood_group)} \u00b7 ${esc(x.phone)}</span></button>`).join(""):"Not available."});
    $("#dl").onclick=e=>{const b=e.target.closest("button");if(b){$("#ph").value=b.dataset.p;$("#ph").focus()}};
    return}
  app.innerHTML=`<div class="card"><h2>Donor login</h2><h3>Enter the code</h3><p class="soft">Sent to ${esc(phone)}. It works for 5 minutes.</p>
    ${demoCode?`<div class="demo">Demo mode: no SMS is sent. Your code is <b>${esc(demoCode)}</b></div>`:""}
    <form id="of"><label class="soft" for="otp" style="display:block;margin-top:12px">6-digit code</label><input id="otp" inputmode="numeric" autocomplete="one-time-code" maxlength="6">
    <div class="row"><button class="btn red">Log in</button><button type="button" class="btn ghost" id="back">Use another number</button></div><div class="err" id="e" role="alert"></div></form></div>`;
  $("#otp").focus();$("#back").onclick=()=>{step="phone";login()};
  $("#of").onsubmit=async e=>{e.preventDefault();const[ok,d]=await api("/api/donor/otp/verify",{phone,otp:$("#otp").value});
    if(!ok)return $("#e").textContent=d.error;token=d.token;sessionStorage.setItem("rs_token",token);demoCode=null;start()}
}
let demoCode=null;

/* ---------- home ---------- */
function eligCard(p){
  const e=p.eligibility;
  if(e.eligible)return `<div class="card elig"><h2>Eligibility</h2><div class="big">You can donate now</div><p class="soft">Meets the age, weight and gap rules. Blood banks near you may call when someone needs your group.</p></div>`;
  if(e.days_left!==null){
    const pct=Math.round((e.progress||0)*100);
    return `<div class="card elig wait"><h2>Eligibility</h2><div class="big">Eligible in ${e.days_left} day${e.days_left===1?"":"s"}</div>
      <p>${e.next_date?"From "+fmt(e.next_date)+".":""}</p>${p.last_donation&&e.gap_days?`<div class="bar" role="img" aria-label="${pct}% of the waiting period done"><i style="width:${pct}%"></i></div><p class="soft">${pct}% of the ${e.gap_days}-day gap since your last donation.</p>`:""}
      <ul class="reasons">${e.reasons.map(r=>`<li>${esc(r)}</li>`).join("")}</ul></div>`}
  return `<div class="card elig no"><h2>Eligibility</h2><div class="big">Not eligible at the moment</div><ul class="reasons">${e.reasons.map(r=>`<li>${esc(r)}</li>`).join("")}</ul></div>`}

function badgeCard(p){
  const b=p.badge,tiers=[1,3,5,10],n=b.donations;
  return `<div class="card"><h2>Your impact</h2><div class="stats">
    <div class="stat"><b>${n}</b><span class="soft">verified donation${n===1?"":"s"}</span></div>
    <div class="stat"><b>${p.streak?p.streak+" in a row":"\u2013"}</b><span class="soft">${p.streak?"streak, keep it going":"no active streak"}</span></div></div>
    <p style="margin-top:12px">${b.name?`Badge: <b>${esc(b.name)}</b>`:"No badge yet. Your first verified donation earns <b>First Drop</b>."}</p>
    <div class="pips" aria-hidden="true">${tiers.map(t=>`<i class="${n>=t?"on":""}"></i>`).join("")}</div>
    <p class="soft">${b.next?`${b.next.needs} more verified donation${b.next.needs===1?"":"s"} to <b>${esc(b.next.name)}</b>.`:"Top badge reached. Thank you."}
    A donation counts once the blood bank verifies it. A streak breaks after a gap of about six months.</p></div>`}

function callCard(c){
  const left=c.slots_needed-c.slots_filled,mine=c.response==="accepted";
  let tag,body;
  if(mine){tag='<span class="tag ok">You are confirmed</span>';body=`<p>Please go to <b>${esc(c.bank)}</b>. They will verify your donation.</p>`}
  else if(c.response==="declined"){tag='<span class="tag off">You passed</span>';body=""}
  else if(c.status==="open"){tag='<span class="tag">Needed now</span>';
    body=`<p>${left} donor${left===1?"":"s"} still needed at <b>${esc(c.bank)}</b>, ${c.km} km from you. First to accept gets the slot.</p>
      <div class="row"><button class="btn red" data-a="accept" data-c="${c.id}">Accept</button><button class="btn ghost" data-a="decline" data-c="${c.id}">Not now</button></div>`}
  else{tag='<span class="tag off">Already covered</span>';body='<p class="soft">Other donors have filled every slot. Thank you for being ready to help.</p>'}
  return `<div class="call ${c.status==="open"&&!c.response?"open":""}"><div style="display:flex;justify-content:space-between;align-items:center;gap:8px;flex-wrap:wrap">
    <h3>${G(c.blood_group)} ${NAME[c.component]}</h3>${tag}</div>${c.hospital?`<p class="soft">For a patient at ${esc(c.hospital)}</p>`:`<p class="soft">${esc(c.reason||"Stock is low")}</p>`}${body}</div>`}

function render(p){
  const hist=p.history;
  app.innerHTML=`<div class="card"><div class="hero"><div class="grp" aria-label="Blood group ${esc(p.blood_group)}">${G(p.blood_group)}</div>
      <div><h3>${esc(p.name)}</h3><p class="soft" style="margin:2px 0 0">${p.sex==="F"?"Woman":"Man"}, ${p.eligibility.age??"?"} years, ${p.weight_kg??"?"} kg</p></div></div></div>
    ${eligCard(p)}
    <div class="card"><h2>Requests for you</h2>${p.calls.length?p.calls.map(callCard).join(""):'<p class="soft">Nothing right now. We only contact you when your group is needed nearby and you are eligible, never as a broadcast.</p>'}</div>
    ${badgeCard(p)}
    <div class="card"><h2>Donation history</h2>${hist.length?`<table>${hist.map(h=>`<tr><td>${h.status==="verified"?fmt(h.date):'<span class="pend">Waiting for blood bank to verify</span>'}</td><td>${esc(h.bank||"")}</td></tr>`).join("")}</table>`:'<p class="soft">No donations yet.</p>'}</div>`;
}
async function refresh(){const[ok,p]=await api("/api/donor/me");if(ok)render(p)}
function startPresence(){
  if(!token||!navigator.geolocation||presenceWatch!==null)return;
  console.log("Initializing live donor tracking...");
  presenceWatch=navigator.geolocation.watchPosition(
    p=>{
      const lat=p.coords.latitude, lon=p.coords.longitude;
      console.log(`Presence update: ${lat},${lon}`);
      api("/api/donor/presence",{lat,lon});
    },
    err=>{
      console.warn("Location error:", err.message);
      if(err.code===1) toast("Location permission denied. Live tracking is disabled.", true);
    },
    {enableHighAccuracy:true, maximumAge:30000, timeout:20000}
  );
}
function start(){$("#out").hidden=false;refresh();startPresence();clearInterval(timer);timer=setInterval(refresh,6000)}

app.addEventListener("click",async e=>{
  const b=e.target.closest("button[data-a]");if(!b)return;b.disabled=true;
  const[ok,d]=await api("/api/donor/"+b.dataset.a,{call_id:b.dataset.c});
  if(!ok){toast(d.error||"Something went wrong.",true)}
  else if(b.dataset.a==="accept")toast(d.message,!d.won);
  refresh()});
if(token)start();else login();
