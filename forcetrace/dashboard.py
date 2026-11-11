"""One self-contained HTML dashboard for several runs: metric cards + overlaid force, depth and top-down plots.

No external requests: data is embedded as JSON and drawn with inline SVG by a small script.
"""
import json

import numpy as np

from forcetrace.metrics import verdict

CARD_KEYS = [
    ("peak force", "peak_force_n", "N", 1),
    ("impulse in contact", "impulse_ns", "N·s", 2),
    ("time in contact", "time_in_contact_s", "s", 2),
    ("contact to insertion", "time_to_insert_s", "s", 2),
    ("jammed since", "jam_t", "s", 2),
    ("axial overshoot", "overshoot_pct", "%", 0),
    ("final depth", "final_depth_m", "mm", 1),
]


def _thin(a, n):
    a = np.asarray(a, dtype=float)
    if len(a) <= n:
        return a
    return a[np.linspace(0, len(a) - 1, n).astype(int)]


def build_payload(runs, hole=None, half=0.0005, max_points=700):
    """runs: [(label, data, metrics)] -> JSON-able dict for the page."""
    out = []
    for label, d, m in runs:
        r = {"name": label, "verdict": verdict(m), "t": _thin(d["t"], max_points).round(4).tolist(),
             "force": _thin(d["force"], max_points).round(3).tolist(), "cards": []}
        if "depth" in d:
            r["depth"] = (_thin(d["depth"], max_points) * 1e3).round(3).tolist()
        if "x" in d and "y" in d:
            ref = (hole[0], hole[1]) if hole else (d["x"][0], d["y"][0])
            r["x"] = ((_thin(d["x"], max_points) - ref[0]) * 1e3).round(3).tolist()
            r["y"] = ((_thin(d["y"], max_points) - ref[1]) * 1e3).round(3).tolist()
        for lab, key, unit, nd in CARD_KEYS:
            v = m.get(key)
            if v is None:
                continue
            if key == "final_depth_m":
                v = v * 1e3
            r["cards"].append([lab, f"{v:.{nd}f} {unit}"])
        out.append(r)
    return {"runs": out, "zone_half_mm": half * 1e3 if hole else None}


def write_dashboard(runs, path, hole=None, half=0.0005, title="forcetrace dashboard"):
    payload = build_payload(runs, hole, half)
    html = TEMPLATE.replace("__TITLE__", title.replace("<", "&lt;")).replace(
        "__DATA__", json.dumps(payload).replace("</", "<\\/"))
    with open(path, "w") as f:
        f.write(html)


TEMPLATE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>__TITLE__</title>
<style>
:root{--bg:#f6f7f9;--panel:#fff;--ink:#1d2330;--mute:#6b7280;--line:#e3e6ec;--grid:#eceff3;--ok:#1f9d55;--bad:#d64545;--warn:#8a8f98}
@media (prefers-color-scheme:dark){:root{--bg:#14171c;--panel:#1c2027;--ink:#e6e9ef;--mute:#98a1b0;--line:#2b313b;--grid:#262b34}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:14px/1.45 system-ui,sans-serif}
main{max-width:1100px;margin:0 auto;padding:20px 16px 40px}h1{font-size:20px;margin:0 0 4px}.sub{color:var(--mute);margin:0 0 16px}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:12px;margin-bottom:16px}
.card{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:12px 14px;border-top:4px solid var(--c)}
.card.off{opacity:.38}.card h2{font-size:13px;margin:0 0 6px;display:flex;justify-content:space-between;gap:8px;cursor:pointer;word-break:break-all}
.badge{font-weight:700;font-size:12px;white-space:nowrap}.INSERTED{color:var(--ok)}.JAMMED{color:var(--bad)}.NOTINSERTED,.NODEPTHDATA{color:var(--warn)}
.row{display:flex;justify-content:space-between;color:var(--mute);font-size:12.5px}.row b{color:var(--ink);font-weight:600}
.panels{display:grid;grid-template-columns:1fr 1fr;gap:12px}.panel{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:10px 12px}
.panel.wide{grid-column:1/-1}.panel h3{font-size:13px;margin:0 0 4px;color:var(--mute);font-weight:600;display:flex;justify-content:space-between}
svg{width:100%;height:auto;display:block}text{fill:var(--mute);font-size:11px}.axis{stroke:var(--line)}.gridl{stroke:var(--grid)}
button{background:none;border:1px solid var(--line);color:var(--mute);border-radius:6px;font-size:11px;padding:1px 8px;cursor:pointer}
#tip{position:fixed;pointer-events:none;background:var(--panel);border:1px solid var(--line);border-radius:6px;padding:6px 8px;font-size:12px;display:none;box-shadow:0 2px 8px #0002}
@media (max-width:760px){.panels{grid-template-columns:1fr}}
</style></head><body><main>
<h1>__TITLE__</h1><p class="sub">Click a card to hide or show a run. Hover a plot to read values. Force on the Gazebo logs is the commanded spring force, on the MuJoCo logs it is simulated contact force.</p>
<div class="cards" id="cards"></div>
<div class="panels">
<div class="panel wide"><h3><span>Force |F| (N)</span><button id="logbtn">log scale</button></h3><div id="pf"></div></div>
<div class="panel"><h3>Insertion depth (mm)</h3><div id="pd"></div></div>
<div class="panel"><h3>Tip path, top-down (mm, green = insert zone)</h3><div id="pm"></div></div>
</div><div id="tip"></div></main>
<script>
const D=__DATA__,COL=["#2f6fdb","#d64545","#1f9d55","#8e5bd6","#e08a1e","#14a6b8","#b0568f","#6b7280"];
const runs=D.runs.map((r,i)=>Object.assign(r,{c:COL[i%COL.length],on:true}));
const NS="http://www.w3.org/2000/svg",tip=document.getElementById("tip");let LOG=false;
const el=(n,a,p,t)=>{const e=document.createElementNS(NS,n);for(const k in a)e.setAttribute(k,a[k]);if(t!==undefined)e.textContent=t;if(p)p.appendChild(e);return e};
const ext=(f)=>{let lo=Infinity,hi=-Infinity;runs.filter(r=>r.on).forEach(r=>(f(r)||[]).forEach(v=>{if(v<lo)lo=v;if(v>hi)hi=v}));return lo===Infinity?[0,1]:[lo,hi===lo?lo+1:hi]};
const nice=(lo,hi,n)=>{const s=(hi-lo)/n,p=Math.pow(10,Math.floor(Math.log10(s))),m=s/p,u=(m<1.5?1:m<3?2:m<7?5:10)*p,a=Math.floor(lo/u)*u,o=[];for(let v=a;v<=hi+u*.001;v+=u)o.push(+v.toFixed(10));return o};
function chart(host,key,opts){
  host.innerHTML="";const W=opts.w||520,H=opts.h||250,m={l:44,r:12,t:8,b:30};
  const svg=el("svg",{viewBox:`0 0 ${W} ${H}`},host);
  const xs=opts.xkey?ext(r=>r[opts.xkey]):ext(r=>r.t),ys=ext(r=>r[key]);
  const lg=opts.log&&LOG,ty=v=>lg?Math.log10(1+Math.max(0,v)):v;
  let [y0,y1]=[opts.zero?Math.min(0,ys[0]):ys[0],ys[1]];if(opts.equal){const a=Math.max(Math.abs(xs[0]),Math.abs(xs[1]),Math.abs(ys[0]),Math.abs(ys[1]),(D.zone_half_mm||0)*1.3);xs[0]=y0=-a;xs[1]=y1=a}
  const pad=(y1-y0)*.06;if(!opts.equal){y1+=pad;if(!opts.zero)y0-=pad}
  const X=v=>m.l+(v-xs[0])/(xs[1]-xs[0])*(W-m.l-m.r),Y=v=>H-m.b-(ty(v)-ty(y0))/(ty(y1)-ty(y0))*(H-m.t-m.b);
  nice(xs[0],xs[1],6).forEach(v=>{if(v<xs[0]||v>xs[1])return;el("line",{x1:X(v),x2:X(v),y1:m.t,y2:H-m.b,class:"gridl"},svg);el("text",{x:X(v),y:H-m.b+14,"text-anchor":"middle"},svg,v)});
  (lg?[0,1,3,10,30,100,300].filter(v=>v<=y1):nice(y0,y1,5)).forEach(v=>{if(v<y0||v>y1)return;el("line",{x1:m.l,x2:W-m.r,y1:Y(v),y2:Y(v),class:"gridl"},svg);el("text",{x:m.l-5,y:Y(v)+4,"text-anchor":"end"},svg,v)});
  el("text",{x:W-m.r,y:H-4,"text-anchor":"end"},svg,opts.xlabel||"time (s)");
  if(opts.hole&&D.zone_half_mm){const h=D.zone_half_mm;el("rect",{x:X(-h),y:Y(h),width:X(h)-X(-h),height:Y(-h)-Y(h),fill:"#2ca02c22",stroke:"#2ca02c","stroke-width":1.4},svg);el("text",{x:X(h)+3,y:Y(h)-3},svg,"insert zone ±"+h.toFixed(1)+" mm")}
  const xk=opts.xkey||"t";
  runs.filter(r=>r.on&&r[key]).forEach(r=>{const pts=r[key].map((v,i)=>X(r[xk][i]).toFixed(1)+","+Y(v).toFixed(1)).join(" ");
    el("polyline",{points:pts,fill:"none",stroke:r.c,"stroke-width":1.8,"stroke-linejoin":"round"},svg);
    if(opts.xkey){const l=r[key].length-1;el("circle",{cx:X(r[xk][l]),cy:Y(r[key][l]),r:4,fill:r.c},svg)}});
  if(opts.xkey)return;
  const cur=el("line",{y1:m.t,y2:H-m.b,stroke:"var(--mute)","stroke-dasharray":"3 3",visibility:"hidden"},svg);
  const hit=el("rect",{x:m.l,y:m.t,width:W-m.l-m.r,height:H-m.t-m.b,fill:"transparent"},svg);
  hit.addEventListener("mousemove",e=>{const b=svg.getBoundingClientRect(),px=(e.clientX-b.left)/b.width*W,t=xs[0]+(px-m.l)/(W-m.l-m.r)*(xs[1]-xs[0]);
    cur.setAttribute("x1",px);cur.setAttribute("x2",px);cur.setAttribute("visibility","visible");
    let h=`<b>t = ${t.toFixed(2)} s</b>`;runs.filter(r=>r.on&&r[key]).forEach(r=>{let lo=0,hi=r.t.length-1;while(lo<hi){const mid=(lo+hi)>>1;if(r.t[mid]<t)lo=mid+1;else hi=mid}
      h+=`<div><span style="color:${r.c}">●</span> ${r.name}: ${r[key][lo].toFixed(2)}</div>`});
    tip.innerHTML=h;tip.style.display="block";tip.style.left=Math.min(innerWidth-240,e.clientX+14)+"px";tip.style.top=e.clientY+14+"px"});
  hit.addEventListener("mouseleave",()=>{tip.style.display="none";cur.setAttribute("visibility","hidden")});
}
function draw(){chart(pf,"force",{log:true,zero:true,w:1040,h:300});chart(pd,"depth",{zero:false});
  if(runs.some(r=>r.x)){chart(pm,"y",{xkey:"x",equal:true,hole:true,xlabel:"x (mm)",h:250})}else pm.innerHTML='<p class="sub">no x/y columns in these logs</p>'}
const pf=document.getElementById("pf"),pd=document.getElementById("pd"),pm=document.getElementById("pm"),cards=document.getElementById("cards");
runs.forEach(r=>{const c=document.createElement("div");c.className="card";c.style.setProperty("--c",r.c);
  c.innerHTML=`<h2><span>${r.name}</span><span class="badge ${r.verdict.replace(/ /g,"")}">${r.verdict}</span></h2>`+r.cards.map(k=>`<div class="row"><span>${k[0]}</span><b>${k[1]}</b></div>`).join("");
  c.querySelector("h2").onclick=()=>{r.on=!r.on;c.classList.toggle("off",!r.on);draw()};cards.appendChild(c)});
document.getElementById("logbtn").onclick=e=>{LOG=!LOG;e.target.textContent=LOG?"linear scale":"log scale";draw()};
{const all=runs.flatMap(r=>r.force).sort((a,b)=>a-b);if(all[all.length-1]>6*Math.max(1,all[Math.floor(all.length*.95)])){LOG=true;document.getElementById("logbtn").textContent="linear scale"}}
draw();
</script></body></html>
"""
