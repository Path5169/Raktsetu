const $=s=>document.querySelector(s);
const esc=t=>String(t).replace(/[&<>\"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'\"':"&quot;"}[c]));
const G=g=>g.slice(0,-1)+"<sup>"+(g.endsWith("+")?"+":"\u2212")+"</sup>";
const NAME={RBC:"red cells",PLT:"platelets"};
const ACT={ADD_UNITS:"Stock added",SEED:"Demo data loaded",EXPIRE_SWEEP:"Expired units cleared"};
let S=null,N=null,comp="RBC",sel=null,ready=false,loading=false,map=null,mapLayer=null;

async function load(){
  if(loading)return;
  loading=true; setConnection("syncing");
  try{
    const r=await fetch("/api/state",{cache:"no-store"});
    if(!r.ok)throw new Error(`Backend returned ${r.status}`);
    S=await r.json();
    const nr=await fetch("/api/network",{cache:"no-store"});
    if(!nr.ok)throw new Error(`Network API returned ${nr.status}`);
    N=await nr.json(); ready=true; render(); renderNetworkMap(); setConnection("connected");
  }catch(err){
    ready=false; setConnection("offline");
    toast("Live backend unavailable. Start the RaktSetu server at http://127.0.0.1:8000.",true);
    console.error("RaktSetu API connection failed",err);
  }finally{loading=false}
}
function setConnection(state){const el=$("#api-status");if(!el)return;el.dataset.state=state;el.querySelector("b").textContent=state==="connected"?"Backend connected":state==="syncing"?"Syncing live data":"Backend offline";el.querySelector("small").textContent=state==="connected"?"Live API · updated just now":state==="syncing"?"Contacting /api/state":"Start python -m raktsetu serve"}
const total=g=>S?Object.values(S.stock[comp][g]).reduce((a,b)=>a+b,0):0;
function render(){
  document.body.classList.toggle("plt",comp==="PLT");
  $("#c-RBC").setAttribute("aria-pressed",comp==="RBC");$("#c-PLT").setAttribute("aria-pressed",comp==="PLT");
  const max=Math.max(1,...S.groups.map(total));
  const bagHtml=S.groups.map(g=>{const n=total(g),h=n?Math.max(14,n/max*88):0;return `<button class="bag ${n===0?"zero":n<=2?"low":""}" data-g="${g}" aria-pressed="${sel===g}" aria-label="${g}, ${n} units"><div class="fill" style="height:${h}%"></div><div class="label"><b>${G(g)}</b><span>${n===0?"None left":n<=2?n+" left":n+" units"}</span></div></button>`}).join("");
  const bagsEl=$("#bags");
  if(bagsEl.dataset.sig!==bagHtml){const first=!bagsEl.dataset.sig;bagsEl.innerHTML=bagHtml;bagsEl.dataset.sig=bagHtml;if(first){bagsEl.classList.add("boot");setTimeout(()=>bagsEl.classList.remove("boot"),1600)}}
  $("#exp").innerHTML=S.expiring.length?S.expiring.map((r,i)=>{const d=Math.round((new Date(r.expires_on)-new Date(S.today))/864e5);return `<button class="row" data-i="${i}"><span class="days ${d<=1?"hot":""}">${d===0?"today":d+" day"+(d>1?"s":"")}</span><span>${r.n} × ${G(r.blood_group)} ${NAME[r.component]}<small>${esc(r.bank)}</small></span></button>`}).join(""):'<p class="empty">Nothing expires in the next 3 days.</p>';
  $("#log").innerHTML=S.audit.map(a=>`<li>${ACT[a.action]||esc(a.action)}<small>${esc(a.detail)}</small></li>`).join("");
  calls();detail();fillReq();fillBroadcast();renderNetwork();
}
function renderNetwork(){
  const el=$("#network-nodes"); if(!el||!S)return;
  const positions=[["17%","48%"],["35%","24%"],["51%","67%"],["67%","28%"],["78%","56%"],["88%","20%"],["74%","82%"],["45%","87%"]];
  el.innerHTML=S.groups.map((g,i)=>{const n=total(g),p=positions[i%positions.length];return `<button class="node3d ${n<3?"node-low":""}" data-g="${g}" style="--x:${p[0]};--y:${p[1]};--delay:${i*.18}s" aria-label="Open ${g}, ${n} units"><span class="node-pulse"></span><strong>${G(g)}</strong><small>${n}u</small></button>`}).join("");
}
function markerIcon(type,label){return L.divIcon({className:`leaflet-marker marker-${type}`,html:`<span>${label}</span>`,iconSize:[28,28],iconAnchor:[14,14]})}
const curTheme=()=>document.documentElement.dataset.theme||"light";let tileBase=null,schem=null;
const tileUrl=()=>"https://{s}.basemaps.cartocdn.com/"+(curTheme()==="dark"?"dark_all":"light_all")+"/{z}/{x}/{y}{r}.png";
function applyTheme(t,save){const r=document.documentElement;r.classList.add("theming");r.dataset.theme=t;const l=document.getElementById("theme-light");if(l)l.media=t==="light"?"all":"not all";if(save)try{localStorage.setItem("raktsetu-theme",t)}catch(e){}const b=$("#theme-toggle");if(b){b.setAttribute("aria-pressed",t==="dark");b.title=t==="dark"?"Switch to light theme":"Switch to dark theme"}if(tileBase){tileBase.setUrl(tileUrl())}if(schem)schem.redraw();setTimeout(()=>r.classList.remove("theming"),450)}
document.addEventListener("click",e=>{if(e.target.closest("#theme-toggle"))applyTheme(curTheme()==="dark"?"light":"dark",true)});
const mk=new Map();
function upsert(key,ik,lat,lon,mkIcon,popup){let m=mk.get(key);if(m){m.setLatLng([lat,lon]);if(m._ik!==ik){m.setIcon(mkIcon());m._ik=ik}m.setPopupContent(popup)}else{m=L.marker([lat,lon],{icon:mkIcon()}).bindPopup(popup).addTo(mapLayer);m._ik=ik;mk.set(key,m)}m._seen=true}
function renderNetworkMap(){
  if(!N||!window.L||!$("#network-map"))return;
  const el=$("#network-map");
  if(!map){
    el.classList.add("is-loading");
    map=L.map(el,{zoomControl:true,scrollWheelZoom:false,zoomSnap:.5}).setView(N.center,12);
    const Schematic=L.GridLayer.extend({createTile(c){const t=document.createElement("canvas"),s=this.getTileSize();t.width=s.x;t.height=s.y;const g=t.getContext("2d"),D=curTheme()==="dark";g.fillStyle=D?"#0b1b2d":"#e6edf4";g.fillRect(0,0,s.x,s.y);
      const step=s.x/4;g.lineWidth=1;g.strokeStyle=D?"rgba(120,175,200,.09)":"rgba(30,70,110,.08)";g.beginPath();for(let i=1;i<4;i++){g.moveTo(i*step+.5,0);g.lineTo(i*step+.5,s.y);g.moveTo(0,i*step+.5);g.lineTo(s.x,i*step+.5)}g.stroke();
      g.strokeStyle=D?"rgba(120,175,200,.2)":"rgba(30,70,110,.16)";g.beginPath();g.moveTo(.5,0);g.lineTo(.5,s.y);g.moveTo(0,.5);g.lineTo(s.x,.5);g.stroke();
      const h=(c.x*73856093^c.y*19349663^c.z*83492791)>>>0;g.strokeStyle=D?"rgba(69,216,202,.07)":"rgba(15,143,134,.1)";g.lineWidth=7;g.beginPath();const y1=(h%200)+28,y2=((h>>8)%200)+28;g.moveTo(0,y1);g.bezierCurveTo(s.x*.35,y1+((h>>4)%60)-30,s.x*.65,y2-((h>>12)%60)+30,s.x,y2);g.stroke();return t}});
    schem=new Schematic({zIndex:1,tileSize:256}).addTo(map);
    const BLANK="data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7";
    const base=L.tileLayer(tileUrl(),{subdomains:"abcd",maxZoom:19,keepBuffer:4,updateWhenIdle:false,detectRetina:true,zIndex:2,errorTileUrl:BLANK,attribution:'© OpenStreetMap contributors © CARTO'}).addTo(map);
    tileBase=base;
    let errs=0;
    base.on("tileerror",()=>{errs++;if(errs===6){base.options.subdomains="abc";base.options.detectRetina=false;el.classList.add("osm");base.setUrl("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png")}if(errs===24)el.classList.add("no-tiles")});
    base.on("load",()=>el.classList.remove("is-loading"));
    setTimeout(()=>el.classList.remove("is-loading"),2500);
    mapLayer=L.layerGroup().addTo(map);
    if(window.ResizeObserver)new ResizeObserver(()=>map.invalidateSize()).observe(el);
    setTimeout(()=>map.invalidateSize(),250);window.addEventListener("load",()=>map.invalidateSize());
  }
  mk.forEach(m=>m._seen=false);
  N.banks.forEach(b=>upsert("b"+b.id,"bank",b.lat,b.lon,()=>markerIcon("bank","+"),`<b>${esc(b.name)}</b><br>Blood bank · ${b.open_24x7?"Open 24/7":"Limited hours"}`));
  N.hospitals.forEach(h=>upsert("h"+h.id,"hospital",h.lat,h.lon,()=>markerIcon("hospital","+"),`<b>${esc(h.name)}</b><br>${h.verified?"Verified hospital":"Verification required"}`));
  N.donors.forEach(d=>upsert("d"+d.id,d.status+d.blood_group,d.lat,d.lon,()=>markerIcon(d.status,d.blood_group.replace("+","＋").replace("-","−")),`<b>${esc(d.name)}</b> · ${G(d.blood_group)}<br>${d.status==="alerted"?"Alerted donor":"Available donor"}${d.alerts.length?`<br>${d.alerts.length} active alert${d.alerts.length>1?"s":""}`:""}<br><small>${d.last_seen?"Last seen "+new Date(d.last_seen).toLocaleTimeString([],{hour:"2-digit",minute:"2-digit"}):"Seeded demo location"}</small>`));
  mk.forEach((m,k)=>{if(!m._seen){mapLayer.removeLayer(m);mk.delete(k)}});
  const updated=$("#map-updated");if(updated)updated.textContent=`Updated ${new Date(N.updated_at).toLocaleTimeString([], {hour:"2-digit",minute:"2-digit"})} · ${N.donors.length} donors tracked`;
}
function fillBroadcast(){if(!S)return;const h=$("#broadcast-hospital"),g=$("#broadcast-group");if(h&&!h.options.length)h.innerHTML=S.hospitals.filter(x=>x.verified).map(x=>`<option value="${x.id}">${esc(x.name)}</option>`).join("");if(g&&!g.options.length)g.innerHTML=S.groups.map(x=>`<option>${x}</option>`).join("");}
function calls(){const open=S.calls.some(c=>c.status==="open");$("#calls").innerHTML=`<h2>Donor calls</h2>${S.calls.length?S.calls.map(c=>`<div class="call"><b class="${c.status}">${c.status==="open"?"Open":c.status==="covered"?"Covered":"Closed"}</b> ${c.slots_needed} × ${G(c.blood_group)} ${NAME[c.component]} at ${esc(c.bank)}<small>${c.slots_filled}/${c.slots_needed} donors confirmed. Wave ${c.wave} of ${S.waves}, ${c.alerted} alerted${c.declined?", "+c.declined+" passed":""}.</small><small>${esc(c.hospital?"For "+c.hospital:c.reason)}</small>${c.status==="open"&&c.alerted?`<button class="ghost" style="margin-top:6px;padding:5px 10px" data-call="race" data-id="${c.id}">Simulate: all alerted donors accept at once</button>`:""}</div>`).join(""):'<p class="empty">No open calls. Donors are alerted automatically when a request cannot be covered from stock.</p>'}<div class="two" style="margin-top:10px"><button data-call="scan">Scan for low stock</button><button data-call="tick" ${open?"":"disabled"}>Skip wait: next wave</button></div>`}
function detail(){const el=$("#detail");if(!sel){el.innerHTML='<h2>Pick a blood group</h2><p class="empty">Tap a bag or a floating 3D network node to see which banks hold it and who can receive it.</p>';return}const per=S.stock[comp][sel],n=total(sel),mx=Math.max(1,...Object.values(per)),from=S.receive_from[comp][sel];el.innerHTML=`<h3>${G(sel)}</h3><p class="sub">${n} unit${n===1?"":"s"} of ${NAME[comp]} across ${Object.values(per).filter(x=>x).length} of ${S.banks.length} banks</p>${S.banks.map(b=>`<div class="bank"><span>${esc(b.name)}</span><span class="meter"><i style="width:${per[b.id]/mx*100}%"></i></span><b class="${per[b.id]?"":"z"}">${per[b.id]}</b></div>`).join("")}<p class="label2" style="margin-top:16px">A ${G(sel)} patient can receive from</p><div class="chips">${from.map((g,i)=>`<button class="chip ${i===0?"exact":g==="O-"&&comp==="RBC"?"univ":""}" data-g="${g}">${G(g)}</button>`).join("")}</div><p class="note">Best match first. O− is the universal donor, so it is listed last on purpose.</p><p class="label2" style="margin-top:16px">Add ${G(sel)} ${NAME[comp]}</p><form id="add"><select id="bank">${S.banks.map(b=>`<option value="${b.id}">${esc(b.name)}</option>`).join("")}</select><div class="qty"><button type="button" data-d="-1">−</button><input id="qty" type="number" min="1" max="50" value="1"><button type="button" data-d="1">+</button></div><button class="go">Add to stock</button></form>`}
function toast(m,err){const t=$("#toast");t.textContent=m;t.className="on"+(err?" err":"");clearTimeout(t.h);t.h=setTimeout(()=>t.className="",3400)}
function ensureReady(){if(ready&&S)return true;toast("Still connecting to the RaktSetu backend…",true);return false}
function clearRequestResult(){const el=$("#rres");if(el)el.innerHTML=""}

document.addEventListener("click",async e=>{const t=e.target.closest("button");if(!t)return;
  if(t.dataset.template){const templates={trauma:{group:"O-",component:"RBC",slots:4,message:"Major trauma response: urgent red-cell support required. Eligible nearby donors, please respond immediately."},critical:{group:"AB-",component:"RBC",slots:2,message:"Critical shortage: this blood group is below safe city stock. Please respond if you are eligible."},platelets:{group:"B+",component:"PLT",slots:3,message:"Platelet emergency: a patient needs support now. Please reach the selected hospital as soon as possible."},pediatric:{group:"O-",component:"RBC",slots:2,message:"Pediatric emergency: urgent compatible blood required. Every minute matters; eligible donors please respond."}}[t.dataset.template];if(templates){$("#broadcast-group").value=templates.group;$("#broadcast-component").value=templates.component;$("#broadcast-slots").value=templates.slots;$("#broadcast-message").value=templates.message;document.querySelectorAll("[data-template]").forEach(b=>b.classList.toggle("active",b===t));$("#broadcast-message").focus()}return}
  if(t.dataset.g){if(!ensureReady())return;sel=t.dataset.g;clearRequestResult();render();jelly(sel);$("#detail")?.scrollIntoView({behavior:"smooth",block:"center"});return}
  if(t.dataset.call){if(!ensureReady())return;if(t.dataset.call==="scan"){const[ok,d]=await post("/api/calls/scan",{});if(!ok)return toast(d.error,true);await load();return toast(d.opened.length?`Called donors for ${d.opened.map(o=>o.blood_group).join(", ")}.`:"No group is critically low.")}if(t.dataset.call==="tick"){const[ok,d]=await post("/api/calls/tick",{force:true});if(!ok)return toast(d.error,true);await load();return toast(d.moved.length?"Moved to the next wave.":"Nothing to escalate.")}if(t.dataset.call==="race"){t.disabled=true;const[ok,d]=await post("/api/calls/race",{call_id:t.dataset.id});if(!ok){t.disabled=false;return toast(d.error,true)}await load();return toast(`${d.donors} donors accepted at once.`)}}
  if(t.dataset.q){const q=$("#rq");q.value=Math.min(10,Math.max(1,+q.value+ +t.dataset.q));return}
  if(t.dataset.bq){const q=$("#broadcast-slots");q.value=Math.min(20,Math.max(1,+q.value+ +t.dataset.bq));return}
  if(t.id==="scan-critical"){if(!ensureReady())return;t.disabled=true;const[ok,d]=await post("/api/calls/scan",{});t.disabled=false;if(!ok)return toast(d.error||"Could not scan stock",true);await load();return toast(d.opened.length?`Emergency calls opened for ${d.opened.map(o=>o.blood_group).join(", ")}.`:`No group is below the critical threshold.`)}
  if(t.dataset.act){if(!ensureReady())return;const[ok,d]=await post("/api/request/"+t.dataset.act,{request_id:t.dataset.rid});if(!ok)return toast(d.error,true);$("#rres").innerHTML="";await load();return toast(t.dataset.act==="issue"?"Marked as issued.":"Reservation cancelled, units are back in stock.")}
  if(t.id==="race"){if(!ensureReady())return;const g=$("#rg")?.value;if(!g||!S.groups.includes(g))return toast("Choose a blood group after the backend finishes loading.",true);t.disabled=true;t.textContent="Running live race…";const[ok,d]=await post("/api/race",{group:g,component:comp});t.disabled=false;t.textContent="Run race test: 6 requests at the same moment";if(!ok)return toast(d.error||"Race test failed",true);await load();$("#rres").innerHTML=`<div class="res"><h3>Race test: ${d.requests} requests at once</h3><p class="empty">${d.supply} compatible unit${d.supply===1?"":"s"} in the city. <b>${d.served} served</b>, ${d.turned_away} turned away, ${d.rerouted} rerouted. <b>${d.oversold} oversold.</b> Stock restored afterwards.</p></div>`;return}
  if(t.id==="c-RBC"||t.id==="c-PLT"){if(!ensureReady())return;comp=t.id.slice(2);clearRequestResult();render();return}
  if(t.classList.contains("row")){if(!ensureReady())return;const r=S.expiring[t.dataset.i];comp=r.component;sel=r.blood_group;clearRequestResult();render();return}
  if(t.dataset.d){const q=$("#qty");q.value=Math.min(50,Math.max(1,+q.value+ +t.dataset.d))}
});
document.addEventListener("submit",async e=>{if(e.target.id==="broadcast")return;e.preventDefault();if(!ensureReady())return;if(e.target.id==="rf")return reqSubmit();const res=await fetch("/api/add",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({bank_id:$("#bank").value,group:sel,component:comp,qty:$("#qty").value})});const d=await res.json();if(!res.ok)return toast(d.error,true);const q=$("#qty").value;await load();toast(`Added ${q} × ${sel} ${NAME[comp]} to ${d.bank}. Expires ${new Date(d.expires).toLocaleDateString("en-IN",{day:"numeric",month:"short"})}.`)});
document.addEventListener("submit",async e=>{if(e.target.id!=="broadcast")return;e.preventDefault();if(!ensureReady())return;const button=e.target.querySelector("button[type=submit]"),out=$("#broadcast-result");button.disabled=true;button.textContent="Broadcasting live alert…";const[ok,d]=await post("/api/broadcast",{hospital_id:$("#broadcast-hospital").value,group:$("#broadcast-group").value,component:$("#broadcast-component").value,slots:$("#broadcast-slots").value,message:$("#broadcast-message").value});button.disabled=false;button.innerHTML="Broadcast critical shortage <span>↗</span>";if(!ok){out.className="broadcast-result error";out.textContent=d.error||"Broadcast failed.";return}out.className="broadcast-result success";out.innerHTML=`<b>Broadcast live.</b> ${d.alerted} donor${d.alerted===1?"":"s"} alerted in wave 1${d.existing?" · existing call reused":""}.`;$("#broadcast-message").value="";await load();toast(`Emergency broadcast sent to ${d.alerted} donor${d.alerted===1?"":"s"}.`)});
document.addEventListener("change",e=>{if(e.target.id==="rg"){clearRequestResult();sel=e.target.value;render()}});
async function post(u,b){try{const r=await fetch(u,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(b)});let d={};try{d=await r.json()}catch{}return[r.ok,d]}catch(err){return[false,{error:"Backend connection lost."}]}}
function fillReq(){if(!S)return;const h=$("#rh"),g=$("#rg");if(!h.options.length)h.innerHTML=S.hospitals.map(x=>`<option value="${x.id}">${esc(x.name)}${x.verified?"":" (not verified)"}</option>`).join("");if(!g.options.length)g.innerHTML=S.groups.map(x=>`<option>${x}</option>`).join("");if(sel)g.value=sel;$("#rc").textContent=NAME[comp];$("#race").disabled=!ready}
async function reqSubmit(){const g=$("#rg")?.value;if(!g)return toast("Choose a blood group first.",true);const[ok,d]=await post("/api/request",{hospital_id:$("#rh").value,group:g,component:comp,qty:$("#rq").value});if(!ok)return toast(d.error,true);await load();if(d.status!=="reserved"){const dc=d.donor_call,msg=dc?(dc.existing?"A donor call is already open.":dc.alerted+" nearby eligible donor"+(dc.alerted===1?"":"s")+" alerted."):"";$("#rres").innerHTML=`<div class="res"><h3>Nothing available</h3><p class="empty">No bank can supply this right now. ${msg?"<b>"+msg+"</b>":""}</p></div>`;return}const b=d.bank,alt=d.ranking.slice(1,3);$("#rres").innerHTML=`<div class="res"><h3>Reserved: ${b.units.replace(/([ABO]+)([+-])/g,(m,x,y)=>x+(y==="-"?"−":"+"))} ${NAME[comp]}</h3><p class="empty"><b style="color:var(--ink)">${esc(b.bank)}</b>, ${b.km} km away. Held until ${new Date(d.hold_until).toLocaleTimeString("en-IN",{hour:"2-digit",minute:"2-digit"})}.</p>${d.fallthroughs.length?`<p class="note">Lost the race at ${esc(d.fallthroughs.join(", "))} and rerouted automatically.</p>`:""}<p class="label2">Why this bank</p><ul>${b.why.map(w=>`<li>${esc(w)}</li>`).join("")}</ul>${alt.length?`<p class="note">Also considered: ${alt.map(a=>esc(a.bank)+" ("+a.score+")").join(", ")}. This bank scored ${b.score}.</p>`:""}<div class="two"><button data-act="issue" data-rid="${d.request_id}">Mark as issued</button><button data-act="cancel" data-rid="${d.request_id}">Cancel and release</button></div></div>`}
function enable3D(){const hero=$(".hero"),art=$(".hero-art");if(!hero||!art)return;hero.addEventListener("pointermove",e=>{const r=hero.getBoundingClientRect(),x=(e.clientX-r.left)/r.width-.5,y=(e.clientY-r.top)/r.height-.5;art.style.setProperty("--ry",`${x*5}deg`);art.style.setProperty("--rx",`${-y*4}deg`);});hero.addEventListener("pointerleave",()=>{art.style.setProperty("--ry","0deg");art.style.setProperty("--rx","0deg")})}
enable3D();load();setInterval(()=>{if(document.visibilityState==="visible")load()},15000);

document.addEventListener("pointerdown",e=>{const b=e.target.closest(".bag,.node3d");if(b){b.classList.remove("jelly");void b.offsetWidth;b.classList.add("tap")}});
document.addEventListener("pointerup",()=>document.querySelectorAll(".tap").forEach(b=>b.classList.remove("tap")));
function jelly(g){const b=document.querySelector(`.bag[data-g="${g}"]`);if(b){b.classList.remove("jelly");void b.offsetWidth;b.classList.add("jelly")}}

applyTheme(curTheme(),false);
