"""Crystal Memory Interface: an admin page that reads the Memory Lock.

The page itself is static and holds no data. It asks for an admin login token
and then reads the admin-only /memory API. It shows only what the API returns;
it never labels anything verified or archived on its own."""
from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter(tags=["crystal-memory"])

PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Crystal Memory</title>
<style>
body{font-family:system-ui,sans-serif;margin:0;background:#0b1220;color:#e6edf7}
header{padding:16px;border-bottom:1px solid #223}main{padding:16px;max-width:1100px;margin:auto}
input,button,select{padding:8px;border-radius:6px;border:1px solid #345;background:#121b2e;color:#e6edf7}
button{cursor:pointer}table{width:100%;border-collapse:collapse;margin-top:12px;font-size:13px}
td,th{border-bottom:1px solid #223;padding:6px;text-align:left;word-break:break-all}
.ok{color:#5be08a}.bad{color:#ff6b6b}.mut{color:#8aa}pre{white-space:pre-wrap;background:#121b2e;padding:10px;border-radius:6px}
</style></head><body><header><b>Crystal Memory</b> <span class="mut">- Memory Lock reader (admin)</span></header>
<main>
<p>Paste an admin login token (from <code>/api/v1/auth/login</code>). It stays in this page only.</p>
<input id="t" type="password" size="50" placeholder="admin token"> <button onclick="load()">Load</button>
<button onclick="verify()">Verify whole chain</button>
<div id="v" style="margin:12px 0"></div>
<div>Auction filter: <input id="a" placeholder="auction id (optional)"> <button onclick="load()">Filter</button></div>
<table><thead><tr><th>#</th><th>Event</th><th>Auction</th><th>Lot</th><th>Time</th><th>Hash</th><th></th></tr></thead><tbody id="rows"></tbody></table>
<pre id="d"></pre></main>
<script>
const H=()=>({Authorization:"Bearer "+document.getElementById("t").value});
const esc=s=>String(s==null?"":s).replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
async function j(u,o){const r=await fetch(u,Object.assign({headers:H()},o||{}));if(!r.ok)throw new Error(r.status+" "+await r.text());return r.json()}
async function load(){try{const a=document.getElementById("a").value.trim();
const rows=await j("/api/v1/memory/records?limit=200"+(a?"&auction_id="+encodeURIComponent(a):""));
document.getElementById("rows").innerHTML=rows.map(r=>`<tr><td>${esc(r.sequence)}</td><td>${esc(r.event_type)}</td><td>${esc(r.auction_id)}</td><td>${esc(r.lot_id)}</td><td>${esc(r.occurred_at)}</td><td>${esc(r.event_hash.slice(0,16))}...</td><td><button onclick="detail(${Number(r.sequence)})">Open</button></td></tr>`).join("")}catch(e){document.getElementById("d").textContent=e.message}}
async function detail(n){try{const [rec,prov,arc]=await Promise.all([j("/api/v1/memory/records/"+n),j("/api/v1/memory/records/"+n+"/provenance"),j("/api/v1/memory/records/"+n+"/manifest")]);
document.getElementById("d").textContent=JSON.stringify({record:rec,provenance:prov,manifest:arc},null,2)}catch(e){document.getElementById("d").textContent=e.message}}
async function verify(){const v=document.getElementById("v");v.textContent="Verifying...";try{const r=await j("/api/v1/memory/verify");
v.innerHTML=`<b class="${r.status==="VERIFIED"?"ok":"bad"}">${esc(r.status)}</b> - ${esc(r.records_checked)} records checked`+(r.failure_reason?` - ${esc(r.failure_reason)} at #${esc(r.first_failure_sequence)}`:"")}catch(e){v.textContent=e.message}}
</script></body></html>"""


@router.get("/crystal", response_class=HTMLResponse, include_in_schema=False)
def crystal_page():
    return PAGE
