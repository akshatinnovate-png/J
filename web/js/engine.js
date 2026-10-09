/* CAREGRAPH engine — faithful JS port of the Python package.
   Extraction keeps verbatim provenance; the verifier rejects any claim whose
   citations or numbers are not present in the source. */

/* ───────────────── units ───────────────── */
export const ANALYTES={
  hba1c:['HbA1c',['hba1c','hb a1c','glycated haemoglobin','glycated hemoglobin','a1c']],
  glucose_fasting:['Fasting glucose',['fasting glucose','fasting blood glucose','fbs','fasting plasma glucose']],
  glucose_random:['Random glucose',['random glucose','random blood sugar','rbs']],
  ldl:['LDL cholesterol',['ldl cholesterol','ldl-c','ldl']],
  hdl:['HDL cholesterol',['hdl cholesterol','hdl-c','hdl']],
  total_cholesterol:['Total cholesterol',['total cholesterol','cholesterol total','serum cholesterol']],
  triglycerides:['Triglycerides',['triglycerides','tg','serum triglycerides']],
  creatinine:['Creatinine',['creatinine','serum creatinine']],
  egfr:['eGFR',['egfr','estimated gfr']],
  haemoglobin:['Haemoglobin',['haemoglobin','hemoglobin','hb']],
  tsh:['TSH',['tsh','thyroid stimulating hormone']],
  vitamin_d:['Vitamin D',['vitamin d','25-oh vitamin d','25(oh)d']],
  alt:['ALT',['alt','sgpt','alanine aminotransferase']],
  weight:['Weight',['weight','body weight']],
  bmi:['BMI',['bmi','body mass index']],
  heart_rate:['Heart rate',['heart rate','pulse','hr']],
  spo2:['SpO2',['spo2','oxygen saturation','sao2']],
  bp_systolic:['Systolic BP',['systolic bp','systolic blood pressure','systolic']],
  bp_diastolic:['Diastolic BP',['diastolic bp','diastolic blood pressure','diastolic']],
};
const UNIT_ALIASES={'%':'%','percent':'%','mg/dl':'mg/dL','mmol/l':'mmol/L','g/dl':'g/dL',
  'g/l':'g/L','mmhg':'mmHg','kg':'kg','lb':'lb','lbs':'lb','miu/l':'mIU/L','uiu/ml':'mIU/L',
  'ng/ml':'ng/mL','nmol/l':'nmol/L','u/l':'U/L','iu/l':'U/L','umol/l':'umol/L','µmol/l':'umol/L',
  'ml/min/1.73m2':'mL/min/1.73m2','ml/min':'mL/min','kg/m2':'kg/m2','kg/m²':'kg/m2',
  'mmol/mol':'mmol/mol','bpm':'bpm'};
const CONVERSIONS={
  'glucose_fasting|mmol/L|mg/dL':18.016,'glucose_random|mmol/L|mg/dL':18.016,
  'ldl|mmol/L|mg/dL':38.67,'hdl|mmol/L|mg/dL':38.67,'total_cholesterol|mmol/L|mg/dL':38.67,
  'triglycerides|mmol/L|mg/dL':88.57,'creatinine|umol/L|mg/dL':1/88.4,'weight|lb|kg':0.45359237};
export const PREFERRED={glucose_fasting:'mg/dL',glucose_random:'mg/dL',ldl:'mg/dL',hdl:'mg/dL',
  total_cholesterol:'mg/dL',triglycerides:'mg/dL',creatinine:'mg/dL',weight:'kg'};
const NON_CONVERTIBLE=new Set(['hba1c|%|mmol/mol','hba1c|mmol/mol|%']);

export const display=k=>ANALYTES[k]?ANALYTES[k][0]:k;
export function canonUnit(u){
  if(!u) return null;
  const k=String(u).trim().toLowerCase().replace(/\s+/g,'');
  for(const [a,c] of Object.entries(UNIT_ALIASES)) if(a.replace(/\s+/g,'')===k) return c;
  return String(u).trim();
}
export function analyteKey(name){
  const n=String(name).trim().toLowerCase().replace(/^[:\-.\s]+|[:\-.\s]+$/g,'');
  let best=null;
  for(const [key,[,aliases]] of Object.entries(ANALYTES))
    for(const a of aliases)
      if(n===a||n.startsWith(a+' ')||n.endsWith(' '+a))
        if(!best||a.length>best[0]) best=[a.length,key];
  return best?best[1]:null;
}
export function convert(an,val,from,to){
  if(from===to) return val;
  if(NON_CONVERTIBLE.has(`${an}|${from}|${to}`)) return null;
  const f=CONVERSIONS[`${an}|${from}|${to}`]; if(f!=null) return val*f;
  const inv=CONVERSIONS[`${an}|${to}|${from}`]; if(inv) return val/inv;
  return null;
}
export const comparable=(a,u1,u2)=> u1===u2 ? true : (!u1||!u2) ? false : convert(a,1,u1,u2)!=null;

/* ───────────────── safety ───────────────── */
const INJECTION=[
  [/ignore\s+(all\s+)?(previous|prior|above)\s+instructions/i,'instruction override attempt'],
  [/disregard\s+(all\s+)?(previous|prior|the)\s+(instructions|rules|system)/i,'instruction override attempt'],
  [/you\s+are\s+now\s+(a|an)\s+/i,'role reassignment attempt'],
  [/system\s*prompt/i,'system-prompt reference'],
  [/<\/?\s*(system|assistant|instructions)\s*>/i,'fake role delimiter'],
  [/(print|output|reveal|repeat)\s+(your|the)\s+(prompt|instructions|api\s*key)/i,'exfiltration attempt'],
  [/do\s+not\s+(flag|report|mention)\s+/i,'suppression attempt'],
  [/\bdiagnose\s+the\s+patient\s+with\b/i,'model-directed clinical instruction'],
];
export function scanInjection(text){
  const out=[];
  for(const [re,label] of INJECTION) if(re.test(text)&&!out.includes(label)) out.push(label);
  return out;
}
export const DISCLAIMER='CAREGRAPH is an educational and administrative tool. It does not diagnose, '+
  'prescribe, or recommend treatment changes, and it does not replace the judgement of a qualified '+
  'healthcare professional.';

/* ───────────────── extraction ───────────────── */
const MONTHS={jan:1,feb:2,mar:3,apr:4,may:5,jun:6,jul:7,aug:8,sep:9,oct:10,nov:11,dec:12};
const DATE_LABEL=/(report|collection|collected|specimen|visit|consultation|sample|test|issued|date)\b[^\n]{0,30}?(\d{4}-\d{1,2}-\d{1,2}|\d{1,2}[/-]\d{1,2}[/-]\d{4}|\d{1,2}\s+[A-Za-z]{3,9}\s+\d{4}|[A-Za-z]{3,9}\s+\d{1,2},?\s+\d{4})/i;
const DOC_TYPES=[['discharge summary','Discharge Summary'],['laboratory report','Laboratory Report'],
  ['lab report','Laboratory Report'],['pathology report','Laboratory Report'],['blood test','Laboratory Report'],
  ['consultation note','Consultation Note'],['clinic note','Consultation Note'],['prescription','Prescription'],
  ['radiology report','Radiology Report'],['imaging report','Radiology Report'],['referral letter','Referral Letter']];

function iso(d){ return d? d.toISOString().slice(0,10):null; }
export function parseDate(raw){
  let m=raw.match(/\b(\d{4})-(\d{1,2})-(\d{1,2})\b/);
  if(m) return mk(+m[1],+m[2],+m[3]);
  m=raw.match(/\b(\d{1,2})[/-](\d{1,2})[/-](\d{4})\b/);
  if(m) return mk(+m[3],+m[2],+m[1]);
  m=raw.match(/\b(\d{1,2})\s+([A-Za-z]{3,9})\s+(\d{4})\b/);
  if(m){const mo=MONTHS[m[2].slice(0,3).toLowerCase()]; return mo?mk(+m[3],mo,+m[1]):null;}
  m=raw.match(/\b([A-Za-z]{3,9})\s+(\d{1,2}),?\s+(\d{4})\b/);
  if(m){const mo=MONTHS[m[1].slice(0,3).toLowerCase()]; return mo?mk(+m[3],mo,+m[2]):null;}
  return null;
}
function mk(y,mo,d){
  if(mo<1||mo>12||d<1||d>31) return null;
  const dt=new Date(Date.UTC(y,mo-1,d));
  return isNaN(dt)?null:dt;
}
function hash(...p){
  let h=2166136261;
  const s=p.join('|');
  for(let i=0;i<s.length;i++){h^=s.charCodeAt(i);h=Math.imul(h,16777619);}
  return (h>>>0).toString(36);
}

const IMAGING_PATTERNS=[
  [/\b(chest\s+)?(x[\s-]?ray|radiograph|cxr)\b/i,'xray_chest'],
  [/\b(mri|magnetic\s+resonance)\b/i,'mri_brain'],
  [/\b(ct|computed\s+tomography)\s*(scan)?\b/i,'ct_abdomen'],
  [/\b(ultrasound|usg|sonograph|echocardiogram|echo)\b/i,'ultrasound_cardiac'],
  [/\b(ecg|ekg|electrocardiogram)\b/i,'ecg'],
];
const BODY_PART=/\b(chest|brain|head|abdomen|abdominal|cardiac|heart|pelvis|spine|knee|shoulder|liver|kidney|thorax|neck|lumbar)\b/i;

const MEAS_RE=/^\s*([A-Za-z][A-Za-z0-9 \-()/']{1,45}?)\s*[:\-]?\s+(-?\d+(?:\.\d+)?)\s*([A-Za-zµ%][A-Za-z0-9µ%/.^²]*(?:\s?\/\s?[A-Za-z0-9.^²]+)*)?\s*(.*)$/;
const RANGE_RE=/(?:ref(?:erence)?(?:\s*range)?\s*[:=]?\s*)?[([]?\s*(-?\d+(?:\.\d+)?)\s*(?:-|–|to)\s*(-?\d+(?:\.\d+)?)\s*[)\]]?/;
const BP_RE=/\b(?:blood\s+pressure|bp)\b\s*[:\-]?\s*(\d{2,3})\s*\/\s*(\d{2,3})\s*(mmhg)?/i;
const MED_RE=/^\s*(?:rx|medication|med|drug)?\s*[:\-]?\s*([A-Z][A-Za-z\-]{2,30})\s+(\d+(?:\.\d+)?\s*(?:mg|mcg|g|ml|units?|iu))\b(.*)$/i;
const CONTEXTS={fasting:'fasting','post-prandial':'post-prandial',postprandial:'post-prandial',
  random:'random','non-fasting':'non-fasting',seated:'seated',standing:'standing'};
const STATEMENT_HINTS=[
  [/\ballerg(y|ic|ies)\b/i,'allergy'],
  [/\b(advised|advise|recommend(ed)?|instruct(ed)?|should|follow[- ]up|review in)\b/i,'instruction'],
  [/\b(diagnos(is|ed)|impression|history of|known case of|patient reports?|complains? of|denies)\b/i,'observation'],
];

export function ingest(filename,text,isSynthetic=false){
  text=text||'';
  const docId='d_'+hash(filename,text.length,text.slice(0,200));
  const doc={docId,filename,text,isSynthetic,injection:scanInjection(text),
             docType:null,docDate:null,dateExplicit:false,pageCount:1,extractionError:null};
  const low=text.toLowerCase();
  for(const [n,l] of DOC_TYPES) if(low.includes(n)){doc.docType=l;break;}
  const lm=text.match(DATE_LABEL);
  if(lm){const d=parseDate(lm[2]); if(d){doc.docDate=d;doc.dateExplicit=true;}}
  if(!doc.docDate){const d=parseDate(text.slice(0,600)); if(d)doc.docDate=d;}

  const measurements=[],statements=[],imaging=[];
  const lines=text.split('\n');
  let page=1,offset=0;
  lines.forEach((line,idx)=>{
    const lineNo=idx+1;
    if(line.includes('\f')) page+=(line.match(/\f/g)||[]).length;
    const s=line.trim(); const start=offset; offset+=line.length+1;
    if(!s||s.length>400) return;
    const banner=s===s.toUpperCase()&&s.split(/\s+/).length<=6;
    const prov={docId,page,line:lineNo,charStart:start,charEnd:start+line.length,raw:s};
    const lineDate=parseDate(s)||doc.docDate;
    let ctx=null;
    for(const [w,l] of Object.entries(CONTEXTS)) if(s.toLowerCase().includes(w)){ctx=l;break;}

    for(const [re,mod] of IMAGING_PATTERNS){
      if(!re.test(s)) continue;
      const bp=s.match(BODY_PART);
      let modality=mod, part=bp?bp[0].toLowerCase():null;
      if(modality==='ct_abdomen'&&(part==='chest'||part==='thorax')) modality='xray_chest';
      imaging.push({factId:'i_'+hash(docId,lineNo,modality),kind:'imaging',modality,
        printedName:s.slice(0,120),bodyPart:part,observedOn:lineDate,reportText:s,prov});
      break;
    }

    let matched=false;
    const bp=s.match(BP_RE);
    if(bp){
      [['bp_systolic',bp[1]],['bp_diastolic',bp[2]]].forEach(([k,v])=>{
        measurements.push({factId:'m_'+hash(docId,lineNo,k),kind:'measurement',analyte:k,
          displayName:display(k),value:+v,unit:canonUnit(bp[3])||'mmHg',
          refLow:null,refHigh:null,refText:null,observedOn:lineDate,context:ctx,prov});
      });
      matched=true;
    }
    if(!matched){
      const m=s.match(MEAS_RE);
      if(m){
        const key=analyteKey(m[1]);
        if(key){
          const unit=(m[3]&&!/^\d+$/.test(m[3]))?canonUnit(m[3]):null;
          const tail=m[4]||''; const r=tail.match(RANGE_RE);
          const val=parseFloat(m[2]);
          if(isFinite(val)){
            measurements.push({factId:'m_'+hash(docId,lineNo,key,m[2]),kind:'measurement',
              analyte:key,displayName:m[1].trim(),value:val,unit,
              refLow:r?+r[1]:null,refHigh:r?+r[2]:null,
              refText:r?r[0].trim().replace(/^[([\s]+|[)\]\s]+$/g,''):null,
              observedOn:lineDate,context:ctx,prov});
            matched=true;
          }
        }
      }
    }
    if(matched) return;

    const med=s.match(MED_RE);
    if(med&&s.length<160){
      statements.push({factId:'s_'+hash(docId,lineNo,'med'),kind:'statement',category:'medication',
        text:s,subject:med[1].toLowerCase(),observedOn:lineDate,prov});
      return;
    }
    if(banner) return;
    for(const [re,cat] of STATEMENT_HINTS){
      if(re.test(s)){
        statements.push({factId:'s_'+hash(docId,lineNo,cat),kind:'statement',category:cat,
          text:s,subject:null,observedOn:lineDate,prov});
        break;
      }
    }
  });
  return {doc,measurements,statements,imaging};
}

/* ───────────────── timeline ───────────────── */
export function buildSeries(c){
  const by={};
  for(const m of c.measurements) (by[m.analyte]=by[m.analyte]||[]).push(m);
  const out=[];
  for(const an of Object.keys(by).sort()){
    const items=by[an];
    const units=items.map(m=>m.unit).filter(Boolean);
    let target=PREFERRED[an];
    if(!target&&units.length){
      const cnt={}; units.forEach(u=>cnt[u]=(cnt[u]||0)+1);
      target=Object.keys(cnt).sort((a,b)=>cnt[b]-cnt[a])[0];
    }
    const contexts=new Set(items.map(m=>m.context).filter(Boolean));
    const series={analyte:an,label:display(an),unit:target||null,points:[],excluded:[]};
    for(const m of items){
      if(!m.observedOn){series.excluded.push([m,'no date is recorded for this measurement']);continue;}
      if(!m.unit){series.excluded.push([m,'no unit is printed, so the value cannot be placed on a scale']);continue;}
      const v=target?convert(an,m.value,m.unit,target):null;
      if(v==null){series.excluded.push([m,`unit '${m.unit}' has no safe conversion to '${target}' for ${display(an)}`]);continue;}
      if(contexts.size>1&&!m.context){
        series.excluded.push([m,'other readings specify a sampling context and this one does not, so it cannot be compared safely']);continue;
      }
      series.points.push({date:m.observedOn,value:Math.round(v*1e4)/1e4,originalValue:m.value,
        originalUnit:m.unit,converted:m.unit!==target,factId:m.factId,docId:m.prov.docId,
        raw:m.prov.raw,context:m.context,refLow:m.refLow,refHigh:m.refHigh});
    }
    series.points.sort((a,b)=>a.date-b.date);
    out.push(series);
  }
  return out;
}
export function changeSummary(s){
  if(s.points.length<2) return null;
  const a=s.points[0],b=s.points[s.points.length-1];
  const d=b.value-a.value;
  const dir=d>0?'increased':d<0?'decreased':'was unchanged';
  return `Recorded ${s.label} ${dir} from ${fmt(a.value)} to ${fmt(b.value)} ${s.unit||''} between ${iso(a.date)} and ${iso(b.date)}.`.replace(/\s+/g,' ');
}
export const fmt=v=>Number.isInteger(v)?String(v):String(Math.round(v*1000)/1000);

/* ───────────────── contradictions ───────────────── */
const SAME_DAY_TOL=0.05;
const NEGATION=/\b(no|denies|without|negative for|not|non[- ])\b/i;
function flagId(...p){return 'f_'+hash(...p);}
function docName(c,id){const d=c.documents.find(x=>x.docId===id);return d?d.filename:id;}
function lbl(c,f){return `${docName(c,f.prov.docId)} p${f.prov.page}`;}

export function runChecks(c){
  const flags=[],seen=new Set();
  const push=f=>{if(!seen.has(f.flagId)){seen.add(f.flagId);flags.push(f);}};
  const by={}; for(const m of c.measurements)(by[m.analyte]=by[m.analyte]||[]).push(m);

  for(const [an,items] of Object.entries(by)){
    const units=[...new Set(items.map(m=>m.unit).filter(Boolean))].sort();
    for(let i=0;i<units.length;i++)for(let j=i+1;j<units.length;j++){
      const ua=units[i],ub=units[j];
      const a=items.find(m=>m.unit===ua), b=items.find(m=>m.unit===ub);
      const conv=comparable(an,ua,ub);
      push({flagId:flagId('unit',an,ua,ub),kind:'unit_mismatch',severity:'formatting',
        title:`${display(an)} is recorded in two different units`,
        reason:`'${ua}' appears in ${lbl(c,a)} and '${ub}' in ${lbl(c,b)}. `+(conv
          ?'A standard conversion exists, so CAREGRAPH plots both in one unit and shows the original value on hover.'
          :`No single agreed conversion factor exists between these units for ${display(an)}, so these readings are NOT plotted together.`),
        needs:conv?'Confirm with the issuing laboratory which unit each result was reported in.'
                  :'Ask the clinician to restate both results in the same unit before comparing them.',
        evidence:[a.factId,b.factId]});
    }
  }
  const buckets={};
  for(const m of c.measurements){ if(!m.observedOn) continue;
    const k=m.analyte+'|'+iso(m.observedOn); (buckets[k]=buckets[k]||[]).push(m); }
  for(const [k,items] of Object.entries(buckets)){
    if(items.length<2) continue;
    const an=k.split('|')[0], date=k.split('|')[1];
    for(let i=0;i<items.length;i++)for(let j=i+1;j<items.length;j++){
      const a=items[i],b=items[j];
      if(!a.unit||!b.unit) continue;
      const bc=convert(an,b.value,b.unit,a.unit); if(bc==null) continue;
      if((a.context||null)!==(b.context||null)) continue;
      const den=Math.max(Math.abs(a.value),Math.abs(bc),1e-9);
      if(Math.abs(a.value-bc)/den<=SAME_DAY_TOL) continue;
      push({flagId:flagId('sameday',an,date,a.factId,b.factId),kind:'value_conflict',severity:'possible',
        title:`Two different ${display(an)} values recorded for ${date}`,
        reason:`${lbl(c,a)} records ${fmt(a.value)} ${a.unit||''} and ${lbl(c,b)} records ${fmt(b.value)} ${b.unit||''} for the same date. CAREGRAPH cannot determine which record is correct.`,
        needs:'Ask which result corresponds to this date; one document may carry a transcription error or a different collection time.',
        evidence:[a.factId,b.factId]});
    }
  }
  for(const [an,items] of Object.entries(by)){
    const ctxs=new Set(items.map(m=>m.context||null));
    if(ctxs.size>1&&ctxs.has(null)&&items.length>1){
      const un=items.filter(m=>!m.context), la=items.filter(m=>m.context);
      if(un.length&&la.length)
        push({flagId:flagId('ctx',an),kind:'incomparable_context',severity:'formatting',
          title:`${display(an)} readings have inconsistent sampling context`,
          reason:`${lbl(c,la[0])} states a '${la[0].context}' sample, while ${lbl(c,un[0])} states no sampling context. These are not necessarily the same quantity, so the unlabelled reading is excluded from the chart.`,
          needs:'Ask whether the unlabelled sample was taken under the same conditions.',
          evidence:[la[0].factId,un[0].factId]});
    }
    const wr=items.filter(m=>m.refLow!=null), wo=items.filter(m=>m.refLow==null);
    if(wr.length&&wo.length)
      push({flagId:flagId('range',an),kind:'missing_reference_range',severity:'formatting',
        title:`${display(an)} is missing a reference range in at least one document`,
        reason:`${lbl(c,wr[0])} prints a reference range (${wr[0].refText}), but ${lbl(c,wo[0])} prints none. Reference ranges differ between laboratories, so a value without one cannot be judged normal or abnormal from this record.`,
        needs:"Request the issuing laboratory's reference range for this result.",
        evidence:[wr[0].factId,wo[0].factId]});
  }
  for(const d of c.documents){
    if(!d.text.trim()) continue;
    if(!d.docDate)
      push({flagId:flagId('nodate',d.docId),kind:'missing_date',severity:'formatting',
        title:`No date could be read from ${d.filename}`,
        reason:'No collection, report or visit date was found in this document, so its contents cannot be positioned on the timeline.',
        needs:'Confirm the date this document was issued.',evidence:[]});
    else if(!d.dateExplicit)
      push({flagId:flagId('impdate',d.docId),kind:'date_conflict',severity:'formatting',
        title:`Date for ${d.filename} is unlabelled`,
        reason:`CAREGRAPH read ${iso(d.docDate)} from the top of this document, but it is not labelled as a collection or report date.`,
        needs:'Confirm what this date refers to.',evidence:[]});
  }
  const meds={};
  for(const s of c.statements) if(s.category==='medication'&&s.subject)(meds[s.subject]=meds[s.subject]||[]).push(s);
  for(const [sub,items] of Object.entries(meds)){
    const aff=items.filter(s=>!NEGATION.test(s.text)), neg=items.filter(s=>NEGATION.test(s.text));
    if(aff.length&&neg.length)
      push({flagId:flagId('stmt',sub),kind:'statement_conflict',severity:'possible',
        title:`Conflicting records about ${title(sub)}`,
        reason:`One document records '${aff[0].text}' while another records '${neg[0].text}'. These cannot both describe the current state.`,
        needs:'Confirm the current medication list with the prescriber.',
        evidence:[aff[0].factId,neg[0].factId]});
    const doses={};
    for(const s of items){
      const m=s.text.match(/(\d+(?:\.\d+)?)\s*(mg|mcg|g|ml|units?|iu)\b/i);
      if(m)(doses[m[1]+m[2].toLowerCase()]=doses[m[1]+m[2].toLowerCase()]||[]).push(s);
    }
    const keys=Object.keys(doses).sort();
    if(keys.length>1){
      const a=doses[keys[0]][0], b=doses[keys[1]][0];
      if(a.prov.docId!==b.prov.docId)
        push({flagId:flagId('dose',sub),kind:'value_conflict',severity:'possible',
          title:`${title(sub)} appears at two different strengths`,
          reason:`${lbl(c,a)} records '${a.text}' and ${lbl(c,b)} records '${b.text}'. This may be an intended change over time or a transcription error; the documents alone do not say which.`,
          needs:'Confirm the current dose and when it was changed.',evidence:[a.factId,b.factId]});
    }
  }
  const ord={possible:0,formatting:1};
  flags.sort((a,b)=>ord[a.severity]-ord[b.severity]||a.kind.localeCompare(b.kind));
  return flags;
}
const title=s=>s.replace(/\b\w/g,m=>m.toUpperCase());

/* ───────────────── claims, gaps, questions ───────────────── */
function cid(...p){return 'c_'+hash(...p);}
export function buildClaims(c){
  const claims=[];
  for(const s of buildSeries(c)){
    if(s.points.length>=2){
      const sum=changeSummary(s);
      if(sum) claims.push({claimId:cid('trend',s.analyte),text:sum,
        evidence:s.points.map(p=>p.factId),generator:'deterministic',
        caveat:'This describes the recorded numbers only. What the change means clinically is for a healthcare professional to assess.'});
    }
    for(const [m,reason] of s.excluded)
      claims.push({claimId:cid('excl',m.factId),
        text:`${display(s.analyte)} of ${fmt(m.value)} ${m.unit||'(no unit)'} is held out of the chart because ${reason}.`,
        evidence:[m.factId],generator:'deterministic',caveat:null});
  }
  for(const m of c.measurements){
    if(m.refLow==null||m.refHigh==null) continue;
    const inside=m.value>=m.refLow&&m.value<=m.refHigh;
    claims.push({claimId:cid('range',m.factId),
      text:`${m.displayName} of ${fmt(m.value)} ${m.unit||''} is ${inside?'within':'outside'} the reference range of ${fmt(m.refLow)}-${fmt(m.refHigh)} printed in this document.`.replace(/\s+/g,' '),
      evidence:[m.factId],generator:'deterministic',
      caveat:'Compared against the range printed on this report only. Reference ranges differ between laboratories.'});
  }
  return claims;
}
export function buildGaps(c){
  const gaps=[];
  const undated=c.documents.filter(d=>!d.docDate&&d.text.trim());
  if(undated.length) gaps.push({gapId:'g_undated',label:'Documents without a readable date',
    detail:`${undated.length} document(s) carry no date CAREGRAPH could read, so their contents cannot be placed in sequence.`,
    docs:undated.map(d=>d.docId)});
  const noRange=[...new Set(c.measurements.filter(m=>m.refLow==null).map(m=>m.analyte))].sort();
  if(noRange.length) gaps.push({gapId:'g_noranges',label:'Results with no reference range',
    detail:'No reference range is printed for: '+noRange.map(display).join(', ')+'. Without it, these values cannot be judged normal or abnormal from the record.',
    docs:[...new Set(c.measurements.filter(m=>m.refLow==null).map(m=>m.prov.docId))]});
  const present=new Set(c.measurements.map(m=>m.analyte));
  for(const an of ['glucose_fasting','ldl']){
    if(!present.has(an)) continue;
    const items=c.measurements.filter(m=>m.analyte===an);
    if(items.every(m=>!m.context)) gaps.push({gapId:'g_ctx_'+an,
      label:`${display(an)}: sampling context not stated`,
      detail:'The record does not state whether the sample was taken fasting.',
      docs:[...new Set(items.map(m=>m.prov.docId))]});
  }
  const singles=[...present].filter(a=>c.measurements.filter(m=>m.analyte===a).length===1);
  if(singles.length) gaps.push({gapId:'g_single',label:'Measured once only',
    detail:'Only one reading exists for: '+singles.map(display).sort().join(', ')+'. No change over time can be described for these.',docs:[]});
  if(!c.statements.length) gaps.push({gapId:'g_nostatements',label:'No medications or instructions found',
    detail:'No medication lines, instructions or recorded observations were extracted. The uploaded documents may be results-only.',docs:[]});
  return gaps;
}
export function buildQuestions(c){
  const qs=[],seen=new Set();
  const add=q=>{if(!seen.has(q.questionId)){seen.add(q.questionId);qs.push(q);}};
  for(const f of c.flags) add({questionId:'q_'+hash('flag',f.flagId),text:f.needs,
    priority:f.severity==='possible'?1:3,evidence:f.evidence,rationale:'Raised by: '+f.title});
  for(const m of c.measurements){
    if(m.refLow==null||m.refHigh==null) continue;
    if(m.value>=m.refLow&&m.value<=m.refHigh) continue;
    add({questionId:'q_'+hash('out',m.factId),
      text:`My ${m.displayName} was ${fmt(m.value)} ${m.unit||''}, outside the ${fmt(m.refLow)}-${fmt(m.refHigh)} range printed on the report. What does that mean for me, and does it need repeating?`.replace(/\s+/g,' '),
      priority:2,evidence:[m.factId],rationale:'A recorded value sits outside the range printed on its own report.'});
  }
  for(const s of buildSeries(c)){
    if(s.points.length<2) continue;
    const a=s.points[0],b=s.points[s.points.length-1];
    if(Math.abs(b.value-a.value)<1e-9) continue;
    add({questionId:'q_'+hash('trend',s.analyte),
      text:`My recorded ${s.label} moved from ${fmt(a.value)} to ${fmt(b.value)} ${s.unit||''}. Is that change expected, and should anything be monitored?`.replace(/\s+/g,' '),
      priority:2,evidence:s.points.map(p=>p.factId),rationale:'A value changed between documents.'});
  }
  for(const g of c.gaps) if(['g_noranges','g_undated'].includes(g.gapId))
    add({questionId:'q_'+hash('gap',g.gapId),text:`Could you supply the missing detail: ${g.label.toLowerCase()}?`,
      priority:3,evidence:[],rationale:g.detail});
  qs.sort((a,b)=>a.priority-b.priority||a.text.localeCompare(b.text));
  return qs;
}

/* ───────────────── verifier ───────────────── */
const numbersIn=t=>new Set((String(t).match(/-?\d+(?:\.\d+)?/g)||[]).map(x=>String(parseFloat(x))));
export function factIds(c){
  return new Set([...c.measurements,...c.statements,...c.imaging].map(f=>f.factId));
}
export function getFact(c,id){
  return [...c.measurements,...c.statements,...c.imaging].find(f=>f.factId===id)||null;
}
export function verifyClaim(c,claim){
  const known=factIds(c);
  const cited=[...new Set(claim.evidence||[])];
  const resolved=cited.filter(i=>known.has(i));
  const dangling=cited.filter(i=>!known.has(i));
  claim.rejected=dangling;
  if(claim.generalEducation){
    claim.status='insufficient_information';
    claim.caveat='General educational information, not drawn from your documents.';
    claim.evidence=resolved; return claim;
  }
  if(!cited.length){claim.status='unverified';
    claim.caveat='This statement cites no source and is shown as unverified.';return claim;}
  if(dangling.length){
    claim.evidence=resolved;
    claim.status=resolved.length?'partially_supported':'unverified';
    claim.caveat=`${dangling.length} cited source reference(s) do not exist in the uploaded documents and were rejected.`;
    if(!resolved.length) return claim;
  }
  const claimNums=numbersIn(claim.text);
  const srcNums=new Set();
  for(const id of resolved){
    const f=getFact(c,id); if(!f) continue;
    numbersIn(f.prov.raw).forEach(n=>srcNums.add(n));
    if(f.value!=null) srcNums.add(String(f.value));
  }
  const unsupported=[...claimNums].filter(n=>!srcNums.has(n));
  const conflicting=c.flags.some(f=>f.severity==='possible'&&f.evidence.some(e=>resolved.includes(e)));
  if(conflicting){
    claim.status='conflicting_evidence';
    claim.caveat=((claim.caveat||'')+' The cited records are themselves flagged as potentially conflicting.').trim();
  }else if(unsupported.length){
    claim.status='partially_supported';
    claim.caveat=`The value(s) ${unsupported.sort().join(', ')} in this statement were not found verbatim in the cited source.`;
  }else if(claim.status!=='partially_supported'){
    claim.status='supported';
    claim.caveat=claim.caveat||'The wording above is traceable to the cited source text. This confirms the record, not that any clinical interpretation of it is correct.';
  }
  return claim;
}

/* ───────────────── pipeline ───────────────── */
export function emptyCase(){
  return {documents:[],measurements:[],statements:[],imaging:[],claims:[],flags:[],gaps:[],questions:[]};
}
export function analyse(c){
  c.flags=runChecks(c);
  c.claims=buildClaims(c);
  c.gaps=buildGaps(c);
  c.questions=buildQuestions(c);
  c.claims=c.claims.map(cl=>verifyClaim(c,cl));
  return c;
}
export function addDocument(c,filename,text,isSynthetic=false){
  const {doc,measurements,statements,imaging}=ingest(filename,text,isSynthetic);
  if(c.documents.some(d=>d.docId===doc.docId)) return {case:c,added:false};
  c.documents.push(doc);
  c.measurements.push(...measurements);
  c.statements.push(...statements);
  c.imaging.push(...imaging);
  return {case:analyse(c),added:true};
}
export function integrity(c){
  const byStatus={};
  for(const cl of c.claims) byStatus[cl.status]=(byStatus[cl.status]||0)+1;
  return {documents:c.documents.length,facts:factIds(c).size,claims:c.claims.length,
    flags:c.flags.length,questions:c.questions.length,imaging:c.imaging.length,
    rejected:c.claims.reduce((n,cl)=>n+(cl.rejected?cl.rejected.length:0),0),byStatus};
}
export function careTeam(c){
  const CL=/(?:dr\.?|doctor|prof\.?)\s+([A-Z][A-Za-z.\-]{1,20}(?:\s+[A-Z][A-Za-z\-]{1,20}){0,2})/gi;
  const RO=/\b(patholog(?:y|ist)|radiolog(?:y|ist)|cardiolog(?:y|ist)|endocrinolog(?:y|ist)|neurolog(?:y|ist)|physician|surgeon|consultant|nephrolog(?:y|ist))\b/i;
  const found={};
  for(const d of c.documents) for(const line of d.text.split('\n')){
    let m; CL.lastIndex=0;
    while((m=CL.exec(line))){
      const name=m[1].trim().replace(/[,.]$/,''); if(name.length<2) continue;
      const r=line.match(RO);
      const e=found[name]=found[name]||{name:'Dr. '+name,role:null,docs:new Set()};
      e.docs.add(d.docId);
      if(r&&!e.role) e.role=title(r[0].toLowerCase());
    }
  }
  return Object.values(found).map(e=>({name:e.name,role:e.role||'Clinician',documents:e.docs.size,
    initials:e.name.replace('Dr. ','').split(/\s+/).slice(0,2).map(p=>p[0]).join('').toUpperCase()}))
    .sort((a,b)=>b.documents-a.documents||a.name.localeCompare(b.name));
}
export function facilities(c){
  const found={};
  for(const d of c.documents){
    const head=(d.text.split('\n').find(l=>l.trim())||'').split('-')[0].trim();
    if(head.length>3&&head.length<48){
      const t=title(head.toLowerCase()); found[t]=(found[t]||0)+1;
    }
  }
  return Object.entries(found).map(([name,documents])=>({name,documents,
    initials:name.split(/\s+/).slice(0,2).map(p=>p[0]).join('').toUpperCase()}))
    .sort((a,b)=>b.documents-a.documents);
}
export function brief(c){
  const L=['# Appointment preparation brief',''];
  if(c.documents.some(d=>d.isSynthetic)) L.push('> **SIMULATED DATA.** Built from synthetic demo records.','');
  L.push('## Documents reviewed','');
  for(const d of c.documents) L.push(`- ${d.filename} — ${d.docType||'Untyped'}, ${d.docDate?iso(d.docDate):'date not recorded'}`);
  const sup=c.claims.filter(x=>x.status==='supported');
  if(sup.length){L.push('','## What the records say','');
    sup.slice(0,12).forEach(x=>L.push(`- ${x.text}`));}
  const unres=c.flags.filter(f=>f.severity==='possible');
  L.push('','## Unresolved inconsistencies','');
  if(unres.length) unres.forEach(f=>L.push(`- **${f.title}** — ${f.reason}\n  _Needs clarification: ${f.needs}_`));
  else L.push('- None that could be justified from these documents.');
  if(c.gaps.length){L.push('','## Missing information','');
    c.gaps.forEach(g=>L.push(`- **${g.label}** — ${g.detail}`));}
  L.push('','## Questions to ask','');
  c.questions.slice(0,12).forEach(q=>L.push(`- [${{1:'High',2:'Medium',3:'Low'}[q.priority]||'Low'}] ${q.text}`));
  L.push('','---','',DISCLAIMER);
  return L.join('\n');
}
export {iso};
