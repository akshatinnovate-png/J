/* CAREGRAPH — app wiring. */
import * as E from './engine.js';
import * as F from './flow.js';
import {SAMPLES} from './samples.js';
import {renderStudy,MODALITIES,SHORT} from './imaging.js';

const $=s=>document.querySelector(s);
const $$=s=>[...document.querySelectorAll(s)];
const esc=s=>String(s==null?'':s).replace(/[&<>"]/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[m]));
const iso=d=>d?new Date(d).toISOString().slice(0,10):'';

const S={ case:E.emptyCase(), view:'flow', cats:F.CATEGORIES.slice(),
          selected:null, zoom:1, layout:null, query:'' };

/* ───────── toast ───────── */
let toastT;
function toast(msg){
  const t=$('#toast'); t.textContent=msg; t.classList.add('on');
  clearTimeout(toastT); toastT=setTimeout(()=>t.classList.remove('on'),2600);
}

/* ───────── rail ───────── */
function renderRail(){
  const c=S.case, rail=$('#rail');
  if(!c.documents.length){ rail.innerHTML=''; return; }
  const series=E.buildSeries(c).filter(s=>s.points.length>=2);
  const head=series.sort((a,b)=>b.points.length-a.points.length)[0];
  const team=E.careTeam(c), fac=E.facilities(c);
  const i=E.integrity(c);
  const possible=c.flags.filter(f=>f.severity==='possible').length;

  let hero='';
  if(head){
    const f=head.points[0], l=head.points[head.points.length-1];
    const dir=l.value>f.value?'rising':l.value<f.value?'falling':'flat';
    hero=`<div class="hero">
      <button class="cbtn sm x" title="Most-tracked measure">
        <svg viewBox="0 0 18 18" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round"><path d="M5 5l8 8M13 5l-8 8"/></svg></button>
      <div class="lbl">Most-tracked measure</div>
      <div class="ttl">${esc(head.label)}</div>
      <div class="sub">${head.points.length} readings · ${dir} · ${E.fmt(f.value)} → ${E.fmt(l.value)} ${esc(head.unit||'')}</div>
      <button class="cbtn blue plus" title="Open timeline" data-open="trend">
        <svg viewBox="0 0 18 18" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round"><path d="M9 4.5v9M4.5 9h9"/></svg></button>
    </div>`;
  }

  const stat=(v,k,cls='')=>`<div class="prow"><div class="av ${cls}">${v}</div>
    <div><div class="nm">${k}</div><div class="ro">in this record set</div></div></div>`;

  rail.innerHTML=hero+`
    <div class="railttl">Record summary</div>
    <div class="plist">
      ${stat(i.documents,'Documents')}
      ${stat(i.facts,'Extracted facts')}
      ${stat(i.imaging,'Imaging studies')}
      ${possible?`<div class="prow" style="border-color:rgba(242,84,91,.35)">
        <div class="av" style="background:rgba(242,84,91,.12);color:#F2545B">${possible}</div>
        <div><div class="nm">Possible conflicts</div><div class="ro">need human review</div></div></div>`:''}
    </div>
    ${team.length?`<div class="railttl">Clinicians named</div><div class="plist">`+
      team.map(p=>`<div class="prow"><div class="av">${esc(p.initials)}</div>
        <div><div class="nm">${esc(p.name)}</div><div class="ro">${esc(p.role)}</div></div>
        <div class="ct">${p.documents}</div></div>`).join('')+`</div>`:''}
    ${fac.length?`<div class="railttl">Issuing sources</div><div class="plist">`+
      fac.map((f,idx)=>`<div class="prow${idx===0?' sel':''}">
        <div class="av">${esc(f.initials)}</div>
        <div><div class="nm">${esc(f.name)}</div><div class="ro">Issuing source</div>
        ${idx===0?'<div class="dots"><i></i><i></i><i></i></div>':''}</div>
        <div class="ct">${f.documents}</div></div>`).join('')+`</div>`:''}`;
}

/* ───────── flow canvas ───────── */
function matches(n){
  if(!S.query) return true;
  const q=S.query.toLowerCase();
  return (n.title+' '+n.sub+' '+(n.detail||'')).toLowerCase().includes(q);
}
function renderFlow(){
  const wrap=$('#scroller');
  let nodes=F.buildNodes(S.case,S.cats).filter(matches);
  const W=wrap.clientWidth/S.zoom, H=wrap.clientHeight/S.zoom;
  const L=F.layout(nodes,W,H);
  S.layout=L;
  const cv=$('#canvas');
  cv.style.transform=`scale(${S.zoom})`;
  cv.style.transformOrigin='0 0';
  F.render($('#nodes'),$('#streams'),$('#months'),L,S.selected);
  F.minimap($('#mmcanvas'),L,S.selected);
  $('#zoom-level').textContent=Math.round(S.zoom*100)+'%';
  if(!nodes.length){
    $('#nodes').innerHTML=`<div class="empty" style="position:absolute;left:50%;top:44%;
      transform:translate(-50%,-50%);width:430px">
      <h3>${S.case.documents.length?'Nothing matches':'No records loaded'}</h3>
      <p>${S.case.documents.length
        ? 'Adjust the filters or clear the search to see events again.'
        : 'Load the demo records, upload a PDF, or add a record by hand.'}</p></div>`;
  }
}

/* ───────── inspector ───────── */
function openDrawer(id){
  const c=S.case;
  const node=(S.layout?.nodes||[]).find(n=>n.id===id);
  const fact=E.getFact(c,id);
  const doc=c.documents.find(d=>d.docId===id);
  S.selected=id;

  let kicker='Record', titleTxt='—', body='';
  if(doc){
    kicker='Document'; titleTxt=doc.filename;
    const imgs=c.imaging.filter(r=>r.prov.docId===doc.docId);
    body=`<div>${doc.dateExplicit?'<span class="badge ok">labelled date</span>'
        :doc.docDate?'<span class="badge warn">date unlabelled</span>'
        :'<span class="badge bad">no date</span>'}
      <span class="badge neutral">${esc(doc.docType||'untyped')}</span></div>
      <div class="dsec"><h4>Extracted from this document</h4>
        <p style="font-size:13px;color:#2A3040">
        ${c.measurements.filter(m=>m.prov.docId===doc.docId).length} measurements ·
        ${c.statements.filter(s=>s.prov.docId===doc.docId).length} statements ·
        ${imgs.length} imaging</p></div>
      ${doc.injection.length?`<div class="dsec"><h4>Safety</h4>
        <div class="card bad"><p>Model-directed text found: ${esc(doc.injection.join(', '))}.
        It was treated as data, not as instructions.</p></div></div>`:''}
      <div class="dsec"><h4>Source text</h4><div class="src">${esc(doc.text.slice(0,4000))}</div></div>`;
  }else if(fact){
    const d=c.documents.find(x=>x.docId===fact.prov.docId);
    kicker=fact.kind==='imaging'?'Imaging study':fact.kind==='measurement'?'Measurement':'Statement';
    titleTxt=node?node.title:(fact.displayName||fact.text||'Record');
    const claims=c.claims.filter(cl=>cl.evidence.includes(id));
    const flags=c.flags.filter(f=>f.evidence.includes(id));
    body=`
      ${fact.kind==='imaging'?`<div class="dsec">
        <canvas id="drawer-scan" width="340" height="300"
          style="width:100%;border-radius:14px;display:block"></canvas>
        <div style="margin-top:8px"><span class="badge bad">Simulated illustration</span></div>
        <p style="font-size:12px;color:#8A909E;margin-top:7px;line-height:1.5">
        CAREGRAPH receives no pixel data. This is drawn procedurally so the record has
        something to show, and must not be read clinically.</p></div>`:''}
      <div class="dsec"><h4>Source</h4>
        <div class="srcmeta">${esc(d?d.filename:'?')} · page ${fact.prov.page}, line ${fact.prov.line}</div>
        <div class="src">${esc(fact.prov.raw)}</div></div>
      ${flags.length?`<div class="dsec"><h4>Flagged</h4>`+flags.map(f=>
        `<div class="card ${f.severity==='possible'?'bad':'warn'}">
          <h3>${esc(f.title)}</h3><p>${esc(f.reason)}</p>
          <div class="meta"><b>Needs clarification:</b> ${esc(f.needs)}</div></div>`).join('')+`</div>`:''}
      ${claims.length?`<div class="dsec"><h4>Claims citing this</h4>`+claims.map(cl=>
        `<div class="card"><p>${esc(cl.text)}</p>
          <div class="meta"><span class="badge ${badgeFor(cl.status)}">${esc(statusLabel(cl.status))}</span></div>
        </div>`).join('')+`</div>`:''}`;
  }
  $('#dk').textContent=kicker;
  $('#dt').textContent=titleTxt;
  $('#db').innerHTML=body;
  $('#drawer').classList.add('open');
  if(fact&&fact.kind==='imaging'){
    const cv=$('#drawer-scan');
    if(cv) cv.getContext('2d').drawImage(renderStudy(fact.modality,fact.factId,340,300),0,0);
  }
  renderFlow();
}
function closeDrawer(){ $('#drawer').classList.remove('open'); S.selected=null; renderFlow(); }

const statusLabel=s=>({supported:'Supported by source',partially_supported:'Partially supported',
  unverified:'Unverified',conflicting_evidence:'Conflicting evidence',
  insufficient_information:'Insufficient information'}[s]||s);
const badgeFor=s=>({supported:'ok',partially_supported:'warn',conflicting_evidence:'bad',
  unverified:'neutral',insufficient_information:'info'}[s]||'neutral');

/* ───────── panels ───────── */
function renderPanels(){
  const c=S.case, i=E.integrity(c);
  const empty=t=>`<div class="empty"><h3>${t}</h3><p>Load records to populate this view.</p></div>`;

  /* imaging */
  $('#view-imaging').innerHTML=`
    <div class="panelhd"><h2>Imaging</h2>
      <p>Every image here is generated, not acquired. CAREGRAPH receives no pixel data —
      when a document names a study it renders an illustration of that modality, drawn
      procedurally and watermarked in the pixels.</p></div>
    ${!c.imaging.length?empty('No imaging study named in these records'):
    `<div class="grid g3">`+c.imaging.map(r=>{
      const d=c.documents.find(x=>x.docId===r.prov.docId);
      return `<div class="card" style="padding:0;overflow:hidden">
        <canvas class="scan" data-modality="${r.modality}" data-key="${r.factId}"
          width="300" height="260" style="width:100%;display:block;cursor:pointer"
          data-open="${r.factId}"></canvas>
        <div style="padding:13px 15px 15px">
          <h3>${esc(MODALITIES[r.modality]||r.modality)}</h3>
          <div class="meta">${esc(iso(r.observedOn)||'no date')} · ${esc(d?d.filename:'?')} line ${r.prov.line}</div>
          <div class="src" style="margin-top:9px">${esc(r.reportText||'')}</div>
          <div style="margin-top:9px"><span class="badge bad">Simulated illustration</span></div>
        </div></div>`;
    }).join('')+`</div>`}`;

  /* contradictions */
  $('#view-contradictions').innerHTML=`
    <div class="panelhd"><h2>Contradiction radar</h2>
      <p>Cross-document inconsistencies, each showing both source passages and what a
      human needs to clarify. CAREGRAPH never decides which record is correct.</p></div>
    ${!c.flags.length?empty('No inconsistency could be justified from these documents'):
    c.flags.map(f=>{
      const pair=f.evidence.slice(0,2).map(id=>{
        const fact=E.getFact(c,id); if(!fact) return '';
        const d=c.documents.find(x=>x.docId===fact.prov.docId);
        return `<div><div class="srcmeta">${esc(d?d.filename:'?')} · page ${fact.prov.page}, line ${fact.prov.line}</div>
          <div class="src">${esc(fact.prov.raw)}</div></div>`;
      }).join('');
      return `<div class="card ${f.severity==='possible'?'bad':'warn'}" style="margin-bottom:13px">
        <span class="badge ${f.severity==='possible'?'bad':'warn'}">
          ${f.severity==='possible'?'possible factual contradiction':'confirmed formatting inconsistency'}</span>
        <h3 style="margin-top:9px">${esc(f.title)}</h3><p>${esc(f.reason)}</p>
        <div class="meta"><b>Needs human clarification:</b> ${esc(f.needs)}</div>
        ${pair?`<div class="grid g2" style="margin-top:12px">${pair}</div>`:''}</div>`;
    }).join('')}`;

  /* evidence */
  const order=['supported','partially_supported','conflicting_evidence','unverified','insufficient_information'];
  const total=c.claims.length||1;
  $('#view-evidence').innerHTML=`
    <div class="panelhd"><h2>Evidence</h2>
      <p>A claim shows as supported only when every citation resolves to a real extracted
      fact and every number it asserts appears in that fact's source text.</p></div>
    <div class="stats">
      <div class="stat"><div class="v">${i.facts}</div><div class="k">extracted facts</div></div>
      <div class="stat"><div class="v">${i.claims}</div><div class="k">generated claims</div></div>
      <div class="stat"><div class="v">${i.rejected}</div><div class="k">refs rejected</div></div>
      <div class="stat"><div class="v">${i.flags}</div><div class="k">flags raised</div></div>
    </div>
    <div class="card" style="margin-bottom:16px">
      <h3>Evidence status</h3>
      <div style="display:flex;height:11px;border-radius:99px;overflow:hidden;margin:11px 0 9px;background:#F0F1F4">
        ${order.map(s=>{const n=i.byStatus[s]||0; if(!n) return '';
          const col={supported:'#15A66A',partially_supported:'#E8A23A',conflicting_evidence:'#F2545B',
                     unverified:'#B4B9C4',insufficient_information:'#7C5CFF'}[s];
          return `<div style="width:${n/total*100}%;background:${col}" title="${statusLabel(s)}: ${n}"></div>`;
        }).join('')}
      </div>
      <div style="display:flex;flex-wrap:wrap;gap:9px">
        ${order.filter(s=>i.byStatus[s]).map(s=>
          `<span class="badge ${badgeFor(s)}">${statusLabel(s)} · ${i.byStatus[s]}</span>`).join('')}
      </div>
      <div class="meta" style="margin-top:11px">${i.rejected
        ? `${i.rejected} source reference(s) pointed at facts that do not exist and were rejected.`
        : 'Every source reference in every claim resolves to a real extracted fact.'}</div>
    </div>
    <div class="grid g2">${c.claims.map(cl=>
      `<div class="card"><span class="badge ${badgeFor(cl.status)}">${statusLabel(cl.status)}</span>
        <p style="margin-top:9px">${esc(cl.text)}</p>
        ${cl.caveat?`<div class="meta">⚠ ${esc(cl.caveat)}</div>`:''}
        <div class="meta">Evidence: ${cl.evidence.length?esc(cl.evidence.join(', ')):'none'}</div>
      </div>`).join('')||empty('No claims generated yet')}</div>`;

  /* gaps */
  $('#view-gaps').innerHTML=`
    <div class="panelhd"><h2>Missing information</h2>
      <p>What the records document, what they leave uncertain, and what is simply absent.
      CAREGRAPH reports absence; it never fills it in.</p></div>
    ${!c.gaps.length?empty('No information gaps detected'):
    `<div class="grid g2">`+c.gaps.map(g=>
      `<div class="card warn"><h3>${esc(g.label)}</h3><p>${esc(g.detail)}</p>
       ${g.docs.length?`<div class="meta">Affects: ${g.docs.map(id=>{
         const d=c.documents.find(x=>x.docId===id); return esc(d?d.filename:'');
       }).filter(Boolean).join(', ')}</div>`:''}</div>`).join('')+`</div>`}`;

  /* brief */
  const md=E.brief(c);
  $('#view-brief').innerHTML=`
    <div class="panelhd"><h2>Appointment brief</h2>
      <p>Prioritised questions, each anchored to real evidence, plus a shareable summary.</p></div>
    <div style="display:flex;gap:9px;margin-bottom:16px">
      <button class="cbtn dark" id="dl-brief" style="width:auto;border-radius:99px;padding:0 17px;height:38px;gap:8px">
        <svg viewBox="0 0 18 18" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" style="width:15px;height:15px">
          <path d="M9 3v9M5.5 8.5 9 12l3.5-3.5M3 15h12"/></svg>
        <span style="font-size:13px;font-weight:550">Download brief</span></button>
    </div>
    <div class="grid g2">${c.questions.slice(0,14).map(q=>
      `<div class="card"><span class="badge ${q.priority===1?'bad':q.priority===2?'warn':'info'}">
        ${{1:'High',2:'Medium',3:'Low'}[q.priority]||'Low'}</span>
       <h3 style="margin-top:9px">${esc(q.text)}</h3>
       <div class="meta">${esc(q.rationale)}</div></div>`).join('')||empty('No questions yet')}</div>
    <div class="card" style="margin-top:16px"><h3>Brief preview</h3>
      <div class="src" style="margin-top:9px;max-height:360px;overflow:auto">${esc(md)}</div></div>`;
  const dl=$('#dl-brief');
  if(dl) dl.onclick=()=>{
    const b=new Blob([md],{type:'text/markdown'});
    const a=document.createElement('a');
    a.href=URL.createObjectURL(b); a.download=`caregraph-brief-${iso(new Date())}.md`; a.click();
    toast('Brief downloaded');
  };

  /* add record */
  renderAdd();

  /* paint panel scans */
  $$('canvas.scan').forEach(cv=>{
    cv.getContext('2d').drawImage(
      renderStudy(cv.dataset.modality,cv.dataset.key,cv.width,cv.height),0,0);
  });
  $$('canvas.scan[data-open]').forEach(cv=>{
    cv.onclick=()=>{ setView('flow'); openDrawer(cv.dataset.open); };
  });
}

function renderAdd(){
  const analytes=Object.keys(E.ANALYTES).filter(k=>!k.startsWith('bp_'));
  $('#view-add').innerHTML=`
    <div class="panelhd"><h2>Add a record</h2>
      <p>Typed entries are composed into a document and run through the same extractor as
      an upload, so they are verified on identical terms.</p></div>
    <div class="grid g2" style="align-items:start">
      <div class="card">
        <h3>Record details</h3>
        <div style="display:grid;gap:10px;margin-top:11px">
          <label style="font-size:12px;color:#8A909E">Document type
            <input id="a-title" value="Laboratory Report" style="width:100%;margin-top:4px;padding:9px 11px;border:1px solid #E3E5EA;border-radius:10px;font-size:13px"></label>
          <label style="font-size:12px;color:#8A909E">Date
            <input id="a-date" type="date" value="${iso(new Date())}" style="width:100%;margin-top:4px;padding:9px 11px;border:1px solid #E3E5EA;border-radius:10px;font-size:13px"></label>
          <label style="font-size:12px;color:#8A909E">Measurement
            <div style="display:flex;gap:7px;margin-top:4px">
              <select id="a-analyte" style="flex:2;padding:9px 11px;border:1px solid #E3E5EA;border-radius:10px;font-size:13px">
                ${analytes.map(k=>`<option value="${k}">${esc(E.display(k))}</option>`).join('')}</select>
              <input id="a-value" type="number" step="0.1" value="7.2" style="flex:1;padding:9px 11px;border:1px solid #E3E5EA;border-radius:10px;font-size:13px">
              <input id="a-unit" value="%" style="flex:1;padding:9px 11px;border:1px solid #E3E5EA;border-radius:10px;font-size:13px">
            </div></label>
          <label style="font-size:12px;color:#8A909E">Reference range (optional)
            <div style="display:flex;gap:7px;margin-top:4px">
              <input id="a-lo" type="number" step="0.1" placeholder="low" style="flex:1;padding:9px 11px;border:1px solid #E3E5EA;border-radius:10px;font-size:13px">
              <input id="a-hi" type="number" step="0.1" placeholder="high" style="flex:1;padding:9px 11px;border:1px solid #E3E5EA;border-radius:10px;font-size:13px">
            </div></label>
          <label style="font-size:12px;color:#8A909E">Imaging study
            <div style="display:flex;gap:7px;margin-top:4px">
              <select id="a-mod" style="flex:2;padding:9px 11px;border:1px solid #E3E5EA;border-radius:10px;font-size:13px">
                <option value="">none</option>
                ${Object.keys(MODALITIES).map(k=>`<option value="${k}">${esc(MODALITIES[k])}</option>`).join('')}</select>
              <input id="a-finding" placeholder="reported finding" style="flex:2;padding:9px 11px;border:1px solid #E3E5EA;border-radius:10px;font-size:13px">
            </div></label>
          <label style="font-size:12px;color:#8A909E">Additional lines
            <textarea id="a-extra" rows="4" placeholder="Metformin 500 mg twice daily&#10;Blood pressure 138/86 mmHg&#10;Advised to repeat in three months"
              style="width:100%;margin-top:4px;padding:9px 11px;border:1px solid #E3E5EA;border-radius:10px;font-size:13px;font-family:'SF Mono',monospace;resize:vertical"></textarea></label>
        </div>
        <button class="cbtn dark" id="a-submit" style="width:100%;border-radius:12px;height:42px;margin-top:13px;gap:8px">
          <span style="font-size:13.5px;font-weight:560">Add record to case</span></button>
      </div>
      <div class="card">
        <h3>What will be parsed</h3>
        <div class="src" id="a-preview" style="margin-top:11px;min-height:150px"></div>
        <div class="stats" style="margin-top:13px;margin-bottom:0" id="a-counts"></div>
      </div>
    </div>`;

  const build=()=>{
    const t=$('#a-title').value||'Record';
    const d=$('#a-date').value||iso(new Date());
    const lines=[];
    const an=$('#a-analyte').value, v=$('#a-value').value, u=$('#a-unit').value;
    if(v!==''){
      const lo=$('#a-lo').value, hi=$('#a-hi').value;
      lines.push(`${E.display(an)} ${v} ${u}`+((lo!==''&&hi!=='')?` (ref ${lo}-${hi})`:''));
    }
    const mod=$('#a-mod').value;
    if(mod){
      const noun={xray_chest:'Chest X-ray',mri_brain:'MRI',ct_abdomen:'CT',
                  ultrasound_cardiac:'Ultrasound',ecg:'ECG'}[mod]||mod;
      lines.push(`${noun}: ${$('#a-finding').value||'reported'}`);
    }
    lines.push(...$('#a-extra').value.split('\n').filter(l=>l.trim()));
    return {text:`${t.toUpperCase()}\nCollection date: ${d}\n\n${lines.join('\n')}\n`,date:d};
  };
  const refresh=()=>{
    const {text}=build();
    $('#a-preview').textContent=text;
    const r=E.ingest('preview.txt',text);
    $('#a-counts').innerHTML=`
      <div class="stat"><div class="v">${r.measurements.length}</div><div class="k">measurements</div></div>
      <div class="stat"><div class="v">${r.statements.length}</div><div class="k">statements</div></div>
      <div class="stat"><div class="v">${r.imaging.length}</div><div class="k">imaging</div></div>`;
  };
  ['a-title','a-date','a-analyte','a-value','a-unit','a-lo','a-hi','a-mod','a-finding','a-extra']
    .forEach(id=>{const el=$('#'+id); if(el){el.oninput=refresh; el.onchange=refresh;}});
  refresh();

  $('#a-submit').onclick=()=>{
    const {text,date}=build();
    const r=E.addDocument(S.case,`typed-${date}-${S.case.documents.length+1}.txt`,text,true);
    if(!r.added){ toast('That record is already loaded'); return; }
    S.case=r.case; refreshAll();
    toast('Record added and the case re-analysed');
    setView('flow');
  };
}

/* ───────── ingest ───────── */
async function readPDF(file){
  const pdfjs=window.pdfjsLib;
  if(!pdfjs) throw new Error('PDF reader unavailable offline — paste the text instead');
  const buf=await file.arrayBuffer();
  pdfjs.GlobalWorkerOptions.workerSrc=
    'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.worker.min.js';
  const pdf=await pdfjs.getDocument({data:buf}).promise;
  const pages=[];
  for(let p=1;p<=pdf.numPages;p++){
    const page=await pdf.getPage(p);
    const tc=await page.getTextContent();
    // group items into visual lines by their y position
    const rows=new Map();
    for(const it of tc.items){
      const y=Math.round(it.transform[5]);
      if(!rows.has(y)) rows.set(y,[]);
      rows.get(y).push(it);
    }
    const lines=[...rows.entries()].sort((a,b)=>b[0]-a[0])
      .map(([,items])=>items.sort((a,b)=>a.transform[4]-b.transform[4])
        .map(i=>i.str).join(' ').replace(/\s+/g,' ').trim())
      .filter(Boolean);
    pages.push(lines.join('\n'));
  }
  return pages.join('\n\f\n');
}
async function handleFiles(files){
  $('#loader').classList.add('on');
  let added=0, failed=[];
  for(const f of files){
    try{
      const text=f.name.toLowerCase().endsWith('.pdf')?await readPDF(f):await f.text();
      if(!text.trim()){ failed.push(f.name+' (no selectable text — scanned PDF?)'); continue; }
      const r=E.addDocument(S.case,f.name,text,false);
      if(r.added){ S.case=r.case; added++; }
    }catch(err){ failed.push(f.name+' ('+(err.message||'unreadable')+')'); }
  }
  $('#loader').classList.remove('on');
  refreshAll();
  if(added) toast(`Added ${added} document${added>1?'s':''}`);
  if(failed.length) toast('Could not read: '+failed.join('; '));
}
function loadDemo(){
  $('#loader').classList.add('on');
  setTimeout(()=>{
    S.case=E.emptyCase();
    for(const s of SAMPLES){
      const r=E.addDocument(S.case,s.name,s.text,true);
      S.case=r.case;
    }
    $('#loader').classList.remove('on');
    refreshAll();
    toast('Demo records loaded and analysed');
  },40);
}

/* ───────── views ───────── */
function setView(v){
  S.view=v;
  $$('#nav .pill').forEach(p=>p.classList.toggle('on',p.dataset.view===v));
  $$('.panel').forEach(p=>p.classList.toggle('on',p.id==='view-'+v));
  if(v==='flow') renderFlow();
}
function refreshAll(){ renderRail(); renderFlow(); renderPanels(); }

/* ───────── events ───────── */
$('#nav').onclick=e=>{ const b=e.target.closest('.pill'); if(b) setView(b.dataset.view); };
$('#btn-demo').onclick=loadDemo;
$('#btn-upload').onclick=()=>$('#file').click();
$('#file').onchange=e=>{ handleFiles([...e.target.files]); e.target.value=''; };
$('#btn-reset').onclick=()=>{ S.case=E.emptyCase(); S.selected=null; closeDrawer(); refreshAll(); toast('Session cleared'); };
$('#drawer-close').onclick=closeDrawer;

$('#nodes').onclick=e=>{
  const card=e.target.closest('[data-id]');
  if(card) openDrawer(card.dataset.id);
};
$('#search').oninput=e=>{ S.query=e.target.value.trim(); renderFlow(); };

$$('.tools .cbtn').forEach(b=>b.onclick=()=>{
  const f=b.dataset.filter;
  S.cats=f==='all'?F.CATEGORIES.slice():[f,'Docs'];
  renderFlow();
  toast(f==='all'?'Showing all events':`Filtered to ${f}`);
});
$('#zoom-in').onclick=()=>{ S.zoom=Math.min(1.6,S.zoom+0.15); renderFlow(); };
$('#zoom-out').onclick=()=>{ S.zoom=Math.max(0.5,S.zoom-0.15); renderFlow(); };
$('#btn-fit').onclick=()=>{ S.zoom=1; $('#scroller').scrollTo({left:0,behavior:'smooth'}); renderFlow(); };

let rT; window.addEventListener('resize',()=>{ clearTimeout(rT); rT=setTimeout(renderFlow,160); });
document.addEventListener('keydown',e=>{ if(e.key==='Escape') closeDrawer(); });

/* boot */
refreshAll();
loadDemo();
