"""The summit log page: one self-contained HTML file (works offline and from disk). Only the map
needs the internet: it loads Leaflet (cdnjs) and the map tiles once it is scrolled into view, and
says so instead when they cannot be reached.

Note for the script: top-level names must not shadow window properties (`top`, `name`, `status`,
`parent`, `self`, `length` ...): a `function top()` is a SyntaxError and the whole page stays empty.
tests/test_page.py checks this.
"""
from __future__ import annotations

import json
from datetime import datetime

import re

from . import __version__
from .osm import wiki_url
from .store import Store, atomic_write

LEAFLET = {"css": "https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.css",
           "js": "https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.js"}

TEXT = {
    "en": {"locale": "en-GB", "title": "Summit log",
           "sub": "Summits, huts and passes from your GPS tracks in Intervals.icu (OpenStreetMap: summits within 100 m, huts and passes within 60 m)",
           "kind": {"peak": "Summit", "hut": "Hut", "pass": "Pass"}, "kinds": {"all": "All", "peak": "Summits", "hut": "Huts", "pass": "Passes"},
           "kpi": ["entries", "different places", "summit visits", "activities", "highest: "],
           "timeline": "Summits over time", "spans": ["1 year", "3 years", "5 years", "All"], "top": "My top", "most": "Most visited",
           "high": "Highest", "per_year": "Per year", "log": "Summit log", "search": "Search …", "year": "Year", "kindsel": "Kind",
           "activity": "Activity", "cols": ["Name", "Height", "Activity", "Date"], "more": "Show more", "keep": "Click to keep",
           "open": "Open in Intervals ↗", "close": "Close", "footer": "Data © OpenStreetMap contributors (ODbL) · made by intervals-summits",
           "map": "Map", "mapoff": "The map needs an internet connection (Leaflet and the map tiles).", "first": "first time here",
           "newin": "new in", "firstvisit": "first", "notyet": "not yet", "colls": "Collections", "colllist": "All of them"},
    "de": {"locale": "de-AT", "title": "Gipfelbuch",
           "sub": "Gipfel, Hütten und Pässe aus deinen GPS-Spuren in Intervals.icu (OpenStreetMap: Gipfel bis 100 m, Hütten und Pässe bis 60 m)",
           "kind": {"peak": "Gipfel", "hut": "Hütte", "pass": "Pass"}, "kinds": {"all": "Alle", "peak": "Gipfel", "hut": "Hütten", "pass": "Pässe"},
           "kpi": ["Einträge", "verschiedene Orte", "Gipfelbesuche", "Touren", "höchster: "],
           "timeline": "Gipfel im Zeitverlauf", "spans": ["1 Jahr", "3 Jahre", "5 Jahre", "Gesamt"], "top": "Meine Top", "most": "Häufigste",
           "high": "Höchste", "per_year": "Pro Jahr", "log": "Gipfelbuch", "search": "Suchen …", "year": "Jahr", "kindsel": "Art",
           "activity": "Aktivität", "cols": ["Name", "Höhe", "Aktivität", "Datum"], "more": "Mehr anzeigen", "keep": "Klicken zum Festhalten",
           "open": "In Intervals öffnen ↗", "close": "Schließen", "footer": "Daten © OpenStreetMap-Mitwirkende (ODbL) · erstellt mit intervals-summits",
           "map": "Karte", "mapoff": "Die Karte braucht eine Internetverbindung (Leaflet und die Kartenkacheln).", "first": "zum ersten Mal hier",
           "newin": "neu in", "firstvisit": "zuerst", "notyet": "noch nicht", "colls": "Sammlungen", "colllist": "Alle anzeigen"},
}

PAGE = r"""<!doctype html>
<html lang="__LANG__"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>__TITLE__</title>
<style>
:root{--bg:#f6f7f9;--card:#fff;--ink:#1d2430;--muted:#6b7480;--line:#e3e6eb;--peak:#0b8fb3;--hut:#c2410c;--pass:#7c3aed;--bar:#0ea5c6}
@media (prefers-color-scheme:dark){:root{--bg:#12161c;--card:#1b2129;--ink:#e6e9ee;--muted:#9aa3ae;--line:#2b333d;--peak:#38bdf8;--hut:#fb923c;--pass:#a78bfa;--bar:#22b8d9}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.45 system-ui,-apple-system,Segoe UI,Roboto,sans-serif}
main{max-width:1100px;margin:0 auto;padding:20px 16px 60px}h1{font-size:26px;margin:4px 0 2px}.sub{color:var(--muted);margin:0 0 18px}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px 18px;margin:0 0 16px}
.card h2{font-size:17px;margin:0 0 12px}.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px}
.kpi b{display:block;font-size:24px}.kpi span{color:var(--muted);font-size:13px}
.seg{display:inline-flex;border:1px solid var(--line);border-radius:8px;overflow:hidden}.seg button{border:0;background:none;color:var(--ink);padding:6px 12px;cursor:pointer;font:inherit}
.seg button.on{background:var(--bar);color:#fff}.row{display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin:0 0 10px}
.bars .b{display:grid;grid-template-columns:minmax(120px,240px) 1fr 70px;gap:10px;align-items:center;margin:5px 0}
.bars .name{text-align:right;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.track{background:var(--line);border-radius:6px;height:20px;overflow:hidden}
.fill{background:var(--bar);height:100%;border-radius:6px}.num{font-variant-numeric:tabular-nums;font-weight:600}
.dot{display:inline-block;width:9px;height:9px;border-radius:50%;margin-right:5px}.k-peak{background:var(--peak)}.k-hut{background:var(--hut)}.k-pass{background:var(--pass)}
#scatter svg,#years svg{width:100%;height:auto;display:block}#scatter svg text,#years svg text{fill:var(--muted);font-size:11px}#scatter svg .grid{stroke:var(--line)}
input,select{font:inherit;color:var(--ink);background:var(--card);border:1px solid var(--line);border-radius:8px;padding:6px 9px}
table{width:100%;border-collapse:collapse;font-size:14px}th,td{padding:7px 8px;border-bottom:1px solid var(--line);text-align:left}th{cursor:pointer;color:var(--muted);font-weight:600;white-space:nowrap}
td.r,th.r{text-align:right;font-variant-numeric:tabular-nums}.more{margin-top:10px}
.scwrap{position:relative}.scwrap svg{cursor:crosshair}td a{color:var(--bar);text-decoration:none}
.tip{position:absolute;z-index:5;background:var(--card);border:1px solid var(--line);border-radius:8px;box-shadow:0 4px 14px rgba(0,0,0,.18);padding:8px 10px;font-size:13px;max-width:280px;pointer-events:none}
.tip.pin{pointer-events:auto}.tip .m{color:var(--muted)}.tip a{color:var(--bar);font-weight:600;text-decoration:none}
.tip .x{float:right;border:0;background:none;color:var(--muted);cursor:pointer;font-size:17px;line-height:1;padding:0 0 0 10px}
footer{color:var(--muted);font-size:12px;margin-top:8px}
#map{height:440px;border-radius:8px;background:var(--line);color:var(--muted);display:flex;align-items:center;justify-content:center;text-align:center}
.star{color:#d97706;margin-left:4px}a.w{font-size:11px;font-weight:700;color:var(--muted);border:1px solid var(--line);border-radius:4px;padding:0 3px;margin-left:6px;text-decoration:none}
.cl{columns:2;font-size:14px;padding-left:18px;margin:6px 0}.cl li.got{font-weight:600}details summary{cursor:pointer;color:var(--muted);margin:2px 0 8px}
.leaflet-popup-content{color:#1d2430}.leaflet-popup-content .m{color:#6b7480}.leaflet-popup-content a{color:#0b8fb3}
@media (max-width:600px){.bars .b{grid-template-columns:110px 1fr 54px}td.hide,th.hide{display:none}}
</style></head><body><main>
<h1 id="h1"></h1><p class="sub" id="sub"></p>
<div class="card"><div class="kpis" id="kpis"></div></div>
<div class="card"><h2 id="maph"></h2><div id="map"></div></div>
<div class="card"><h2 id="tl"></h2><div class="row"><div class="seg" id="span"></div></div><div class="scwrap" id="scwrap"><div id="scatter"></div><div class="tip" id="tip" hidden></div></div>
<div class="row" style="margin-top:6px" id="legend"></div></div>
<div class="card"><h2 id="toptitle"></h2><div class="row"><div class="seg" id="topmode"></div><div class="seg" id="topkind"></div><div class="seg" id="topn"></div></div><div class="bars" id="topbars"></div></div>
<div class="card"><h2 id="py"></h2><div id="years"></div></div>
<div class="card" id="collcard" hidden><h2 id="collh"></h2><div class="bars" id="colls"></div></div>
<div class="card"><h2 id="logtitle"></h2>
<div class="row"><input id="q" style="flex:1;min-width:160px"><select id="fy"></select><select id="fk"></select><select id="ft"></select></div>
<table><thead><tr><th data-s="name"></th><th data-s="ele" class="r"></th><th data-s="type" class="hide"></th><th data-s="date"></th></tr></thead><tbody id="rows"></tbody></table>
<button class="more" id="more"></button></div>
<footer id="foot"></footer>
</main><script>
const V=__DATA__,P=__PLACES__,C=__COLL__,T=__TEXT__,META=__META__;const KIND=T.kind,LOC=T.locale;const $=id=>document.getElementById(id);
const fmt=n=>n==null?"–":Math.round(n).toLocaleString(LOC)+" m";const de=d=>new Date(d+"T12:00:00").toLocaleDateString(LOC,{day:"2-digit",month:"2-digit",year:"numeric"});
const esc=s=>String(s??"").replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"})[c]);const ACT=id=>"https://intervals.icu/activities/"+encodeURIComponent(id);
function seg(id,opts,cur,cb){const el=$(id);el.innerHTML="";opts.forEach(([v,l])=>{const b=document.createElement("button");b.textContent=l;if(v===cur)b.className="on";b.onclick=()=>{cb(v);seg(id,opts,v,cb)};el.appendChild(b)})}
// texts
document.title=META.title;$("h1").textContent=META.title;$("sub").textContent=T.sub+(META.range?" – "+META.range:"");$("tl").textContent=T.timeline;$("py").textContent=T.per_year;
$("legend").innerHTML=["peak","hut","pass"].map(k=>`<span><span class="dot k-${k}"></span>${esc(KIND[k])}</span>`).join("");
$("q").placeholder=T.search;document.querySelectorAll("th[data-s]").forEach((th,i)=>th.textContent=T.cols[i]);$("more").textContent=T.more;
$("foot").textContent=T.footer+" "+META.version+" · "+META.generated;
// the first visit of each place: "new this year", the star in the log
const FIRST={};V.forEach(v=>{if(!FIRST[v.osm]||v.date<FIRST[v.osm])FIRST[v.osm]=v.date});
const newThisYear=Object.values(FIRST).filter(d=>d.startsWith(META.year)).length;
// KPIs
const distinct=new Set(V.map(v=>v.osm));const peaks=V.filter(v=>v.kind==="peak");const hi=peaks.reduce((a,b)=>(b.ele||0)>(a.ele||0)?b:a,{});
const acts=new Set(V.map(v=>v.aid));
$("kpis").innerHTML=[[V.length,T.kpi[0]],[distinct.size,T.kpi[1]],[peaks.length,T.kpi[2]],[acts.size,T.kpi[3]],[fmt(hi.ele),T.kpi[4]+(hi.name||"–")],[newThisYear,T.newin+" "+META.year]].map(([b,s])=>`<div class="kpi"><b>${typeof b==="number"?b.toLocaleString(LOC):b}</b><span>${esc(s)}</span></div>`).join("");
// timeline: hover shows a point, a click (tap) keeps it with the link to the activity
let span="all",SP=[],pinned=null;const wrap=$("scwrap"),tip=$("tip");
function scatter(){if(!V.length){$("scatter").innerHTML="";return}const now=new Date(V.reduce((a,v)=>v.date>a?v.date:a,""));let from=new Date(V.reduce((a,v)=>v.date<a?v.date:a,"9999"));
 if(span!=="all"){from=new Date(now);from.setFullYear(now.getFullYear()-span)}const pts=V.filter(v=>v.ele&&new Date(v.date)>=from);
 const W=1000,H=320,L=48,B=28,maxE=Math.ceil(Math.max(...pts.map(p=>p.ele),1000)/1000)*1000,t0=from.getTime(),t1=now.getTime()+864e5;
 const x=d=>L+(new Date(d).getTime()-t0)/(t1-t0)*(W-L-10),y=e=>H-B-e/maxE*(H-B-10);let s=`<svg viewBox="0 0 ${W} ${H}">`;
 for(let e=0;e<=maxE;e+=1000)s+=`<line class="grid" x1="${L}" x2="${W-10}" y1="${y(e)}" y2="${y(e)}"/><text x="${L-6}" y="${y(e)+4}" text-anchor="end">${e.toLocaleString(LOC)}</text>`;
 for(let yr=from.getFullYear();yr<=now.getFullYear();yr++){const d=`${yr}-01-01`;if(new Date(d)>=from)s+=`<text x="${x(d)}" y="${H-8}" text-anchor="middle">${yr}</text>`}
 SP=pts.map(p=>({p,x:x(p.date),y:y(p.ele)}));SP.forEach(q=>s+=`<circle cx="${q.x.toFixed(1)}" cy="${q.y.toFixed(1)}" r="3.2" fill="none" stroke="var(--${q.p.kind})" stroke-width="1.4"/>`);
 s+=`<circle id="hl" r="6.5" fill="none" stroke="var(--ink)" stroke-width="2" visibility="hidden"/>`;$("scatter").innerHTML=s+"</svg>";pinned=null;show(null)}
function nearest(ev){const svg=wrap.querySelector("svg");if(!svg)return null;const r=svg.getBoundingClientRect(),k=1000/r.width,qx=(ev.clientX-r.left)*k,qy=(ev.clientY-r.top)*k;
 let best=null,bd=(14*k)**2;for(const q of SP){const d=(q.x-qx)**2+(q.y-qy)**2;if(d<bd){bd=d;best=q}}return best}
function show(q,pin){const hl=$("hl");if(!q){tip.hidden=true;if(hl)hl.setAttribute("visibility","hidden");return}const p=q.p;
 hl.setAttribute("cx",q.x);hl.setAttribute("cy",q.y);hl.setAttribute("visibility","visible");tip.className="tip"+(pin?" pin":"");
 tip.innerHTML=(pin?`<button class="x" aria-label="${esc(T.close)}">×</button>`:"")+`<b>${esc(p.name)}</b> · ${fmt(p.ele)}<div class="m">${esc(KIND[p.kind])} · ${de(p.date)}</div>`+
  `<div>${esc(p.aname)} <span class="m">(${esc(p.type)})</span></div>`+(pin?`<a href="${ACT(p.aid)}" target="_blank" rel="noopener">${esc(T.open)}</a>`:`<div class="m">${esc(T.keep)}</div>`);
 tip.hidden=false;const r=wrap.querySelector("svg").getBoundingClientRect(),w=wrap.getBoundingClientRect(),k=r.width/1000;
 let tx=r.left-w.left+q.x*k+12,ty=r.top-w.top+q.y*k+12;if(tx+tip.offsetWidth>w.width)tx=Math.max(0,tx-tip.offsetWidth-24);if(ty+tip.offsetHeight>w.height)ty=Math.max(0,ty-tip.offsetHeight-24);
 tip.style.left=tx+"px";tip.style.top=ty+"px"}
wrap.addEventListener("mousemove",ev=>{if(!pinned&&!ev.target.closest(".tip"))show(nearest(ev),false)});
wrap.addEventListener("mouseleave",()=>{if(!pinned)show(null)});
wrap.addEventListener("click",ev=>{if(ev.target.closest(".tip")){if(ev.target.closest(".x")){pinned=null;show(null)}return}pinned=nearest(ev);show(pinned,!!pinned)});
document.addEventListener("keydown",ev=>{if(ev.key==="Escape"&&pinned){pinned=null;show(null)}});
seg("span",[[1,T.spans[0]],[3,T.spans[1]],[5,T.spans[2]],["all",T.spans[3]]],"all",v=>{span=v;scatter()});scatter();
// top list
let topmode="freq",topkind="all",topn=10;function renderTop(){const by={};V.filter(v=>topkind==="all"||v.kind===topkind).forEach(v=>{(by[v.osm]=by[v.osm]||{...v,n:0}).n++});
 let list=Object.values(by);list=topmode==="freq"?list.sort((a,b)=>b.n-a.n):list.filter(v=>v.ele).sort((a,b)=>b.ele-a.ele);list=list.slice(0,topn);$("toptitle").textContent=`${T.top} ${topn}`;
 const max=topmode==="freq"?list[0]?.n||1:list[0]?.ele||1;
 $("topbars").innerHTML=list.map(v=>{const val=topmode==="freq"?v.n:v.ele;return `<div class="b"><div class="name" title="${esc(KIND[v.kind])}"><span class="dot k-${v.kind}"></span>${esc(v.name)}</div><div class="track"><div class="fill" style="width:${(val/max*100).toFixed(1)}%"></div></div><div class="num">${topmode==="freq"?v.n+"×":fmt(v.ele)}</div></div>`}).join("")}
seg("topn",[[10,"10"],[20,"20"],[50,"50"],[100,"100"]],10,v=>{topn=v;renderTop()});seg("topmode",[["freq",T.most],["high",T.high]],"freq",v=>{topmode=v;renderTop()});
seg("topkind",Object.entries(T.kinds),"all",v=>{topkind=v;renderTop()});renderTop();
// per year
(function(){const c={};V.forEach(v=>{const y=v.date.slice(0,4);c[y]=c[y]||{peak:0,hut:0,pass:0};c[y][v.kind]++});const ys=Object.keys(c).sort();if(!ys.length)return;const max=Math.max(...ys.map(y=>c[y].peak+c[y].hut+c[y].pass));
 const nw={};Object.values(FIRST).forEach(d=>{const y=d.slice(0,4);nw[y]=(nw[y]||0)+1});
 const W=1000,H=214,L=36,B=38,bw=(W-L-10)/ys.length;let s=`<svg viewBox="0 0 ${W} ${H}">`;
 ys.forEach((y,i)=>{let base=H-B;["peak","hut","pass"].forEach(k=>{const h=c[y][k]/max*(H-B-14);s+=`<rect x="${L+i*bw+bw*.15}" y="${base-h}" width="${bw*.7}" height="${h}" fill="var(--${k})"><title>${y}: ${c[y][k]} ${esc(KIND[k])}</title></rect>`;base-=h});
 s+=`<text x="${L+i*bw+bw/2}" y="${H-22}" text-anchor="middle">${y}</text><text x="${L+i*bw+bw/2}" y="${base-4}" text-anchor="middle">${c[y].peak+c[y].hut+c[y].pass}</text>`+
  `<text x="${L+i*bw+bw/2}" y="${H-6}" text-anchor="middle"><title>${esc(T.newin)} ${y}</title>★ ${nw[y]||0}</text>`});
 $("years").innerHTML=s+"</svg>"})();
// collections: all summits of an area above a height, and how many of them you have been on
(function(){if(!C.length)return;$("collcard").hidden=false;$("collh").textContent=T.colls;
 $("colls").innerHTML=C.map(c=>{const got=c.members.filter(m=>FIRST[m[0]]).length,all=c.members.length||1;
  const list=c.members.slice().sort((a,b)=>(b[2]||0)-(a[2]||0)).map(m=>`<li class="${FIRST[m[0]]?"got":""}">${FIRST[m[0]]?"✓":"○"} ${esc(m[1])} <span class="m">${fmt(m[2])}${FIRST[m[0]]?" · "+de(FIRST[m[0]]):""}</span></li>`).join("");
  return `<div class="b"><div class="name">${esc(c.label)}</div><div class="track"><div class="fill" style="width:${(got/all*100).toFixed(1)}%"></div></div><div class="num">${got} / ${c.members.length}</div></div>`+
   `<details><summary>${esc(T.colllist)}</summary><ul class="cl">${list}</ul></details>`}).join("")})();
// the map: loaded only once it comes into view (Leaflet and the tiles need the internet)
$("maph").textContent=T.map;let mapAsked=false;
function loadMap(){if(mapAsked)return;mapAsked=true;const el=$("map");if(!META.tiles){el.textContent=T.mapoff;return}
 el.textContent="…";const css=document.createElement("link");css.rel="stylesheet";css.href=META.leaflet.css;document.head.appendChild(css);
 const js=document.createElement("script");js.src=META.leaflet.js;js.onload=drawMap;js.onerror=()=>{el.textContent=T.mapoff};document.head.appendChild(js)}
function drawMap(){const el=$("map");if(!window.L){el.textContent=T.mapoff;return}el.textContent="";el.style.display="block";
 const cs=getComputedStyle(document.documentElement),col=k=>cs.getPropertyValue("--"+k).trim()||"#0b8fb3";
 const lmap=L.map(el,{scrollWheelZoom:false});L.tileLayer(META.tiles.url,{attribution:META.tiles.attribution,subdomains:META.tiles.sub||"abc",maxZoom:17}).addTo(lmap);
 const by={};V.forEach(v=>{if(!P[v.osm])return;const o=by[v.osm]=by[v.osm]||{v,n:0,acts:[]};o.n++;o.acts.push(v)});
 const groups={peak:L.layerGroup(),hut:L.layerGroup(),pass:L.layerGroup()},pts=[];
 Object.entries(by).forEach(([osm,o])=>{const pl=P[osm],v=o.v;pts.push([pl[0],pl[1]]);
  const acts=o.acts.slice().sort((a,b)=>b.date.localeCompare(a.date)).slice(0,6).map(a=>`<div><a href="${ACT(a.aid)}" target="_blank" rel="noopener">${de(a.date)}</a> ${esc(a.aname)}</div>`).join("");
  const html=`<b>${esc(v.name)}</b> · ${fmt(v.ele)}<div class="m">${esc(KIND[v.kind])} · ${o.n}× · ${esc(T.firstvisit)} ${de(FIRST[osm])}</div>`+
   (pl[2]?`<div><a href="${esc(pl[2])}" target="_blank" rel="noopener">Wikipedia ↗</a></div>`:"")+acts+(o.n>6?`<div class="m">…</div>`:"");
  L.circleMarker([pl[0],pl[1]],{radius:4+Math.min(6,Math.log2(o.n)*1.5),color:col(v.kind),weight:2,fillOpacity:.55}).bindPopup(html).addTo(groups[v.kind])});
 const overlays={};["pass","hut","peak"].forEach(k=>groups[k].addTo(lmap));["peak","hut","pass"].forEach(k=>overlays[T.kinds[k]]=groups[k]);
 C.forEach(c=>{const g=L.layerGroup();c.members.filter(m=>!by[m[0]]&&!FIRST[m[0]]).forEach(m=>L.circleMarker([m[3],m[4]],{radius:3,color:"#888",weight:1,fillOpacity:.2})
  .bindPopup(`<b>${esc(m[1])}</b> · ${fmt(m[2])}<div class="m">${esc(c.label)} · ${esc(T.notyet)}</div>`).addTo(g));overlays[`${c.label} – ${T.notyet}`]=g});
 L.control.layers(null,overlays,{collapsed:true}).addTo(lmap);
 // the view: where most of it is – a far-away trip (Kilimanjaro, say) is still on the map, a zoom out away
 const q=(a,f)=>a[Math.min(a.length-1,Math.max(0,Math.round(f*(a.length-1))))],la=pts.map(x=>x[0]).sort((a,b)=>a-b),lo=pts.map(x=>x[1]).sort((a,b)=>a-b);
 const cut=pts.length>=50?.1:pts.length>=20?.05:0;if(pts.length)lmap.fitBounds([[q(la,cut),q(lo,cut)],[q(la,1-cut),q(lo,1-cut)]],{padding:[20,20],maxZoom:12});else lmap.setView([47.3,11.4],8)}
if(window.IntersectionObserver){const seen=new IntersectionObserver(es=>{if(es.some(e=>e.isIntersecting)){seen.disconnect();loadMap()}});seen.observe($("map"))}else loadMap();
// the log
const yearList=[...new Set(V.map(v=>v.date.slice(0,4)))].sort().reverse(),typeList=[...new Set(V.map(v=>v.type))].sort();
$("fy").innerHTML=`<option value="">${esc(T.year)}</option>`+yearList.map(y=>`<option>${y}</option>`).join("");
$("fk").innerHTML=`<option value="">${esc(T.kindsel)}</option>`+Object.entries(KIND).map(([k,l])=>`<option value="${k}">${esc(l)}</option>`).join("");
$("ft").innerHTML=`<option value="">${esc(T.activity)}</option>`+typeList.map(t=>`<option>${esc(t)}</option>`).join("");
let sortBy="date",dir=-1,shown=50;function renderLog(){const q=$("q").value.toLowerCase(),fy=$("fy").value,fk=$("fk").value,ft=$("ft").value;
 let rows=V.filter(v=>(!q||v.name.toLowerCase().includes(q)||(v.aname||"").toLowerCase().includes(q))&&(!fy||v.date.startsWith(fy))&&(!fk||v.kind===fk)&&(!ft||v.type===ft));
 rows.sort((a,b)=>{const x=a[sortBy]??-1,y=b[sortBy]??-1;return (x>y?1:x<y?-1:0)*dir});$("logtitle").textContent=`${T.log} (${rows.length.toLocaleString(LOC)})`;
 $("rows").innerHTML=rows.slice(0,shown).map(v=>`<tr><td><span class="dot k-${v.kind}" title="${esc(KIND[v.kind])}"></span>${esc(v.name)}${FIRST[v.osm]===v.date?`<span class="star" title="${esc(T.first)}">★</span>`:""}${P[v.osm]&&P[v.osm][2]?`<a class="w" href="${esc(P[v.osm][2])}" target="_blank" rel="noopener" title="Wikipedia">W</a>`:""}</td><td class="r">${fmt(v.ele)}</td><td class="hide"><a href="${ACT(v.aid)}" target="_blank" rel="noopener" title="${esc(v.aname)}">${esc(v.type)} ↗</a></td><td>${de(v.date)}</td></tr>`).join("");
 $("more").style.display=rows.length>shown?"":"none"}
document.querySelectorAll("th[data-s]").forEach(th=>th.onclick=()=>{const s=th.dataset.s;dir=sortBy===s?-dir:(s==="name"||s==="type"?1:-1);sortBy=s;renderLog()});
["q","fy","fk","ft"].forEach(id=>$(id).oninput=()=>{shown=50;renderLog()});$("more").onclick=()=>{shown+=100;renderLog()};renderLog();
</script></body></html>"""


def _script_json(value) -> str:
    """JSON safe inside a <script> element."""
    return json.dumps(value, ensure_ascii=False).replace("</", "<\\/")


def rows(store: Store) -> list[dict]:
    return [{"date": (v["start"] or "")[:10], "type": v["type"], "aname": v["aname"], "aid": v["activity_id"], "osm": v["osm"],
             "name": v["name"], "kind": v["kind"], "ele": round(v["ele"]) if v["ele"] is not None else None}
            for v in store.all_visits()]


def places(store: Store) -> dict[str, list]:
    return {osm: [round(p["lat"], 5), round(p["lon"], 5), wiki_url(p["wiki"])] for osm, p in store.places().items()}


def collections(store: Store, wanted) -> list[dict]:
    out = []
    for c in wanted or ():
        got = store.collection(c.key)
        if got:
            out.append({"label": c.label, "members": [[m["osm"], m["name"], m["ele"], m["lat"], m["lon"]] for m in got["members"]]})
    return out


def render(store: Store, language: str = "en", title: str = "", *, tiles: dict | None = None, wanted=()) -> str:
    text = TEXT.get(language, TEXT["en"])
    data = rows(store)
    span = f"{data[0]['date'][:4]}–{data[-1]['date'][:4]}" if data else ""
    now = datetime.now()
    meta = {"title": title or text["title"], "range": span, "version": __version__, "year": str(now.year),
            "generated": now.strftime("%Y-%m-%d %H:%M"), "tiles": tiles, "leaflet": LEAFLET}
    lang = language if language in TEXT else "en"
    # one pass, so that nothing inserted (a name, say) is taken for a placeholder itself
    values = {"LANG": lang, "TITLE": (title or text["title"]).replace("<", "&lt;"), "TEXT": _script_json(text),
              "META": _script_json(meta), "PLACES": _script_json(places(store)),
              "COLL": _script_json(collections(store, wanted)), "DATA": _script_json(data)}
    return re.sub(r"__(LANG|TITLE|TEXT|META|PLACES|COLL|DATA)__", lambda m: values[m.group(1)], PAGE)


def write(store: Store, path, language: str = "en", title: str = "", *, tiles: dict | None = None, wanted=()) -> int:
    html = render(store, language, title, tiles=tiles, wanted=wanted)
    atomic_write(path, html.encode("utf-8"), readable=True)
    return len(html)
