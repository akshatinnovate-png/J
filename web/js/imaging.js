/* Procedurally generated synthetic medical imaging, drawn on canvas.
   Nothing here is a real patient study. Every image is synthesised from a
   deterministic seed and watermarked SIMULATED in the pixels. */

export const MODALITIES = {
  xray_chest:        'X-ray · Chest PA',
  mri_brain:         'MRI · Brain axial T2',
  ultrasound_cardiac:'Ultrasound · Cardiac 4-chamber',
  ct_abdomen:        'CT · Abdomen axial',
  ecg:               'ECG · Rhythm strip',
};

export const SHORT = {
  xray_chest:'Chest X-ray', mri_brain:'MRI', ultrasound_cardiac:'Ultrasound',
  ct_abdomen:'CT', ecg:'ECG',
};

/* deterministic PRNG so a record always renders the same study */
function mulberry(seed){
  return function(){
    seed|=0; seed=seed+0x6D2B79F5|0;
    let t=Math.imul(seed^seed>>>15,1|seed);
    t=t+Math.imul(t^t>>>7,61|t)^t;
    return ((t^t>>>14)>>>0)/4294967296;
  };
}
export function seedFrom(str){
  let h=2166136261;
  for(let i=0;i<str.length;i++){h^=str.charCodeAt(i);h=Math.imul(h,16777619);}
  return h>>>0;
}
function gauss(rnd){
  let u=0,v=0;
  while(!u)u=rnd(); while(!v)v=rnd();
  return Math.sqrt(-2*Math.log(u))*Math.cos(2*Math.PI*v);
}

/* ── field helpers: we build a density field, then render it ── */
function field(w,h){ return new Float32Array(w*h); }

function ellipse(f,w,h,cx,cy,rx,ry,rot,feather,amp){
  const ca=Math.cos(rot),sa=Math.sin(rot);
  const x0=Math.max(0,Math.floor(cx-rx*1.9)),x1=Math.min(w,Math.ceil(cx+rx*1.9));
  const y0=Math.max(0,Math.floor(cy-ry*1.9)),y1=Math.min(h,Math.ceil(cy+ry*1.9));
  for(let y=y0;y<y1;y++){
    for(let x=x0;x<x1;x++){
      let dx=x-cx, dy=y-cy;
      const rxx=dx*ca+dy*sa, ryy=-dx*sa+dy*ca;
      const d=Math.sqrt((rxx/rx)**2+(ryy/ry)**2);
      let v;
      if(feather<=0) v = d<=1?1:0;
      else v = Math.min(1,Math.max(0,(1-d)/feather+1));
      if(v>0) f[y*w+x]+=v*amp;
    }
  }
}
function ellipseMask(w,h,cx,cy,rx,ry,rot,feather){
  const m=field(w,h); ellipse(m,w,h,cx,cy,rx,ry,rot,feather,1); return m;
}
function annulus(w,h,cx,cy,rx,ry,th,rot,feather){
  const o=ellipseMask(w,h,cx,cy,rx,ry,rot,feather);
  const i=ellipseMask(w,h,Math.max(rx-th,1)&&cx,cy,Math.max(rx-th,1),Math.max(ry-th,1),rot,feather);
  for(let k=0;k<o.length;k++) o[k]=Math.max(0,Math.min(1,o[k]-i[k]));
  return o;
}
/* separable box blur, repeated => near-gaussian */
function blur(f,w,h,r,passes=3){
  if(r<=0) return f;
  let src=f, tmp=new Float32Array(f.length);
  const R=Math.max(1,Math.round(r));
  for(let p=0;p<passes;p++){
    for(let y=0;y<h;y++){
      let acc=0; const row=y*w;
      for(let x=-R;x<=R;x++) acc+=src[row+Math.min(w-1,Math.max(0,x))];
      for(let x=0;x<w;x++){
        tmp[row+x]=acc/(2*R+1);
        acc-=src[row+Math.min(w-1,Math.max(0,x-R))];
        acc+=src[row+Math.min(w-1,Math.max(0,x+R+1))];
      }
    }
    for(let x=0;x<w;x++){
      let acc=0;
      for(let y=-R;y<=R;y++) acc+=tmp[Math.min(h-1,Math.max(0,y))*w+x];
      for(let y=0;y<h;y++){
        src[y*w+x]=acc/(2*R+1);
        acc-=tmp[Math.min(h-1,Math.max(0,y-R))*w+x];
        acc+=tmp[Math.min(h-1,Math.max(0,y+R+1))*w+x];
      }
    }
  }
  return src;
}
function grain(w,h,rnd,scale){
  const coarse=field(w,h);
  for(let i=0;i<coarse.length;i++) coarse[i]=gauss(rnd);
  blur(coarse,w,h,Math.max(2,w*0.02),2);
  const out=field(w,h);
  for(let i=0;i<out.length;i++) out[i]=(coarse[i]*5.2*0.65+gauss(rnd)*0.35)*scale;
  return out;
}
function vignette(f,w,h,strength){
  for(let y=0;y<h;y++)for(let x=0;x<w;x++){
    const dx=(x-w/2)/(w/2), dy=(y-h/2)/(h/2);
    const r=Math.sqrt(dx*dx+dy*dy);
    f[y*w+x]*=Math.max(0,1-strength*Math.max(0,r-0.45)**1.6);
  }
}
function strokeField(w,h,blurR,drawFn){
  const c=document.createElement('canvas'); c.width=w; c.height=h;
  const g=c.getContext('2d'); g.clearRect(0,0,w,h);
  drawFn(g);
  const d=g.getImageData(0,0,w,h).data, f=field(w,h);
  for(let i=0;i<f.length;i++) f[i]=d[i*4]*(d[i*4+3]/255);
  return blur(f,w,h,blurR,2);
}

/* ── chest X-ray ── */
function chestXray(w,h,rnd){
  const f=field(w,h);
  for(let i=0;i<f.length;i++) f[i]=6;
  const body=ellipseMask(w,h,w*.5,h*.55,w*.405,h*.475,0,.09);
  const shou=ellipseMask(w,h,w*.5,h*.185,w*.455,h*.175,0,.28);
  const soft=field(w,h);
  for(let i=0;i<f.length;i++){soft[i]=Math.min(1,body[i]+shou[i]*.9); f[i]+=soft[i]*74;}

  const lungL=ellipseMask(w,h,w*.337,h*.495,w*.152,h*.272,.09,.20);
  const lungR=ellipseMask(w,h,w*.663,h*.495,w*.152,h*.272,-.09,.20);
  const heart=ellipseMask(w,h,w*.455,h*.585,w*.150,h*.185,.26,.30);
  const lungs=field(w,h);
  for(let i=0;i<f.length;i++){
    lungs[i]=Math.min(1,lungL[i]+lungR[i])*(1-heart[i]*.85);
    f[i]*=(1-lungs[i]*.82);
  }
  // pulmonary vasculature
  const vasc=strokeField(w,h,1.3,g=>{
    g.lineCap='round';
    for(const side of [-1,1]){
      const hx=w*(.5+side*.075), hy=h*.49;
      for(let k=0;k<22;k++){
        let ang=Math.PI/2+(rnd()*2.3-1.15), x=hx,y=hy;
        const bright=120+rnd()*95, wd=2.6+rnd()*1.8, n=5+Math.floor(rnd()*8);
        for(let s=0;s<n;s++){
          ang+=gauss(rnd)*.26;
          const nx=x+Math.cos(ang)*7*side, ny=y+Math.sin(ang)*7;
          g.strokeStyle=`rgb(${Math.round(bright*(1-s/(n+2)))},0,0)`;
          g.lineWidth=Math.max(1,wd*(1-s/n));
          g.beginPath(); g.moveTo(x,y); g.lineTo(nx,ny); g.stroke();
          x=nx;y=ny;
        }
      }
    }
  });
  for(let i=0;i<f.length;i++) f[i]+=vasc[i]*.45*lungs[i];

  const ribs=strokeField(w,h,2.3,g=>{
    g.lineCap='round';
    for(let i=0;i<9;i++){
      const y0=h*(.225+i*.0585), spread=w*(.20+i*.0175), drop=h*(.10+i*.013);
      const br=Math.round(168-i*7);
      g.strokeStyle=`rgb(${br},0,0)`; g.lineWidth=7;
      for(const side of [-1,1]){
        g.beginPath();
        g.ellipse(w*.5,y0,spread,drop,0,side<0?Math.PI*1.08:Math.PI*1.62,
                  side<0?Math.PI*1.92:Math.PI*0.42);
        g.stroke();
      }
    }
    for(let i=0;i<6;i++){
      const y0=h*(.345+i*.062), spread=w*(.185+i*.016);
      g.strokeStyle=`rgb(${Math.round(92-i*6)},0,0)`; g.lineWidth=5;
      for(const side of [-1,1]){
        g.beginPath();
        g.ellipse(w*.5,y0+h*.04,spread*.9,h*.09,0,
                  side<0?Math.PI*1.14:Math.PI*1.66,side<0?Math.PI*1.86:Math.PI*0.38);
        g.stroke();
      }
    }
  });
  for(let i=0;i<f.length;i++) f[i]+=ribs[i]*(0.30+0.26*lungs[i])*Math.min(1,soft[i]+.15);

  const clav=strokeField(w,h,2.2,g=>{
    g.strokeStyle='rgb(200,0,0)'; g.lineWidth=8; g.lineCap='round';
    g.beginPath(); g.ellipse(w*.33,h*.225,w*.17,h*.07,0,Math.PI*1.1,Math.PI*1.9); g.stroke();
    g.beginPath(); g.ellipse(w*.67,h*.225,w*.17,h*.07,0,Math.PI*1.1,Math.PI*1.9); g.stroke();
  });
  for(let i=0;i<f.length;i++) f[i]+=clav[i]*.42;

  const med=ellipseMask(w,h,w*.5,h*.44,w*.052,h*.26,0,.30);
  const spine=ellipseMask(w,h,w*.5,h*.54,w*.038,h*.42,0,.22);
  for(let i=0;i<f.length;i++) f[i]+=(med[i]*26+spine[i]*24)*soft[i];

  const verts=strokeField(w,h,1.8,g=>{
    g.fillStyle='rgb(58,0,0)';
    for(let i=0;i<12;i++){const y=h*(.205+i*.0495); g.fillRect(w*.466,y,w*.068,h*.034);}
  });
  for(let i=0;i<f.length;i++) f[i]+=verts[i]*.32*soft[i];
  for(let i=0;i<f.length;i++) f[i]+=heart[i]*34*soft[i];

  const diaph=strokeField(w,h,3.0,g=>{
    g.fillStyle='rgb(112,0,0)';
    g.beginPath(); g.ellipse(w*.34,h*.78,w*.175,h*.18,0,Math.PI,2*Math.PI); g.fill();
    g.fillStyle='rgb(100,0,0)';
    g.beginPath(); g.ellipse(w*.65,h*.82,w*.17,h*.18,0,Math.PI,2*Math.PI); g.fill();
  });
  const abd=ellipseMask(w,h,w*.5,h*.98,w*.40,h*.17,0,.28);
  const gas=ellipseMask(w,h,w*.615,h*.80,w*.055,h*.038,0,.35);
  const gr=grain(w,h,rnd,6.0);
  for(let i=0;i<f.length;i++) f[i]+=diaph[i]*.42*soft[i]+abd[i]*44*soft[i]-gas[i]*34+gr[i];
  vignette(f,w,h,.46);
  return blur(f,w,h,.8,1);
}

/* ── brain MRI ── */
function brainMRI(w,h,rnd){
  const f=field(w,h); for(let i=0;i<f.length;i++) f[i]=5;
  const cx=w*.5,cy=h*.5,rx=w*.355,ry=h*.425;
  const scalp=ellipseMask(w,h,cx,cy,rx*1.085,ry*1.07,0,.035);
  const osk  =ellipseMask(w,h,cx,cy,rx*1.03,ry*1.018,0,.030);
  const isk  =ellipseMask(w,h,cx,cy,rx*.975,ry*.962,0,.028);
  const brain=ellipseMask(w,h,cx,cy,rx*.945,ry*.930,0,.030);
  const inner=ellipseMask(w,h,cx,cy,rx*.835,ry*.805,0,.12);
  for(let i=0;i<f.length;i++){
    f[i]+=(scalp[i]-osk[i])*120+(osk[i]-isk[i])*14+(isk[i]-brain[i])*165+brain[i]*108;
    f[i]+=Math.max(0,brain[i]-inner[i])*26;
  }
  // noise-driven gyral folding (ridge transform)
  const n=field(w,h); for(let i=0;i<n.length;i++) n[i]=gauss(rnd);
  blur(n,w,h,Math.max(2,w*.013),2);
  let mean=0; for(let i=0;i<n.length;i++) mean+=n[i]; mean/=n.length;
  let sd=0; for(let i=0;i<n.length;i++) sd+=(n[i]-mean)**2; sd=Math.sqrt(sd/n.length)||1;
  for(let y=0;y<h;y++)for(let x=0;x<w;x++){
    const i=y*w+x, z=(n[i]-mean)/sd;
    const rad=Math.sqrt(((x-cx)/rx)**2+((y-cy)/ry)**2);
    const ridge=Math.max(0,1-Math.abs(z)*1.15)**1.4;
    const depth=Math.max(0,Math.min(1,(rad-.46)/.50))**.7;
    f[i]+=ridge*depth*brain[i]*66;
  }
  const fissure=ellipseMask(w,h,cx,cy,w*.009,ry*.90,0,.55);
  for(let i=0;i<f.length;i++) f[i]+=fissure[i]*brain[i]*58;
  const vent=field(w,h);
  for(const side of [-1,1]){
    const vx=cx+side*w*.052;
    ellipse(vent,w,h,vx,cy+h*.010,w*.026,h*.095,side*.16,.22,1);
    ellipse(vent,w,h,vx+side*w*.020,cy-h*.080,w*.030,h*.044,side*.72,.26,1);
    ellipse(vent,w,h,vx+side*w*.034,cy+h*.082,w*.022,h*.040,-side*.55,.30,1);
  }
  const third=ellipseMask(w,h,cx,cy+h*.020,w*.009,h*.055,0,.40);
  for(let i=0;i<f.length;i++){
    const v=Math.min(1,vent[i]);
    f[i]=f[i]*(1-v*.90)+v*.90*206;
    f[i]=f[i]*(1-third[i]*.80)+third[i]*.80*192;
  }
  const gr=grain(w,h,rnd,3.4);
  for(let i=0;i<f.length;i++) f[i]+=gr[i]*brain[i];
  vignette(f,w,h,.16);
  return blur(f,w,h,.9,1);
}

/* ── cardiac ultrasound ── */
function ultrasound(w,h,rnd){
  const f=field(w,h);
  const ax=w*.5, ay=h*.04, half=38*Math.PI/180;
  const echo=field(w,h); for(let i=0;i<echo.length;i++) echo[i]=.30;

  const lv=ellipseMask(w,h,w*.432,h*.400,w*.093,h*.158,.12,.26);
  const rv=ellipseMask(w,h,w*.593,h*.372,w*.076,h*.126,-.14,.28);
  const la=ellipseMask(w,h,w*.447,h*.700,w*.078,h*.082,.06,.30);
  const ra=ellipseMask(w,h,w*.581,h*.688,w*.068,h*.074,-.06,.30);
  const wl=annulus(w,h,w*.432,h*.400,w*.093,h*.158,w*.030,.12,.30);
  const wr=annulus(w,h,w*.593,h*.372,w*.076,h*.126,w*.018,-.14,.32);
  const wa=annulus(w,h,w*.447,h*.700,w*.078,h*.082,w*.014,.06,.34);
  const wb=annulus(w,h,w*.581,h*.688,w*.068,h*.074,-.06&&w*.013,-.06,.34);
  const sep=ellipseMask(w,h,w*.513,h*.400,w*.020,h*.150,.03,.40);
  const v1=ellipseMask(w,h,w*.448,h*.566,w*.072,h*.013,.10,.45);
  const v2=ellipseMask(w,h,w*.590,h*.548,w*.060,h*.011,-.08,.45);
  const peri=annulus(w,h,w*.508,h*.520,w*.215,h*.300,w*.012,.02,.30);

  for(let i=0;i<echo.length;i++){
    const blood=Math.min(1,lv[i]+rv[i]+la[i]+ra[i]);
    const walls=Math.min(1,wl[i]+wr[i]*.72+wa[i]*.62+wb[i]*.58);
    echo[i]+=walls*.62+sep[i]*.70+Math.min(1,v1[i]+v2[i])*.85+peri[i]*.55;
    echo[i]*=(1-blood*.93);
  }
  // Rayleigh speckle, smeared along the beam
  const sp=field(w,h);
  for(let i=0;i<sp.length;i++){ const u=Math.max(1e-6,rnd()); sp[i]=Math.sqrt(-2*Math.log(u)); }
  blur(sp,w,h,1,1);
  let mx=0; for(let i=0;i<sp.length;i++) mx=Math.max(mx,sp[i]);
  for(let i=0;i<sp.length;i++) sp[i]/=(mx||1);
  const sm=field(w,h);
  for(let y=0;y<h;y++)for(let x=0;x<w;x++){
    const i=y*w+x;
    sm[i]=(sp[i]+sp[Math.max(0,y-1)*w+x]+sp[Math.max(0,y-2)*w+x])/3;
  }
  for(let y=0;y<h;y++)for(let x=0;x<w;x++){
    const i=y*w+x, dx=x-ax, dy=y-ay;
    const r=Math.sqrt(dx*dx+dy*dy), th=Math.atan2(dx,Math.max(dy,1e-6));
    const inSector=(Math.abs(th)<=half && r<h*.96 && dy>0)?1:0;
    let v=echo[i]*sm[i]*430;
    v*=Math.max(.10,Math.min(1.30,1.30-Math.pow(r/(h*.96),1.25)*1.05));
    v*=(1+0.045*Math.sin(th/half*150));
    f[i]=v*inSector;
  }
  blur(f,w,h,1,1);
  return f;
}

/* ── CT abdomen ── */
function ctAbdomen(w,h,rnd){
  const f=field(w,h); for(let i=0;i<f.length;i++) f[i]=3;
  const cx=w*.5, cy=h*.505;
  const body=ellipseMask(w,h,cx,cy,w*.435,h*.335,0,.030);
  const musc=ellipseMask(w,h,cx,cy,w*.395,h*.296,0,.045);
  for(let i=0;i<f.length;i++) f[i]+=body[i]*52+musc[i]*46;

  ellipse(f,w,h,w*.330,h*.425,w*.195,h*.165,.22,.09,30);
  ellipse(f,w,h,w*.712,h*.418,w*.088,h*.092,-.35,.14,28);
  const stom=ellipseMask(w,h,w*.560,h*.372,w*.092,h*.078,.18,.16);
  for(let i=0;i<f.length;i++) f[i]-=stom[i]*44;
  ellipse(f,w,h,w*.560,h*.400,w*.084,h*.034,0,.30,40);
  for(const side of [-1,1]){
    ellipse(f,w,h,cx+side*w*.178,h*.570,w*.062,h*.052,side*.3,.14,34);
    const pel=ellipseMask(w,h,cx+side*w*.178+side*w*.012,h*.570,w*.022,h*.020,side*.3,.3);
    for(let i=0;i<f.length;i++) f[i]-=pel[i]*18;
  }
  for(let k=0;k<9;k++){
    const ang=rnd()*2*Math.PI, rad=Math.pow(rnd(),.6);
    const bx=cx+Math.cos(ang)*rad*w*.155, by=h*.545+Math.sin(ang)*rad*h*.085;
    const rr=0.028+rnd()*0.017;
    const ring=annulus(w,h,bx,by,w*rr,h*rr*.95,w*rr*.30,0,.34);
    const gasm=ellipseMask(w,h,bx,by,w*rr*.64,h*rr*.60,0,.42);
    for(let i=0;i<f.length;i++) f[i]+=ring[i]*16-gasm[i]*14;
  }
  ellipse(f,w,h,cx,h*.690,w*.072,h*.058,0,.05,150);
  const trab=ellipseMask(w,h,cx,h*.690,w*.052,h*.040,0,.15);
  const canal=ellipseMask(w,h,cx,h*.735,w*.028,h*.024,0,.2);
  for(let i=0;i<f.length;i++) f[i]-=trab[i]*62+canal[i]*70;
  for(const side of [-1,1]){
    ellipse(f,w,h,cx+side*w*.098,h*.690,w*.034,h*.016,side*.2,.15,120);
    ellipse(f,w,h,cx+side*w*.072,h*.655,w*.040,h*.038,side*.25,.18,22);
  }
  ellipse(f,w,h,cx,h*.778,w*.016,h*.040,0,.15,115);
  ellipse(f,w,h,cx-w*.030,h*.620,w*.026,h*.024,0,.16,42);
  ellipse(f,w,h,cx+w*.036,h*.616,w*.030,h*.022,0,.20,34);
  const ra=w*.408, rb=h*.312;
  for(let i=0;i<13;i++){
    const t=Math.PI*(-.46+i/12*.92);
    for(const side of [-1,1]){
      const px=cx+side*ra*Math.cos(t), py=cy+rb*Math.sin(t);
      const tan=Math.atan2(rb*Math.cos(t),-side*ra*Math.sin(t));
      ellipse(f,w,h,px,py,w*.024,h*.009,-tan,.30,95*(0.75+0.25*(i%2)));
    }
  }
  const gr=grain(w,h,rnd,3.0);
  for(let i=0;i<f.length;i++) f[i]+=gr[i]*body[i];
  vignette(f,w,h,.14);
  return blur(f,w,h,.7,1);
}

/* ── render a grayscale field to a canvas ── */
function paintField(ctx,f,w,h){
  const img=ctx.createImageData(w,h), d=img.data;
  for(let i=0;i<f.length;i++){
    const v=Math.max(0,Math.min(255,f[i]))|0;
    d[i*4]=v; d[i*4+1]=v; d[i*4+2]=v; d[i*4+3]=255;
  }
  ctx.putImageData(img,0,0);
}

/* ── ECG is drawn, not a density field ── */
function drawECG(ctx,w,h,rnd,rate){
  ctx.fillStyle='#FFFBFA'; ctx.fillRect(0,0,w,h);
  const sm=Math.max(5,Math.round(w/44));
  ctx.strokeStyle='#FBD8D2'; ctx.lineWidth=1;
  for(let x=0;x<w;x+=sm){ctx.beginPath();ctx.moveTo(x,0);ctx.lineTo(x,h);ctx.stroke();}
  for(let y=0;y<h;y+=sm){ctx.beginPath();ctx.moveTo(0,y);ctx.lineTo(w,y);ctx.stroke();}
  ctx.strokeStyle='#F3A096';
  for(let x=0;x<w;x+=sm*5){ctx.beginPath();ctx.moveTo(x,0);ctx.lineTo(x,h);ctx.stroke();}
  for(let y=0;y<h;y+=sm*5){ctx.beginPath();ctx.moveTo(0,y);ctx.lineTo(w,y);ctx.stroke();}

  const leads=[['II',1.0],['V1',.62],['V5',.88]];
  const beat=Math.max(w*60/((rate||72)*4.2),34);
  ctx.lineWidth=1.8; ctx.strokeStyle='#121620'; ctx.lineJoin='round';
  leads.forEach(([name,amp],li)=>{
    const base=h*(0.24+li*0.29);
    ctx.beginPath(); let started=false;
    for(let x=6;x<w-6;x+=beat){
      const j=gauss(rnd)*beat*0.012;
      const pts=[[0,0],[.10,0],[.16,.14],[.22,0],[.28,0],[.31,-.08],[.34,1],
                 [.37,-.22],[.40,0],[.52,0],[.62,.26],[.72,0],[1,0]];
      for(const [fr,mv] of pts){
        const px=x+fr*beat+j;
        const sign=(name==='V1'&&mv>.5)?-1:1;
        const py=base-mv*amp*sign*h*0.105+gauss(rnd)*0.4;
        if(px>w-4) continue;
        if(!started){ctx.moveTo(px,py);started=true;} else ctx.lineTo(px,py);
      }
    }
    ctx.stroke();
    ctx.fillStyle='#4A5162'; ctx.font='600 10px Inter,sans-serif';
    ctx.fillText(name,8,base-h*0.145);
  });
}

/* ── watermark burned into the pixels ── */
function watermark(ctx,w,h,label,seed,dark){
  ctx.save();
  // Below thumbnail size the caption text is unreadable and collides with the
  // card's own overlay, so only the diagonal SIMULATED ghost is drawn there.
  const roomy=w>=230&&h>=200;
  if(roomy){
    ctx.font='600 10px Inter,sans-serif';
    ctx.fillStyle=dark?'rgba(255,255,255,.92)':'rgba(30,36,48,.9)';
    ctx.fillText(label,9,15);
    // seed sits top-right so it cannot collide with the caption along the foot
    ctx.fillStyle=dark?'rgba(200,208,220,.75)':'rgba(110,118,132,.8)';
    ctx.textAlign='right';
    ctx.fillText('SEED '+seed,w-9,15);
    ctx.fillStyle='rgba(242,84,91,.95)';
    ctx.textAlign='center';
    ctx.fillText('SIMULATED — NOT A REAL PATIENT STUDY',w/2,h-9);
    ctx.textAlign='left';
  }
  ctx.translate(w/2,h/2); ctx.rotate(-28*Math.PI/180);
  ctx.font=`700 ${Math.max(11,w/(roomy?17:9))}px Inter,sans-serif`;
  ctx.fillStyle=dark?'rgba(255,255,255,.085)':'rgba(0,0,0,.055)';
  ctx.textAlign='center';
  for(let i=-1;i<=1;i++) ctx.fillText('SIMULATED',0,i*(h*(roomy?0.30:0.42)));
  ctx.restore();
}

const _cache=new Map();

/** Render a study into a canvas element. Cached by key+size. */
export function renderStudy(modality,key,w=320,h=320,opts={}){
  const ck=`${modality}|${key}|${w}x${h}`;
  if(_cache.has(ck)) return _cache.get(ck);
  const seed=seedFrom(modality+'|'+key);
  const rnd=mulberry(seed);
  const c=document.createElement('canvas'); c.width=w; c.height=h;
  const ctx=c.getContext('2d');
  if(modality==='ecg'){
    drawECG(ctx,w,h,rnd,opts.rate);
    watermark(ctx,w,h,MODALITIES[modality],seed%1000000,false);
  }else{
    const gen={xray_chest:chestXray,mri_brain:brainMRI,
               ultrasound_cardiac:ultrasound,ct_abdomen:ctAbdomen}[modality]||chestXray;
    paintField(ctx,gen(w,h,rnd),w,h);
    if(modality==='ultrasound_cardiac'&&w>=230){
      ctx.fillStyle='rgba(220,228,240,.85)'; ctx.font='600 10px Inter,sans-serif';
      [['LV',.432,.400],['RV',.593,.372],['LA',.447,.700],['RA',.581,.688]]
        .forEach(([l,fx,fy])=>ctx.fillText(l,w*fx-8,h*fy));
    }
    watermark(ctx,w,h,MODALITIES[modality],seed%1000000,true);
  }
  _cache.set(ck,c);
  return c;
}

export function studyDataURL(modality,key,w,h,opts){
  return renderStudy(modality,key,w,h,opts).toDataURL('image/png');
}
