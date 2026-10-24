"""Build Prezervia-standalone.html — ONE file, no server, works on any device.

It embeds all animal profiles and reimplements the detector (match profile,
check alarm, severity) in JavaScript, so the page needs no Python backend.
Pets are stored in the browser (localStorage).
"""
from __future__ import annotations
import csv, json
from pathlib import Path

HERE = Path(__file__).parent
CSV = HERE / "prezervia" / "animal_vitals.csv"
LOGO = HERE / "pawwatch_logo.png"
OUT = HERE / "Prezervia-standalone.html"


def profiles():
    out = []
    with open(CSV) as f:
        for r in csv.DictReader(f):
            out.append({
                "species": r["species"], "breed": r["breed_or_type"],
                "age": r["age_range_yrs"],
                "hr": [float(r["hr_min"]), float(r["hr_max"])],
                "resp": [float(r["resp_min"]), float(r["resp_max"])],
                "temp": [float(r["temp_min_c"]), float(r["temp_max_c"])],
                "movement": [float(r["movement_score_min"]), float(r["movement_score_max"])],
            })
    return out


def logo_data_uri():
    if not LOGO.exists():
        return ""
    import base64
    b = base64.b64encode(LOGO.read_bytes()).decode()
    return f"data:image/png;base64,{b}"


HTML = r"""<!DOCTYPE html><html lang="en"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Prezervia</title>
<link rel="icon" href="__LOGO__">
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
<style>
:root{--card:rgba(255,255,255,.045);--card-br:rgba(255,255,255,.09);--ink:#F3EEE9;--muted:#A79C92;--taupe:#B8A796;--good:#7FC9A0;--red:#E0533B;--strava:#FC4C02;--glow:0 1px 0 rgba(255,255,255,.04) inset,0 18px 40px rgba(0,0,0,.45);}
@media (prefers-reduced-motion:reduce){*{animation:none!important;transition:none!important}}
*{box-sizing:border-box}
body{margin:0;min-height:100vh;color:var(--ink);background:radial-gradient(130% 90% at 50% 0%,#241f1c,#141210 45%,#0E0C0B);font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;line-height:1.45}
.app{max-width:460px;margin:0 auto;min-height:100vh;display:flex;flex-direction:column}
.bar{display:flex;align-items:center;gap:12px;padding:16px 18px;position:sticky;top:0;background:rgba(16,12,11,.82);backdrop-filter:blur(10px);z-index:10;border-bottom:1px solid var(--card-br)}
.bar .logo{width:34px;height:34px;border-radius:9px;object-fit:cover;background:#3a312b}
.bar h1{font-size:17px;margin:0;font-weight:650;flex:1}
.bar .back{background:none;border:none;color:var(--taupe);font-size:15px;cursor:pointer;padding:4px 6px;width:auto;margin:0}
.offline{font-size:11px;color:var(--good)}
.screen{display:none;flex-direction:column;gap:16px;padding:18px 16px 40px}
.screen.active{display:flex}
.card{background:var(--card);border:1px solid var(--card-br);border-radius:22px;padding:18px;box-shadow:var(--glow)}
.card h2{font-size:12px;margin:0 0 14px;color:var(--taupe);font-weight:600;letter-spacing:.4px;text-transform:uppercase}
label{display:block;font-size:12px;color:var(--muted);margin:10px 0 4px}
input,select{width:100%;padding:12px 13px;border:1px solid var(--card-br);border-radius:13px;font-size:14px;background:rgba(0,0,0,.25);color:var(--ink)}
.row{display:grid;grid-template-columns:1fr 1fr;gap:10px}
button{cursor:pointer;border:none;border-radius:999px;padding:13px 18px;font-size:14px;font-weight:650;width:100%;margin-top:14px}
.primary{background:var(--taupe);color:#211b16}.primary:hover{background:#c9b9a8}
.ghost{background:rgba(255,255,255,.06);color:var(--ink);border:1px solid var(--card-br)}.ghost:hover{background:rgba(255,255,255,.1)}
.hero{text-align:center;padding:26px 10px 6px}.hero .big{font-size:26px;font-weight:700;margin:14px 0 6px}.hero p{color:var(--muted);font-size:14px;margin:0 20px}
.muted{color:var(--muted);font-size:13px}
.petrow{display:flex;align-items:center;gap:14px;padding:14px;border-radius:16px;background:rgba(0,0,0,.22);border:1px solid var(--card-br);cursor:pointer}
.petrow:hover{background:rgba(255,255,255,.04);border-color:var(--taupe)}.petrow+.petrow{margin-top:10px}
.pfp{width:48px;height:48px;border-radius:14px;background:linear-gradient(135deg,#5a4c42,#3a312b);display:flex;align-items:center;justify-content:center;font-size:22px;flex-shrink:0}
.petrow .nm{font-weight:650;font-size:15px}.petrow .sb{font-size:12px;color:var(--muted)}
.statusdot{margin-left:auto;width:12px;height:12px;border-radius:50%}
.s-ok{background:var(--good)}.s-alarm{background:var(--red);box-shadow:0 0 8px var(--red)}.s-unknown{background:#6b625b}
.stats{display:grid;grid-template-columns:1fr 1fr;gap:12px}
.stat{background:rgba(0,0,0,.22);border:1px solid var(--card-br);border-radius:18px;padding:14px}
.stat .k{font-size:11px;color:var(--muted);text-transform:uppercase;letter-spacing:.4px}.stat .v{font-size:30px;font-weight:700;margin-top:4px;line-height:1}.stat .u{font-size:13px;color:var(--muted);font-weight:500}
.reasons{font-size:13px;margin:10px 0 0;padding-left:18px}.reasons li{margin:4px 0}
#map{height:190px;border-radius:16px;overflow:hidden;border:1px solid var(--card-br)}
.leaflet-tile{filter:brightness(.6) invert(1) contrast(.9) hue-rotate(180deg) saturate(.4)}
.chartwrap{position:relative;margin-top:12px}canvas{width:100%;display:block;border-radius:14px;background:rgba(0,0,0,.22);border:1px solid var(--card-br)}
.scrub{position:absolute;top:0;bottom:0;width:2px;background:var(--taupe);opacity:.7;pointer-events:none}
.hud{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-top:12px}.hud div{background:rgba(0,0,0,.22);border:1px solid var(--card-br);border-radius:14px;padding:10px;text-align:center}.hud .k{font-size:11px;color:var(--muted)}.hud .v{font-size:16px;font-weight:700}
.warn{background:rgba(224,83,59,.12);border:1px solid rgba(224,83,59,.4);color:#f0a393;padding:11px 13px;border-radius:13px;font-weight:600;font-size:13px;margin-top:10px}
.ok{background:rgba(127,201,160,.1);border:1px solid rgba(127,201,160,.3);color:var(--good);padding:11px 13px;border-radius:13px;font-weight:600;font-size:13px;margin-top:10px}
.pulse{width:14px;height:14px;border-radius:50%;background:var(--strava);animation:pulse 1.8s infinite}
@keyframes pulse{0%{box-shadow:0 0 0 0 rgba(252,76,2,.55)}70%{box-shadow:0 0 0 15px rgba(252,76,2,0)}100%{box-shadow:0 0 0 0 rgba(252,76,2,0)}}
.drop{border:1.5px dashed var(--card-br);border-radius:14px;padding:14px;text-align:center;cursor:pointer;color:var(--muted);font-size:13px;background:rgba(0,0,0,.18)}.drop:hover{border-color:var(--taupe);color:var(--ink)}.drop b{color:var(--ink)}
</style></head><body><div class="app">
<div class="bar">
  <button class="back" id="backBtn" style="display:none" onclick="goPets()">‹ Back</button>
  <img class="logo" id="logo" src="__LOGO__" alt="">
  <h1 id="barTitle">Prezervia</h1><span class="offline">● Works offline</span>
</div>

<section class="screen active" id="screen-signup">
  <div class="hero"><div class="big">Welcome to Prezervia</div><p>Keep watch over the animals you love. Create an account to start.</p></div>
  <div class="card"><h2>Create your account</h2>
    <label>Your name</label><input id="acc_name" placeholder="e.g. Alex">
    <label>Email</label><input id="acc_email" type="email" placeholder="you@email.com">
    <label>Password</label><input id="acc_pw" type="password" placeholder="At least 8 characters">
    <div class="muted" id="pwHint" style="margin-top:6px"></div>
    <button class="primary" onclick="signUp()">Create account</button>
    <div class="warn" id="signupErr" style="display:none"></div>
    <p class="muted" style="text-align:center;margin-top:12px">Already have one? <a href="#" onclick="goPets();return false" style="color:var(--taupe)">Skip to my pets</a></p>
  </div>
</section>

<section class="screen" id="screen-pets">
  <div class="card"><h2>My pets</h2><div id="petList"></div>
    <button class="ghost" onclick="loadSamples()">Load sample pets</button></div>
  <div class="card"><h2>Add a pet</h2>
    <div style="display:flex;justify-content:center"><div class="pfp" id="newPfp" style="width:84px;height:84px;font-size:34px">🐾</div></div>
    <label>Photo</label><div class="drop" id="drop"><b>Add a photo</b><br>tap to choose</div>
    <input type="file" id="photo" accept="image/*" style="display:none" onchange="loadPhoto(event)">
    <div class="row"><div><label>Name</label><input id="p_name" placeholder="Rex"></div><div><label>Species</label><input id="p_species" placeholder="Dog"></div></div>
    <div class="row"><div><label>Breed</label><input id="p_breed" placeholder="Chihuahua"></div><div><label>Age (years)</label><input id="p_age" placeholder="3"></div></div>
    <button class="primary" onclick="addPet()">Add pet</button><div class="muted" id="addMsg" style="margin-top:8px"></div>
  </div>
</section>

<section class="screen" id="screen-pet">
  <div class="card"><h2 id="petHdr">Wellness</h2>
    <div class="stats">
      <div class="stat"><div class="k">Heart rate</div><div class="v" id="s_hr">—<span class="u"> bpm</span></div></div>
      <div class="stat"><div class="k">Temperature</div><div class="v" id="s_temp">—<span class="u"> °C</span></div></div>
      <div class="stat"><div class="k">Breathing</div><div class="v" id="s_resp">—<span class="u"> /min</span></div></div>
      <div class="stat"><div class="k">Movement</div><div class="v" id="s_move">—<span class="u"> /100</span></div></div>
    </div><div class="muted" id="s_status" style="margin-top:12px"></div><ul class="reasons" id="reasons"></ul>
  </div>
  <div class="card"><h2>Collar</h2>
    <div class="row"><div><label>Connection</label><select id="d_how"><option>bluetooth</option><option>wifi</option></select></div><div><label>Battery (%)</label><input id="d_batt" value="80"></div></div>
    <button class="ghost" id="liveBtn" onclick="toggleLive()">▶ Start live feed</button><div id="deviceOut" style="margin-top:8px"></div>
  </div>
  <div class="card"><h2>Track & timeline</h2><div id="map"></div>
    <div class="chartwrap"><canvas id="chart" height="150"></canvas><div class="scrub" id="scrub" style="left:0"></div></div>
    <div class="hud"><div><div class="k">Pace</div><div class="v" id="h_pace">—</div></div><div><div class="k">Elevation</div><div class="v" id="h_elev">—</div></div><div><div class="k">Heart rate</div><div class="v" id="h_hr">—</div></div></div>
    <p class="muted" style="margin-top:8px;text-align:center">Drag across the graph — the marker retraces the walk.</p>
  </div>
  <div class="card"><h2>Vet connect</h2><p class="muted">A printable summary of recorded data for your vet. Data only — no diagnosis.</p>
    <button class="primary" onclick="vetPrint()">Open vet report</button></div>
</section>
</div>

<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script>
const PROFILES=__PROFILES__;
let CURRENT=null;
/* ---- storage ---- */
const DB={get:()=>JSON.parse(localStorage.getItem('prez_pets')||'[]'),
  set:v=>localStorage.setItem('prez_pets',JSON.stringify(v))};
/* ---- detector (in JS, no server) ---- */
function ageIn(band,age){const[a,b]=band.split('-').map(Number);return age>=a&&age<=b;}
function matchProfile(species,breed,age){
  const sp=PROFILES.filter(p=>p.species.toLowerCase()===String(species).toLowerCase());
  let pool=sp.filter(p=>p.breed.toLowerCase()===String(breed).toLowerCase());
  if(!pool.length)pool=sp;
  if(!pool.length)pool=PROFILES;
  let hit=pool.find(p=>ageIn(p.age,+age));
  if(!hit){hit=pool.reduce((best,p)=>{const m=b=>{const[x,y]=b.split('-').map(Number);return(x+y)/2;};return Math.abs(m(p.age)-age)<Math.abs(m(best.age)-age)?p:best;},pool[0]);}
  return hit;
}
function checkAlarm(prof,r){
  const reasons=[],abnormal=[];
  const defs=[['hr','Heart rate','bpm'],['resp','Breathing','breaths/min'],['temp','Temperature','°C'],['movement','Movement','/100']];
  let alarm=false;
  for(const[k,label,unit]of defs){
    if(r[k]==null)continue;
    const[lo,hi]=prof[k];const v=r[k];
    if(v>hi){alarm=true;abnormal.push(k+'=HIGH');reasons.push(`${label} ${v} ${unit} is above normal. Normal is ${lo}-${hi} ${unit}.`);}
    else if(v<lo){alarm=true;abnormal.push(k+'=LOW');reasons.push(`${label} ${v} ${unit} is below normal. Normal is ${lo}-${hi} ${unit}.`);}
  }
  return {alarm,reasons,abnormal};
}
/* ---- screens ---- */
function show(id){document.querySelectorAll('.screen').forEach(s=>s.classList.remove('active'));document.getElementById(id).classList.add('active');document.getElementById('backBtn').style.display=(id==='screen-pet')?'block':'none';window.scrollTo(0,0);}
function goPets(){stopLive();document.getElementById('barTitle').textContent='Prezervia';loadPets();show('screen-pets');}
function pwStrong(p){return p.length>=8&&/[A-Za-z]/.test(p)&&/[0-9]/.test(p)&&/[^A-Za-z0-9]/.test(p);}
function validEmail(e){return /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(e);}
(function(){const pw=document.getElementById('acc_pw');pw.addEventListener('input',()=>{const v=pw.value,h=document.getElementById('pwHint');if(!v){h.textContent='';return;}if(pwStrong(v)){h.textContent='Strong password ✓';h.style.color='var(--good)';}else{h.textContent='Needs 8+ chars, a letter, a number, and a symbol.';h.style.color='var(--muted)';}});})();
function signUp(){const n=acc_name.value.trim(),e=acc_email.value.trim(),p=acc_pw.value,err=signupErr,pr=[];if(!n)pr.push('Enter your name.');if(!validEmail(e))pr.push('Enter a valid email.');if(!pwStrong(p))pr.push('Password needs 8+ chars, a letter, a number, and a symbol.');if(pr.length){err.style.display='block';err.innerHTML=pr.join('<br>');return;}err.style.display='none';goPets();}
/* ---- color ---- */
function colorFor(v,lo,hi){if(v>hi)return mix("#FF7A00","#D32F2F",Math.min(1,(v-hi)/(hi*0.4+1)));if(v<lo)return mix("#F0F8FF","#004AAD",Math.min(1,(lo-v)/(lo*0.6+1)));return "#7FC9A0";}
function mix(a,b,t){const pa=hx(a),pb=hx(b);return `rgb(${pa.map((v,i)=>Math.round(v+(pb[i]-v)*t)).join(',')})`;}
function hx(h){return[1,3,5].map(i=>parseInt(h.slice(i,i+2),16));}
function emojiFor(sp){const m={Dog:'🐕',Cat:'🐈',Rabbit:'🐇',Horse:'🐎',Goat:'🐐',Sheep:'🐑',Cow:'🐄',Cattle:'🐄',Pig:'🐖',Chicken:'🐔',Ferret:'🦫',Hamster:'🐹',GuineaPig:'🐹',Llama:'🦙',Deer:'🦌',Bear:'🐻',Lion:'🦁',Tiger:'🐅',Elephant:'🐘',Giraffe:'🦒',Zebra:'🦓'};return m[sp]||'🐾';}
/* ---- pets ---- */
function loadPets(){const list=document.getElementById('petList');const pets=DB.get();if(!pets.length){list.innerHTML='<p class="muted">No pets yet. Add one below, or load samples.</p>';return;}list.innerHTML='';pets.forEach(p=>{const prof=matchProfile(p.species,p.breed,p.age);const last=p.readings&&p.readings[p.readings.length-1];const res=last?checkAlarm(prof,last):null;const cls=!res?'s-unknown':(res.alarm?'s-alarm':'s-ok');const el=document.createElement('div');el.className='petrow';el.onclick=()=>openPet(p);el.innerHTML=`<div class="pfp">${emojiFor(p.species)}</div><div><div class="nm">${p.name}</div><div class="sb">${p.species} · ${p.breed}</div></div><div class="statusdot ${cls}"></div>`;list.appendChild(el);});}
function loadPhoto(e){const f=e.target.files[0];if(!f)return;const u=URL.createObjectURL(f);const p=document.getElementById('newPfp');p.style.backgroundSize='cover';p.style.backgroundImage=`url(${u})`;p.textContent='';document.getElementById('drop').innerHTML='<b>Photo added</b>';}
(function(){const d=document.getElementById('drop'),i=document.getElementById('photo');d.onclick=()=>i.click();})();
function addPet(){const n=p_name.value.trim(),s=p_species.value.trim(),b=p_breed.value.trim(),a=p_age.value.trim();const msg=addMsg;if(!n||!s||!b||!a){msg.textContent='Fill name, species, breed and age.';return;}const prof=matchProfile(s,b,a);const pets=DB.get();pets.push({name:n,species:s,breed:b,age:+a,readings:[]});DB.set(pets);msg.textContent=`Added ${n}. Matched ${prof.species}/${prof.breed}.`;p_name.value=p_species.value=p_breed.value=p_age.value='';loadPets();}
function loadSamples(){const names=['Luna','Milo','Clover','Pepper','Juniper','Biscuit','Willow','Gus','Maple','Rico','Olive','Dash'].sort(()=>Math.random()-.5);const sps=[...new Set(PROFILES.map(p=>p.species))].sort(()=>Math.random()-.5).slice(0,5);const pets=DB.get();sps.forEach((sp,i)=>{const b=PROFILES.filter(p=>p.species===sp);const br=b[Math.floor(Math.random()*b.length)];pets.push({name:names[i],species:sp,breed:br.breed,age:[1,2,3,4,5][Math.floor(Math.random()*5)],readings:[]});});DB.set(pets);loadPets();}
/* ---- pet detail ---- */
function openPet(p){CURRENT=p;document.getElementById('barTitle').textContent=p.name;document.getElementById('petHdr').textContent=p.name+' — wellness';s_status.textContent='Start the live feed to see readings.';['s_hr','s_temp','s_resp','s_move'].forEach(id=>document.getElementById(id).innerHTML='—');reasons.innerHTML='';show('screen-pet');setTimeout(()=>{initMap();chartData=buildSeries();drawChart();syncTo(chartData.length-1);const c=document.getElementById('chart');c.onmousemove=scrub;c.ontouchmove=scrub;},60);}
function fillSummary(hr,tp,rs,mv,alarm){s_hr.innerHTML=`${hr}<span class="u"> bpm</span>`;s_hr.style.color=colorFor(hr,100,140);s_temp.innerHTML=`${tp}<span class="u"> °C</span>`;s_temp.style.color=colorFor(tp,38.3,39.2);s_resp.innerHTML=`${rs}<span class="u"> /min</span>`;s_resp.style.color=colorFor(rs,18,34);s_move.innerHTML=`${mv}<span class="u"> /100</span>`;s_move.style.color=colorFor(mv,20,60);s_status.textContent=alarm?'Abnormal — check your vet.':'Looks normal.';s_status.style.color=alarm?'var(--red)':'var(--good)';}
/* ---- live feed (local detector) ---- */
let liveTimer=null;
function stopLive(){if(liveTimer){clearInterval(liveTimer);liveTimer=null;const b=document.getElementById('liveBtn');if(b)b.textContent='▶ Start live feed';}}
function toggleLive(){const b=document.getElementById('liveBtn');if(liveTimer){stopLive();return;}b.textContent='⏸ Stop live feed';liveTick();liveTimer=setInterval(liveTick,3000);}
function liveTick(){if(!CURRENT)return;const prof=matchProfile(CURRENT.species,CURRENT.breed,CURRENT.age);const span=r=>+(r[0]+Math.random()*(r[1]-r[0])).toFixed(1);const rd={hr:span(prof.hr),resp:span(prof.resp),temp:span(prof.temp),movement:span(prof.movement)};const res=checkAlarm(prof,rd);CURRENT.readings=(CURRENT.readings||[]).concat(rd).slice(-50);const pets=DB.get();const idx=pets.findIndex(x=>x.name===CURRENT.name);if(idx>=0){pets[idx]=CURRENT;DB.set(pets);}fillSummary(Math.round(rd.hr),rd.temp.toFixed(1),Math.round(rd.resp),Math.round(rd.movement),res.alarm);reasons.innerHTML='';res.reasons.forEach(t=>{const li=document.createElement('li');li.textContent=t;reasons.appendChild(li);});deviceOut.innerHTML=res.alarm?`<div class="warn">Live over ${d_how.value}. Abnormal.</div>`:`<div class="ok">Live over ${d_how.value}. Streaming…</div>`;}
/* ---- vet report (printable, no diagnosis) ---- */
function vetPrint(){if(!CURRENT)return;const prof=matchProfile(CURRENT.species,CURRENT.breed,CURRENT.age);const last=(CURRENT.readings||[]).slice(-1)[0];const w=window.open('','_blank');const rows=last?['hr','resp','temp','movement'].map(k=>`<tr><td>${k}</td><td>${last[k]}</td></tr>`).join(''):'<tr><td colspan=2>No readings yet</td></tr>';
w.document.write(`<html><head><title>Prezervia — ${CURRENT.name}</title><style>body{font-family:-apple-system,sans-serif;color:#2B2320;padding:40px;max-width:700px;margin:auto}h1{margin:0}hr{border:0;border-top:1px solid #ECE4DB}table{width:100%;border-collapse:collapse;margin-top:12px}td,th{border:1px solid #ECE4DB;padding:8px;text-align:left}.foot{color:#8A7E76;font-size:12px;margin-top:30px}</style></head><body>
<h1>Prezervia</h1><p style="color:#8A7E76">Animal monitoring report · ${new Date().toLocaleString()}</p><hr>
<h3>Patient</h3><p>Name: ${CURRENT.name}<br>Species / breed: ${CURRENT.species} / ${CURRENT.breed}<br>Age: ${CURRENT.age} years</p>
<h3>Reference ranges (source: Merck/VCA)</h3><p>Heart rate ${prof.hr[0]}-${prof.hr[1]} bpm · Breathing ${prof.resp[0]}-${prof.resp[1]} /min · Temp ${prof.temp[0]}-${prof.temp[1]} °C · Movement ${prof.movement[0]}-${prof.movement[1]} /100</p>
<h3>Most recent reading</h3><table><tr><th>Signal</th><th>Value</th></tr>${rows}</table>
<p class="foot">This report shows recorded data only. Prezervia does not diagnose and makes no assessment of whether these values are healthy. Interpretation is for the attending veterinarian.</p>
<script>setTimeout(()=>window.print(),400)<\/script></body></html>`);w.document.close();}
/* ---- map + chart ---- */
let chartData=[],routePts=[],mapObj=null,doneLine=null,nowMarker=null;
function buildRoute(){const base=[42.3732,-72.5199];const p=[base.slice()];let lat=base[0],lon=base[1],a=Math.random()*6.28;for(let i=1;i<40;i++){a+=(Math.random()-.5)*.9;lat+=Math.cos(a)*.0006*(.6+Math.random()*.8);lon+=Math.sin(a)*.0006*(.6+Math.random()*.8);p.push([lat,lon]);}return p;}
function buildSeries(){const d=[];for(let i=0;i<40;i++)d.push({pace:4+Math.sin(i/5)*1.2,elev:20+Math.sin(i/8)*14+i*.4,hr:90+Math.sin(i/4)*25+(i>30?(i-30)*6:0)});return d;}
function drawChart(hi){const c=document.getElementById('chart');const w=c.clientWidth;c.width=w;const h=c.height;const ctx=c.getContext('2d');ctx.clearRect(0,0,w,h);[['pace',2,7,'#8A7E76',0],['elev',10,60,'#b07a46',1],['hr',60,170,'#FC4C02',0]].forEach(([k,lo,hhi,col,fill])=>{if(fill){ctx.beginPath();chartData.forEach((d,i)=>{const x=i/(chartData.length-1)*w,y=h-((d[k]-lo)/(hhi-lo))*h;i?ctx.lineTo(x,y):ctx.moveTo(x,y);});ctx.lineTo(w,h);ctx.lineTo(0,h);ctx.closePath();ctx.fillStyle='rgba(176,122,70,.10)';ctx.fill();}ctx.beginPath();ctx.lineWidth=k==='hr'?2.4:1.6;chartData.forEach((d,i)=>{const x=i/(chartData.length-1)*w,y=h-((d[k]-lo)/(hhi-lo))*h;ctx.strokeStyle=k==='hr'?colorFor(d.hr,80,150):col;i?ctx.lineTo(x,y):ctx.moveTo(x,y);});ctx.stroke();});if(hi!=null&&chartData[hi]){const x=hi/(chartData.length-1)*w,d=chartData[hi],y=h-((d.hr-60)/110)*h;ctx.beginPath();ctx.arc(x,y,4,0,7);ctx.fillStyle=colorFor(d.hr,80,150);ctx.fill();}}
function syncTo(i){i=Math.max(0,Math.min(chartData.length-1,i));const d=chartData[i];if(!d)return;h_pace.textContent=d.pace.toFixed(1)+"′/km";h_elev.textContent=Math.round(d.elev)+" m";h_hr.textContent=Math.round(d.hr)+" bpm";h_hr.style.color=colorFor(d.hr,80,150);const c=document.getElementById('chart');document.getElementById('scrub').style.left=(i/(chartData.length-1)*c.clientWidth)+'px';drawChart(i);if(doneLine)doneLine.setLatLngs(routePts.slice(0,i+1));if(nowMarker&&routePts[i])nowMarker.setLatLng(routePts[i]);}
function scrub(e){const c=document.getElementById('chart');const r=c.getBoundingClientRect();const x=Math.max(0,Math.min(r.width,(e.touches?e.touches[0].clientX:e.clientX)-r.left));syncTo(Math.round(x/r.width*(chartData.length-1)));}
function initMap(){if(mapObj){mapObj.remove();mapObj=null;}routePts=buildRoute();mapObj=L.map('map',{zoomControl:false,attributionControl:false}).setView(routePts[0],14);L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png').addTo(mapObj);L.polyline(routePts,{color:'#FC4C02',weight:4,opacity:.25}).addTo(mapObj);doneLine=L.polyline([routePts[0]],{color:'#FC4C02',weight:5}).addTo(mapObj);L.circleMarker(routePts[0],{color:'#7FC9A0',radius:5,fillOpacity:1}).addTo(mapObj);nowMarker=L.marker(routePts[0],{icon:L.divIcon({className:'',html:'<div class="pulse"></div>',iconSize:[14,14]})}).addTo(mapObj);mapObj.fitBounds(routePts,{padding:[18,18]});}
window.addEventListener('resize',()=>{if(chartData.length)drawChart();});
</script></body></html>"""


def main():
    html = HTML.replace("__PROFILES__", json.dumps(profiles()))
    html = html.replace("__LOGO__", logo_data_uri())
    OUT.write_text(html)
    print(f"wrote {OUT} ({len(html)//1024} KB)")


if __name__ == "__main__":
    main()
