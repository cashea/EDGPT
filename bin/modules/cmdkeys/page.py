"""Commands page: button grid with live Status.json indicators. Served at /cmdkeys/page."""

PAGE = """<!DOCTYPE html><html><head><meta charset="UTF-8"><title>EDGPT Commands</title>
<style>
body{background:#111;color:#eee;font-family:Consolas,monospace;margin:24px}
h1{color:#ff9500;margin:0 0 8px} .muted{color:#888} a{color:#ff9500}
.bar{display:flex;gap:12px;align-items:center;margin:12px 0;flex-wrap:wrap}
button{background:#222;color:#eee;border:1px solid #444;border-radius:6px;padding:10px 14px;font:inherit;cursor:pointer}
button:hover{border-color:#ff9500} button:disabled{opacity:.4;cursor:default}
button.danger{background:#5a1a1a;border-color:#a33} button.on{background:#2d4a1f;border-color:#6c3}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:10px}
.card{background:#191919;border:1px solid #333;border-radius:8px;padding:10px}
.card .name{font-weight:bold} .card .desc{color:#999;font-size:.9em;margin:4px 0 8px;min-height:2.4em}
.card .warn{color:#e6a23c;font-size:.85em}
.flags{display:flex;gap:6px;flex-wrap:wrap} .flag{padding:3px 8px;border-radius:12px;background:#222;border:1px solid #333;font-size:.85em}
.flag.on{background:#2d4a1f;border-color:#6c3}
#log{background:#191919;padding:12px;border-radius:8px;white-space:pre-wrap;min-height:4em;margin-top:12px}
</style></head><body>
<h1>Commands</h1>
<div class="muted">Local only. Keys are sent only while Elite Dangerous is the foreground window. <a href="/">state</a> · <a href="/cmdkeys">json</a></div>
<div class="bar">
 <button id="arm" onclick="toggleArm()">Injection: OFF</button>
 <button class="danger" onclick="post('/cmdkeys/cancel',{})">CANCEL</button>
 <label><input type="checkbox" id="dry" checked> dry run</label>
 <span id="binds" class="muted"></span>
</div>
<div class="flags" id="flags"></div>
<h3>Macros <span class="muted" id="file"></span></h3>
<div class="grid" id="grid"></div>
<div id="log">Ready.</div>
<script>
const WATCH=["Docked","Landed","LandingGearDown","HardpointsDeployed","LightsOn","CargoScoopDeployed","Supercruise","FsdCharging","FsdMassLocked","ShieldsUp","InSrv","OnFoot","HudInAnalysisMode","NightVision","SilentRunning"];
let armed=false;
function log(x){document.getElementById('log').textContent=(typeof x==='string')?x:JSON.stringify(x,null,2)}
async function post(path,body){try{const r=await fetch(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});const d=await r.json();log(d);await refresh();return d}catch(e){log('ERROR: '+e)}}
async function toggleArm(){await post('/cmdkeys/enable',{enabled:!armed})}
async function run(name){await post('/cmdkeys/run',{macro:name,dry_run:document.getElementById('dry').checked})}
async function refresh(){try{
 const d=await (await fetch('/cmdkeys?t='+Date.now())).json();
 armed=d.injection_enabled;const a=document.getElementById('arm');a.textContent='Injection: '+(armed?'ON':'OFF');a.className=armed?'on':'';
 document.getElementById('binds').textContent=d.binds.file?('binds: '+d.binds.preset+' ('+d.binds.actions+' actions)'):('binds: '+(d.binds.error||'none'));
 document.getElementById('file').textContent=d.macros_file;
 const on=new Set(d.flags);document.getElementById('flags').innerHTML=WATCH.map(f=>`<span class="flag ${on.has(f)?'on':''}">${f}</span>`).join('');
 document.getElementById('grid').innerHTML=d.macros.map(m=>{
  const bad=m.problems.length?('invalid: '+m.problems.join('; ')):(m.unbound_actions.length?('no keyboard binding: '+m.unbound_actions.join(', ')):'');
  const dis=m.problems.length||(!m.enabled&&!document.getElementById('dry').checked);
  return `<div class="card"><div class="name">${m.name}${m.enabled?'':' <span class="muted">(disabled)</span>'}</div><div class="desc">${m.description||''}</div><div class="warn">${bad}</div><button ${dis?'disabled':''} onclick="run(${JSON.stringify(m.name)})">Run</button></div>`}).join('');
 if(d.running)log('Running: '+d.running);
}catch(e){log('refresh failed: '+e)}}
refresh();setInterval(refresh,2000);
</script></body></html>"""
