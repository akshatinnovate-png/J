/* The care-flow canvas: chronological events as floating cards, joined by
   bezier streams. Cards are real DOM so they can carry shadows, images and
   controls; the streams are one SVG layer beneath them. */

import * as E from './engine.js';
import {renderStudy,SHORT} from './imaging.js';

export const CATEGORIES=['Docs','Labs','Imaging','Medications','Visits','Findings'];
const CAT_COLOR={Docs:'#2F6BFF',Labs:'#0FA3A3',Imaging:'#7C5CFF',
                 Medications:'#E8A23A',Visits:'#2F6BFF',Findings:'#F2545B'};

const ICONS={
  Docs:'<path d="M4 2h6l4 4v10a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V3a1 1 0 0 1 1-1z"/><path d="M10 2v5h5"/>',
  Labs:'<path d="M7 2v5L3.5 14A1.5 1.5 0 0 0 5 16h8a1.5 1.5 0 0 0 1.5-2L11 7V2"/><path d="M6 2h6"/>',
  Imaging:'<rect x="2.5" y="3" width="13" height="12" rx="2"/><circle cx="9" cy="9" r="3"/>',
  Medications:'<rect x="2" y="6" width="14" height="6" rx="3"/><path d="M9 6v6"/>',
  Visits:'<path d="M9 15s-5.5-3.6-5.5-7a3 3 0 0 1 5.5-1.7A3 3 0 0 1 14.5 8c0 3.4-5.5 7-5.5 7z"/>',
  Findings:'<circle cx="9" cy="9" r="6.5"/><path d="M9 5.5v4M9 12.2v.4"/>',
};
const icon=c=>`<svg viewBox="0 0 18 18" fill="none" stroke="currentColor" stroke-width="1.6"
  stroke-linecap="round" stroke-linejoin="round">${ICONS[c]||ICONS.Findings}</svg>`;

/* ── build events from the case ── */
export function buildNodes(c,cats=CATEGORIES){
  const want=new Set(cats);
  const flagged=new Set();
  c.flags.filter(f=>f.severity==='possible').forEach(f=>f.evidence.forEach(e=>flagged.add(e)));
  const out=[];

  if(want.has('Docs')) for(const d of c.documents){
    if(!d.text.trim()) continue;
    out.push({id:d.docId,cat:'Docs',kind:'chip',title:d.docType||'Document',
      sub:d.filename.replace(/\.(txt|pdf|md)$/,''),date:d.docDate,docId:d.docId,
      detail:`${d.pageCount} page(s)`});
  }
  if(want.has('Imaging')) for(const r of c.imaging){
    out.push({id:r.factId,cat:'Imaging',kind:'image',title:SHORT[r.modality]||r.modality,
      sub:(r.bodyPart||'').replace(/^\w/,m=>m.toUpperCase())||'Study',
      date:r.observedOn,docId:r.prov.docId,factId:r.factId,modality:r.modality,
      detail:r.reportText||'',flagged:flagged.has(r.factId)});
  }
  if(want.has('Labs')){
    const series=E.buildSeries(c);
    const seriesOf={}; series.forEach(s=>s.points.forEach(p=>seriesOf[p.factId]=s));
    // Only the most recent reading of a series is drawn as a sparkline; repeating
    // the same chart at every point reads as duplicated cards.
    const sparkAt=new Set(series.filter(s=>s.points.length>=3)
      .map(s=>s.points[s.points.length-1].factId));
    for(const m of c.measurements){
      if(m.analyte==='bp_systolic'||m.analyte==='bp_diastolic') continue;
      const s=seriesOf[m.factId];
      const multi=sparkAt.has(m.factId);
      out.push({id:m.factId,cat:'Labs',kind:multi?'spark':'chip',
        title:E.display(m.analyte),sub:`${E.fmt(m.value)} ${m.unit||''}`.trim(),
        date:m.observedOn,docId:m.prov.docId,factId:m.factId,detail:m.prov.raw,
        flagged:flagged.has(m.factId),series:multi?s:null,value:m.value,unit:m.unit,
        refLow:m.refLow,refHigh:m.refHigh,analyte:m.analyte});
    }
  }
  if(want.has('Visits')) for(const m of c.measurements){
    if(m.analyte!=='bp_systolic') continue;
    const dia=c.measurements.find(d=>d.analyte==='bp_diastolic'&&
      d.prov.line===m.prov.line&&d.prov.docId===m.prov.docId);
    out.push({id:m.factId,cat:'Visits',kind:'chip',title:'Blood pressure',
      sub:dia?`${E.fmt(m.value)}/${E.fmt(dia.value)} mmHg`:`${E.fmt(m.value)} mmHg`,
      date:m.observedOn,docId:m.prov.docId,factId:m.factId,detail:m.prov.raw,
      flagged:flagged.has(m.factId)});
  }
  if(want.has('Medications')) for(const s of c.statements){
    if(s.category!=='medication') continue;
    out.push({id:s.factId,cat:'Medications',kind:'chip',
      title:(s.subject||'Medication').replace(/^\w/,m=>m.toUpperCase()),
      sub:s.text.replace(new RegExp('^'+(s.subject||''),'i'),'').trim().slice(0,30),
      date:s.observedOn,docId:s.prov.docId,factId:s.factId,detail:s.prov.raw,
      flagged:flagged.has(s.factId)});
  }
  if(want.has('Findings')) for(const s of c.statements){
    if(!['observation','instruction','allergy'].includes(s.category)) continue;
    out.push({id:s.factId,cat:'Findings',kind:'flat',
      title:s.category.replace(/^\w/,m=>m.toUpperCase()),sub:s.text.slice(0,42),
      date:s.observedOn,docId:s.prov.docId,factId:s.factId,detail:s.prov.raw,
      flagged:flagged.has(s.factId)});
  }
  return out.filter(n=>n.date);
}

/* ── layout: a column per date, cards staggered to avoid collision ── */
const SIZE={chip:[188,44],flat:[168,38],spark:[196,78],image:[150,112]};

export function layout(nodes,width,height){
  if(!nodes.length) return {nodes:[],width,height,months:[],spineY:height/2};
  nodes=nodes.slice().sort((a,b)=>a.date-b.date||a.cat.localeCompare(b.cat));
  const t0=Math.min(...nodes.map(n=>+n.date)), t1=Math.max(...nodes.map(n=>+n.date));
  const span=Math.max(t1-t0,1);

  const byDate={};
  nodes.forEach(n=>{const k=+n.date;(byDate[k]=byDate[k]||[]).push(n);});
  const dates=Object.keys(byDate).map(Number).sort((a,b)=>a-b);

  const padL=92, padR=170, padT=74, padB=118;
  const MAX_PER_COL=9, SUBCOL=214;
  const colMin=268;
  const usable=Math.max(width-padL-padR, dates.length*colMin);
  const xs={}; let prev=-Infinity;
  dates.forEach(d=>{
    let x=padL+((d-t0)/span)*usable;
    if(x-prev<colMin) x=prev+colMin;
    xs[d]=x; prev=x;
  });
  const widest=Math.max(...dates.map(d=>Math.ceil(byDate[d].length/9)));
  const contentW=Math.max(width,(xs[dates[dates.length-1]]||padL)+(widest-1)*214+padR);

  const order={Docs:0,Imaging:1,Visits:2,Labs:3,Medications:4,Findings:5};
  let maxY=0, minY=0;
  dates.forEach(d=>{
    const g=byDate[d].sort((a,b)=>(order[a.cat]??9)-(order[b.cat]??9)||a.title.localeCompare(b.title));
    const mid=(height-padT-padB)/2+padT;
    // a busy date is split across sub-columns rather than stacked into one tall run
    const cols=[];
    for(let i=0;i<g.length;i+=MAX_PER_COL) cols.push(g.slice(i,i+MAX_PER_COL));
    cols.forEach((col,ci)=>{
      let up=0, down=0;
      col.forEach((n,i)=>{
        const [w,h]=SIZE[n.kind]||SIZE.chip;
        n.w=w; n.h=h;
        const goUp=i%2===0;
        if(goUp){ up+=h+16; n.y=mid-up+h/2; }
        else{ down+=h+16; n.y=mid+down-h/2; }
        n.x=xs[d]+ci*SUBCOL+((i%3)-1)*11;
        maxY=Math.max(maxY,n.y+h/2); minY=Math.min(minY,n.y-h/2);
      });
    });
  });

  // months rail
  const months=[]; const d0=new Date(t0), d1=new Date(t1);
  let cur=new Date(Date.UTC(d0.getUTCFullYear(),d0.getUTCMonth(),1));
  let lastYear=null;
  while(cur<=d1){
    const x=padL+((+cur-t0)/span)*usable;
    if(x>=0&&x<=contentW){
      const y=cur.getUTCFullYear();
      months.push({x,label:cur.toLocaleString('en',{month:'long',timeZone:'UTC'}),
        year:y!==lastYear?y:null});
      lastYear=y;
    }
    cur=new Date(Date.UTC(cur.getUTCFullYear(),cur.getUTCMonth()+1,1));
  }
  const contentH=Math.max(height, maxY-minY+padT+padB);
  const shift=minY<padT? padT-minY : 0;
  if(shift) nodes.forEach(n=>n.y+=shift);
  return {nodes,width:contentW,height:Math.max(height,contentH),months,
          spineY:(height-padT-padB)/2+padT+shift};
}

/* ── streams ── */
function path(x0,y0,x1,y1){
  const dx=Math.max(Math.abs(x1-x0)*0.42,34);
  return `M ${x0} ${y0} C ${x0+dx} ${y0}, ${x1-dx} ${y1}, ${x1} ${y1}`;
}
export function streams(L,focus){
  if(!L.nodes.length) return '';
  const parts=[];
  const byDoc={}; L.nodes.forEach(n=>(byDoc[n.docId]=byDoc[n.docId]||[]).push(n));

  // each document feeds the events extracted from it
  for(const [docId,group] of Object.entries(byDoc)){
    const src=group.find(n=>n.cat==='Docs');
    if(!src) continue;
    for(const n of group){
      if(n===src) continue;
      const dim=focus&&focus!==n.id&&focus!==src.id;
      parts.push(`<path d="${path(src.x+src.w/2,src.y,n.x-n.w/2,n.y)}" fill="none"
        stroke="${CAT_COLOR[n.cat]||'#2F6BFF'}" stroke-width="1.5"
        opacity="${dim?0.06:0.30}" stroke-linecap="round"/>`);
    }
  }
  // repeated measurements chain forward in time
  const chains={};
  L.nodes.filter(n=>n.cat==='Labs'||n.cat==='Visits')
    .forEach(n=>(chains[n.title]=chains[n.title]||[]).push(n));
  for(const chain of Object.values(chains)){
    if(chain.length<2) continue;
    chain.sort((a,b)=>a.x-b.x);
    for(let i=0;i<chain.length-1;i++){
      const a=chain[i],b=chain[i+1];
      const dim=focus&&focus!==a.id&&focus!==b.id;
      parts.push(`<path d="${path(a.x+a.w/2,a.y,b.x-b.w/2,b.y)}" fill="none"
        stroke="#2F6BFF" stroke-width="${dim?1.4:2}"
        opacity="${dim?0.07:0.55}" stroke-linecap="round"/>`);
    }
  }
  return parts.join('');
}

/* ── card markup ── */
function sparkSVG(series,w=172,h=30){
  const pts=series.points;
  if(pts.length<2) return '';
  const xs=pts.map(p=>+p.date), ys=pts.map(p=>p.value);
  const x0=Math.min(...xs),x1=Math.max(...xs),y0=Math.min(...ys),y1=Math.max(...ys);
  const sx=v=>((v-x0)/Math.max(x1-x0,1))*w;
  const sy=v=>h-((v-y0)/Math.max(y1-y0,1e-9))*h;
  const d=pts.map((p,i)=>`${i?'L':'M'} ${sx(+p.date).toFixed(1)} ${sy(p.value).toFixed(1)}`).join(' ');
  const area=`${d} L ${w} ${h} L 0 ${h} Z`;
  return `<svg class="spark" viewBox="0 0 ${w} ${h}" preserveAspectRatio="none">
    <defs><linearGradient id="sg" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="#2F6BFF" stop-opacity=".22"/>
      <stop offset="100%" stop-color="#2F6BFF" stop-opacity="0"/></linearGradient></defs>
    <path d="${area}" fill="url(#sg)"/>
    <path d="${d}" fill="none" stroke="#2F6BFF" stroke-width="1.8"
      stroke-linecap="round" stroke-linejoin="round"/>
    ${pts.map(p=>`<circle cx="${sx(+p.date).toFixed(1)}" cy="${sy(p.value).toFixed(1)}" r="2.4"
      fill="#fff" stroke="#2F6BFF" stroke-width="1.6"/>`).join('')}
  </svg>`;
}
const esc=s=>String(s==null?'':s).replace(/[&<>"]/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[m]));
const tm=d=>d?new Date(d).toLocaleDateString('en',{day:'2-digit',month:'short',timeZone:'UTC'}):'';

export function cardHTML(n,selected){
  const sel=selected===n.id?' sel':'';
  if(n.kind==='image'){
    return `<div class="imgcard${sel}" style="width:${n.w}px;height:${n.h}px" data-id="${n.id}">
      <canvas data-modality="${n.modality}" data-key="${n.id}" width="${n.w}" height="${n.h}"></canvas>
      <div class="tm">${esc(tm(n.date))}</div>
      <button class="cbtn sm go" title="Open study">
        <svg viewBox="0 0 18 18" fill="none" stroke="currentColor" stroke-width="1.8"
         stroke-linecap="round"><path d="M6 12 12 6M7.5 6H12v4.5"/></svg></button>
      <div class="ov"><div class="big">${esc(n.title)}</div>
        <div class="cap">${esc(n.sub)}</div></div>
      <span class="simtag">SIM</span></div>`;
  }
  if(n.kind==='spark'){
    const s=n.series, last=s.points[s.points.length-1], first=s.points[0];
    return `<div class="sparkcard${sel}" style="width:${n.w}px" data-id="${n.id}">
      <div class="hd"><div class="ic">${icon(n.cat)}</div>
        <div><div class="t1">${esc(n.title)}</div><div class="t2">${esc(n.unit||'')}</div></div>
        <div class="vals"><div class="v1">${esc(E.fmt(last.value))}</div>
          <div class="v2">${esc(E.fmt(first.value))}</div></div></div>
      ${sparkSVG(s,n.w-26)}</div>`;
  }
  if(n.kind==='flat'){
    return `<div class="chip flat${sel}" style="min-width:${n.w}px" data-id="${n.id}">
      <div class="tx"><div class="t1">${esc(n.title)}</div>
        <div class="t2">${esc(n.sub)}</div></div>
      <span class="tm">${esc(tm(n.date))}</span></div>`;
  }
  const style=n.flagged?' flag':'';
  return `<div class="chip${style}${sel}" style="min-width:${n.w}px" data-id="${n.id}">
    <div class="ic" style="background:${n.flagged?'#F2545B':CAT_COLOR[n.cat]}">${icon(n.cat)}</div>
    <div class="tx"><div class="t1">${esc(n.title)}</div><div class="t2">${esc(n.sub)}</div></div>
    <span class="tm">${esc(tm(n.date))}</span></div>`;
}

/* ── render into the DOM ── */
export function render(container,svg,monthsEl,L,selected){
  svg.setAttribute('viewBox',`0 0 ${L.width} ${L.height}`);
  svg.setAttribute('width',L.width); svg.setAttribute('height',L.height);
  svg.innerHTML=`<line x1="0" y1="${L.spineY}" x2="${L.width}" y2="${L.spineY}"
      stroke="#E8EAEE" stroke-width="1.5"/>`+streams(L,selected);

  container.style.width=L.width+'px';
  container.style.height=L.height+'px';
  container.innerHTML=L.nodes.map(n=>
    `<div class="node" style="left:${n.x}px;top:${n.y}px">${cardHTML(n,selected)}</div>`).join('');

  monthsEl.style.width=L.width+'px';
  monthsEl.innerHTML=L.months.map(m=>
    `<div class="m" style="left:${m.x}px">
      ${m.year?`<span class="y">${m.year}</span> `:''}${esc(m.label)}</div>`).join('');

  // paint the imaging canvases now that they are in the document
  container.querySelectorAll('canvas[data-modality]').forEach(cv=>{
    const src=renderStudy(cv.dataset.modality,cv.dataset.key,
                          cv.width||150,cv.height||112);
    cv.getContext('2d').drawImage(src,0,0,cv.width,cv.height);
  });
}

export function minimap(cv,L,selected){
  const ctx=cv.getContext('2d');
  const W=cv.width=cv.clientWidth*2, H=cv.height=cv.clientHeight*2;
  ctx.clearRect(0,0,W,H);
  if(!L.nodes.length) return;
  const sx=W/L.width, sy=H/L.height;
  ctx.strokeStyle='rgba(255,255,255,.22)'; ctx.lineWidth=1.2;
  ctx.beginPath(); ctx.moveTo(0,L.spineY*sy); ctx.lineTo(W,L.spineY*sy); ctx.stroke();
  for(const n of L.nodes){
    ctx.fillStyle=n.id===selected?'#fff':(CAT_COLOR[n.cat]||'#2F6BFF');
    const w=Math.max(4,n.w*sx*0.8), h=Math.max(2.5,n.h*sy*0.7);
    ctx.globalAlpha=n.id===selected?1:.78;
    ctx.beginPath();
    ctx.roundRect(n.x*sx-w/2,n.y*sy-h/2,w,h,2);
    ctx.fill();
  }
  ctx.globalAlpha=1;
}
