/* SVG charts: the faceted measurement timeline and the layered evidence graph.
   Both are built from extracted data only - no synthetic points, no smoothing
   between readings, and nothing plotted that the engine held out. */

import * as E from './engine.js';

const C={blue:'#2F6BFF',teal:'#0FA3A3',violet:'#7C5CFF',amber:'#D97706',
         rose:'#E11D48',green:'#059669',ink:'#10131A',muted:'#64748B',
         faint:'#B4B9C4',line:'#EDEEF1',canvas:'#FFFFFF'};
const SERIES=[C.blue,C.amber,C.teal,C.violet,'#DB2777','#65A30D','#0EA5E9','#F97316'];
const esc=s=>String(s==null?'':s).replace(/[&<>"]/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[m]));
const d2=n=>Math.round(n*100)/100;

/* ───────────────────── faceted timeline ───────────────────── */
export function timelineSVG(seriesList,width){
  const shown=seriesList.filter(s=>s.points.length);
  if(!shown.length) return '';
  const W=Math.max(width,520), rowH=132, padL=62, padR=26, padT=26, padB=34;
  const H=shown.length*rowH+18;
  const t0=Math.min(...shown.flatMap(s=>s.points.map(p=>+p.date)));
  const t1=Math.max(...shown.flatMap(s=>s.points.map(p=>+p.date)));
  const span=Math.max(t1-t0,1);
  const sx=t=>padL+((t-t0)/span)*(W-padL-padR);

  let out=`<svg viewBox="0 0 ${W} ${H}" width="100%" height="${H}" font-family="Inter,sans-serif">`;

  shown.forEach((s,i)=>{
    const top=i*rowH+padT, h=rowH-padT-padB;
    const vals=s.points.map(p=>p.value);
    const lows=s.points.filter(p=>p.refLow!=null).map(p=>p.refLow);
    const highs=s.points.filter(p=>p.refHigh!=null).map(p=>p.refHigh);
    let lo=Math.min(...vals,...(lows.length?[Math.min(...lows)]:[]));
    let hi=Math.max(...vals,...(highs.length?[Math.max(...highs)]:[]));
    if(hi-lo<1e-9){hi=lo+1;lo=lo-1;}
    const pad=(hi-lo)*0.16; lo-=pad; hi+=pad;
    const sy=v=>top+h-((v-lo)/(hi-lo))*h;
    const col=SERIES[i%SERIES.length];

    out+=`<text x="${padL}" y="${top-9}" font-size="12.5" font-weight="650" fill="${C.ink}">`+
         `${esc(s.label)} <tspan fill="${C.muted}" font-weight="500">${esc(s.unit||'no unit')}</tspan></text>`;

    // reference band, drawn only where the source printed one
    if(lows.length&&highs.length){
      const y1=sy(Math.max(...highs)), y2=sy(Math.min(...lows));
      out+=`<rect x="${padL}" y="${y1}" width="${W-padL-padR}" height="${Math.max(y2-y1,1)}"
             fill="${C.green}" opacity=".07"/>`
         +`<text x="${padL+6}" y="${y1+11}" font-size="9" fill="${C.green}" opacity=".75">reference range printed in source</text>`;
    }
    // axes
    out+=`<line x1="${padL}" y1="${top+h}" x2="${W-padR}" y2="${top+h}" stroke="${C.line}"/>`;
    [lo+(hi-lo)*0.0,lo+(hi-lo)*0.5,hi].forEach(v=>{
      out+=`<line x1="${padL}" y1="${sy(v)}" x2="${W-padR}" y2="${sy(v)}" stroke="${C.line}" stroke-dasharray="2 4"/>`
        +`<text x="${padL-8}" y="${sy(v)+3.5}" font-size="9.5" fill="${C.faint}" text-anchor="end">${d2(v)}</text>`;
    });

    const line=s.points.map((p,k)=>`${k?'L':'M'} ${d2(sx(+p.date))} ${d2(sy(p.value))}`).join(' ');
    out+=`<path d="${line}" fill="none" stroke="${col}" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/>`;
    s.points.forEach(p=>{
      const x=sx(+p.date), y=sy(p.value);
      const title=`${s.label} ${E.fmt(p.value)} ${s.unit||''}\n${E.iso(p.date)}\n`+
        `printed in source: ${E.fmt(p.originalValue)} ${p.originalUnit||''}`+
        (p.converted?' (converted)':' (as printed)')+
        `\ncontext: ${p.context||'not stated'}\n${p.raw}`;
      // a converted reading is marked so the chart never hides a unit change
      out+=p.converted
        ? `<rect x="${d2(x-5)}" y="${d2(y-5)}" width="10" height="10" transform="rotate(45 ${d2(x)} ${d2(y)})"
            fill="#fff" stroke="${col}" stroke-width="2.2"><title>${esc(title)}</title></rect>`
        : `<circle cx="${d2(x)}" cy="${d2(y)}" r="4.6" fill="#fff" stroke="${col}" stroke-width="2.2">
            <title>${esc(title)}</title></circle>`;
    });
    // date ticks on the last facet only
    if(i===shown.length-1){
      const seen=new Set();
      shown.flatMap(x=>x.points).forEach(p=>{
        const t=+p.date; if(seen.has(t))return; seen.add(t);
        out+=`<text x="${d2(sx(t))}" y="${top+h+17}" font-size="9.5" fill="${C.faint}" text-anchor="middle">`+
             `${new Date(t).toLocaleDateString('en',{day:'2-digit',month:'short',timeZone:'UTC'})}</text>`;
      });
    }
  });
  return out+'</svg>';
}

/* ───────────────────── evidence graph ───────────────────── */
const STATUS_COLOR={supported:C.green,partially_supported:C.amber,
  conflicting_evidence:C.rose,unverified:C.faint,insufficient_information:C.violet};

export function buildGraph(c,kinds){
  const want=new Set(kinds);
  const nodes=[],edges=[],seen=new Set();
  const add=(id,kind,label,extra={})=>{
    if(seen.has(id)||!want.has(kind))return; seen.add(id);
    nodes.push({id,kind,label,...extra});
  };
  for(const d of c.documents) add(d.docId,'document',d.filename,{detail:`${d.docType||'Untyped'} · ${E.iso(d.docDate)||'no date'}`});
  for(const m of c.measurements){
    add(m.factId,'fact',`${m.displayName} ${E.fmt(m.value)} ${m.unit||''}`.trim(),{detail:m.prov.raw});
    edges.push({s:m.prov.docId,t:m.factId,rel:'contains'});
  }
  for(const st of c.statements){
    add(st.factId,'fact',st.text.slice(0,52),{detail:st.prov.raw});
    edges.push({s:st.prov.docId,t:st.factId,rel:'contains'});
  }
  for(const r of c.imaging){
    add(r.factId,'fact',r.printedName.slice(0,52),{detail:r.prov.raw});
    edges.push({s:r.prov.docId,t:r.factId,rel:'contains'});
  }
  for(const cl of c.claims){
    add(cl.claimId,'claim',cl.text.slice(0,58),{detail:cl.text,status:cl.status,caveat:cl.caveat});
    cl.evidence.forEach(f=>edges.push({s:cl.claimId,t:f,rel:'supported_by'}));
  }
  for(const f of c.flags){
    add(f.flagId,'flag',f.title,{detail:f.reason,severity:f.severity});
    f.evidence.forEach(e=>edges.push({s:f.flagId,t:e,rel:'flags'}));
  }
  for(const q of c.questions){
    add(q.questionId,'question',q.text.slice(0,58),{detail:q.rationale});
    q.evidence.forEach(e=>edges.push({s:q.questionId,t:e,rel:'asks'}));
  }
  const ids=new Set(nodes.map(n=>n.id));
  return {nodes,edges:edges.filter(e=>ids.has(e.s)&&ids.has(e.t))};
}

export function graphSVG(g,width,focus){
  const {nodes,edges}=g;
  if(!nodes.length) return '';
  // layered: documents -> facts -> claims & flags -> questions
  const COL={document:0,fact:1,claim:2,flag:2,question:3};
  const byCol={};
  nodes.forEach(n=>{const c=COL[n.kind]??2;(byCol[c]=byCol[c]||[]).push(n);});
  const cols=Object.keys(byCol).map(Number).sort((a,b)=>a-b);

  const rowH=26, padT=52, padB=30;
  const tallest=Math.max(...cols.map(c=>byCol[c].length));
  const H=Math.max(380,padT+padB+tallest*rowH);
  const W=Math.max(width,560);
  const colX=c=>{
    const n=cols.length;
    return 132+(cols.indexOf(c)/(Math.max(n-1,1)))*(W-264);
  };
  const pos={};
  const place=()=>cols.forEach(c=>{
    const items=byCol[c];
    const h=H-padT-padB, step=items.length>1?h/(items.length-1):0;
    items.forEach((n,i)=>pos[n.id]=[colX(c),items.length>1?padT+i*step:H/2]);
  });
  place();
  // two barycentre sweeps pull connected nodes level with each other
  const adj={};
  edges.forEach(e=>{(adj[e.s]=adj[e.s]||[]).push(e.t);(adj[e.t]=adj[e.t]||[]).push(e.s);});
  for(let pass=0;pass<2;pass++){
    cols.forEach(c=>{
      byCol[c].sort((a,b)=>bary(a)-bary(b));
      place();
    });
  }
  function bary(n){
    const ys=(adj[n.id]||[]).map(m=>pos[m]&&pos[m][1]).filter(v=>v!=null);
    return ys.length?ys.reduce((a,b)=>a+b,0)/ys.length:(pos[n.id]?pos[n.id][1]:0);
  }

  const near=new Set();
  if(focus){near.add(focus);edges.forEach(e=>{if(e.s===focus)near.add(e.t);if(e.t===focus)near.add(e.s);});}

  let out=`<svg viewBox="0 0 ${W} ${H}" width="100%" height="${H}" font-family="Inter,sans-serif">`;
  ['DOCUMENTS','EXTRACTED FACTS','CLAIMS & FLAGS','QUESTIONS'].forEach((t,i)=>{
    if(!cols.includes(i))return;
    out+=`<text x="${colX(i)}" y="22" font-size="9.5" font-weight="650" fill="${C.faint}"
           letter-spacing="1" text-anchor="middle">${t}</text>`;
  });
  const relCol={contains:C.line,supported_by:C.green,flags:C.rose,asks:C.violet};
  for(const e of edges){
    const ra=pos[e.s],rb=pos[e.t]; if(!ra||!rb)continue;
    const dim=focus&&!(near.has(e.s)&&near.has(e.t));
    // A claim sits to the right of the fact it cites, so that edge runs right to
    // left. Drawing it in stored order inverts the control points and the curve
    // loops back on itself, so always draw from the leftmost endpoint.
    const [a,b]=ra[0]<=rb[0]?[ra,rb]:[rb,ra];
    const dx=Math.max(Math.abs(b[0]-a[0])*0.42,28);
    out+=`<path d="M ${d2(a[0])} ${d2(a[1])} C ${d2(a[0]+dx)} ${d2(a[1])}, ${d2(b[0]-dx)} ${d2(b[1])}, ${d2(b[0])} ${d2(b[1])}"
           fill="none" stroke="${relCol[e.rel]||C.line}" stroke-width="${e.rel==='contains'?1:1.5}"
           opacity="${dim?0.05:(e.rel==='contains'?0.32:0.46)}"/>`;
  }
  const shape={document:'square',fact:'circle',claim:'diamond',flag:'triangle',question:'star'};
  for(const n of nodes){
    const [x,y]=pos[n.id]; const dim=focus&&!near.has(n.id);
    const col=n.kind==='claim'?(STATUS_COLOR[n.status]||C.muted)
      :n.kind==='flag'?(n.severity==='possible'?C.rose:C.amber)
      :n.kind==='document'?C.blue:n.kind==='question'?C.violet:C.teal;
    const r=n.kind==='document'?7:n.kind==='fact'?4.4:6;
    const title=`${n.label}\n${n.detail||''}`;
    const mark=shape[n.kind]==='square'
      ? `<rect x="${d2(x-r)}" y="${d2(y-r)}" width="${r*2}" height="${r*2}" rx="2" fill="${col}"/>`
      : shape[n.kind]==='diamond'
      ? `<rect x="${d2(x-r)}" y="${d2(y-r)}" width="${r*2}" height="${r*2}" fill="${col}" transform="rotate(45 ${d2(x)} ${d2(y)})"/>`
      : shape[n.kind]==='triangle'
      ? `<polygon points="${d2(x)},${d2(y-r)} ${d2(x+r)},${d2(y+r)} ${d2(x-r)},${d2(y+r)}" fill="${col}"/>`
      : `<circle cx="${d2(x)}" cy="${d2(y)}" r="${r}" fill="${col}"/>`;
    out+=`<g class="gnode" data-id="${esc(n.id)}" opacity="${dim?0.18:1}" style="cursor:pointer">
            ${mark}<title>${esc(title)}</title>
            <circle cx="${d2(x)}" cy="${d2(y)}" r="11" fill="transparent"/></g>`;
    // label documents, and whatever is focused
    if(n.kind==='document'||n.id===focus)
      out+=`<text x="${d2(x)}" y="${d2(y-13)}" font-size="10" fill="${C.ink}" text-anchor="middle">${esc(n.label.slice(0,26))}</text>`;
  }
  return out+'</svg>';
}
