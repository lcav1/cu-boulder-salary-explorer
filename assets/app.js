import {valid,salaries,quantile,summary,compare,filterRecords,sortRecords,buildPeers} from './stats.js';
const $=id=>document.getElementById(id);
const money=x=>valid(x)?new Intl.NumberFormat('en-US',{style:'currency',currency:'USD',maximumFractionDigits:0}).format(x):'—';
const num=x=>new Intl.NumberFormat('en-US').format(x);
const pct=x=>valid(x)?`${x.toFixed(1)}%`:'—';
const compact=x=>valid(x)?`$${new Intl.NumberFormat('en-US',{notation:'compact',maximumFractionDigits:1}).format(x)}`:'—';
const escape=s=>String(s??'Not reported').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const signed=x=>valid(x)?`${x<0?'−':'+'}${money(Math.abs(x))}`:'—';
const definitions=[['jobFamily','Job family'],['departmentGroup','Department group'],['department','Department'],['jobTitle','Job title']];
const filters=Object.fromEntries(definitions.map(([key])=>[key,new Set()]));
let all=[],filtered=[],current=summary([]),peerFor,sortKey='salary',sortDirection=-1,page=0,pinned=false,activeAnchor=null,scatterPoints=[];
const pageSize=25;

function setupFilters(){
  $('filters').innerHTML=definitions.map(([key,label])=>`<div class="filter"><label id="${key}-label">${label}</label><details id="${key}-details"><summary id="${key}-summary" aria-labelledby="${key}-label ${key}-summary-text"><span id="${key}-summary-text">All ${label.toLowerCase()} options</span></summary><div class="filter-menu"><input type="search" id="${key}-search" placeholder="Search ${label.toLowerCase()}…" aria-label="Search ${label.toLowerCase()} options"><div class="filter-options" id="${key}-options"></div></div></details><div class="selection-count" id="${key}-count"></div></div>`).join('');
  for(const [key,label] of definitions){
    const options=[...new Set(all.map(r=>r[key]??''))].sort((a,b)=>a.localeCompare(b));
    $(''+key+'-options').innerHTML=options.map((v,i)=>`<label class="filter-option" data-search="${escape(v.toLowerCase())}"><input type="checkbox" value="${escape(v)}" data-key="${key}" id="${key}-option-${i}"><span>${escape(v||'Not reported')}</span></label>`).join('')+'<p class="no-options" hidden>No options match this search.</p>';
    $(key+'-search').addEventListener('input',e=>{
      let count=0;
      for(const option of $(key+'-options').querySelectorAll('.filter-option')){
        option.hidden=!option.dataset.search.includes(e.target.value.toLowerCase());
        if(!option.hidden)count++;
      }
      $(key+'-options').querySelector('.no-options').hidden=count>0;
    });
    $(key+'-options').addEventListener('change',e=>{
      if(e.target.type!=='checkbox')return;
      if(e.target.checked)filters[key].add(e.target.value);else filters[key].delete(e.target.value);
      updateFilterLabel(key,label);update();
    });
  }
  document.addEventListener('click',e=>{
    for(const [key] of definitions)if(!$(key+'-details').contains(e.target))$(key+'-details').open=false;
  });
}
function updateFilterLabel(key,label){
  const values=[...filters[key]];
  $(key+'-summary-text').textContent=values.length===0?`All ${label.toLowerCase()} options`:values.length===1?(values[0]||'Not reported'):`${values.length} selected`;
  $(key+'-count').textContent=values.length?`${values.length} selected`:'';
}
function reset(){
  for(const [key,label] of definitions){
    filters[key].clear();updateFilterLabel(key,label);$(key+'-details').open=false;
    $(key+'-search').value='';$(key+'-search').dispatchEvent(new Event('input'));
  }
  document.querySelectorAll('#filters input[type=checkbox]').forEach(c=>c.checked=false);
  $('minimum').value=0;$('minimum-value').textContent='0%';update();
}
function update(){
  hidePeer(true);page=0;
  filtered=filterRecords(all,filters,Number($('minimum').value));current=summary(filtered);
  const selections=Object.values(filters).reduce((n,s)=>n+s.size,0), minimum=Number($('minimum').value);
  $('active-summary').textContent=selections||minimum?`${selections} selected option${selections===1?'':'s'}${minimum?` · ≥ ${minimum}% full-time`:''}`:'All Boulder records';
  $('empty').hidden=filtered.length>0;
  $('metrics').innerHTML=[['Appointment records',num(current.count),`${num(all.length)} in the full snapshot`],['Median salary',money(current.median),'50th percentile'],['Average salary',money(current.average),'Arithmetic mean'],['90th percentile',money(current.p90),'90% at or below this value'],['Full-time records',num(current.fullTime),'At least 100% full-time']].map(([label,value,note])=>`<div class="metric"><div class="metric-label">${label}</div><div class="metric-value">${value}</div><div class="metric-note">${note}</div></div>`).join('');
  $('metrics').setAttribute('aria-busy','false');
  $('snapshot').textContent=`FY ${all[0]?.fiscalYear??''} · ${num(all.length)} source records · ${current.missingSalary?`${num(current.missingSalary)} filtered records missing salary · `:''}Snapshot collected ${window.snapshotDate}`;
  updateComparison();renderDistribution();renderScatter();renderBars('family-median','jobFamily',false);renderBars('family-count','jobFamily',true);renderGroups();renderTable();
  $('export').disabled=!filtered.length;
}
function updateComparison(){
  const input=$('your-salary'),value=input.value===''?null:Number(input.value);
  if(input.validity.badInput||(value!==null&&(!valid(value)||value<0))){
    $('salary-validation').textContent='Enter a valid salary of $0 or more.';
    $('comparison').innerHTML='<p>Enter a valid salary to compare.</p>';return;
  }
  $('salary-validation').textContent='';
  if(value===null){$('comparison').innerHTML='<p>Enter a salary to see your percentile and position in the salary range.</p>';return;}
  if(!current.salaryCount){$('comparison').innerHTML='<p>No known salaries in this view. Change the filters to make a comparison.</p>';return;}
  const c=compare(current.sorted,value),position=c.position;
  $('comparison').innerHTML=`<div class="compare-values"><div><strong id="salary-percentile">${pct(c.percentile)}</strong><span>of salary records at or below yours</span></div><div><strong id="salary-position">${pct(position)}</strong><span>position within the salary range</span></div></div><div class="range-track" aria-hidden="true"><span class="range-marker" style="left:${position===null?50:Math.max(0,Math.min(100,position))}%"></span></div><div class="range-labels compare"><span>Min ${money(current.min)}</span><span>Max ${money(current.max)}</span></div><p class="range-description">${signed(c.difference)} from the median · ${num(c.size)} salary records.${position===null?' Range position is undefined because all salaries are equal.':position<0?' Your salary is below this range.':position>100?' Your salary is above this range.':''}</p>`;
}
function renderDistribution(){
  const target=$('distribution'),s=current.sorted;
  if(!s.length){target.innerHTML='<p class="chart-empty">No known salary data in this view.</p>';return;}
  const logarithmic=$('log-scale').checked,transform=x=>logarithmic?Math.log10(x+1):x,inverse=x=>logarithmic?10**x-1:x;
  let lo=transform(s[0]),hi=transform(s.at(-1));if(hi===lo){lo=Math.max(0,lo-.5);hi+=.5;}
  const n=24,bins=Array(n).fill(0),w=640,h=245,left=45,right=12,top=18,bottom=42,pw=w-left-right,ph=h-top-bottom;
  for(const v of s)bins[Math.min(n-1,Math.floor((transform(v)-lo)/(hi-lo)*n))]++;
  const max=Math.max(...bins,1),bw=pw/n;
  let svg=`<svg viewBox="0 0 ${w} ${h}" role="img" aria-label="Salary histogram of ${s.length} appointment records, ${logarithmic?'logarithmic':'linear'} salary axis, ranging from ${escape(money(s[0]))} to ${escape(money(s.at(-1)))}"><title>Salary distribution</title>`;
  for(let i=0;i<=3;i++){const y=top+ph-i*ph/3;svg+=`<line class="chart-gridline" x1="${left}" x2="${w-right}" y1="${y}" y2="${y}"/><text x="${left-7}" y="${y+3}" text-anchor="end">${num(Math.round(max*i/3))}</text>`;}
  bins.forEach((count,i)=>{
    const bh=count/max*ph,from=inverse(lo+i/n*(hi-lo)),to=inverse(lo+(i+1)/n*(hi-lo));
    svg+=`<rect class="histogram-bar" x="${left+i*bw+1}" y="${top+ph-bh}" width="${bw-2}" height="${bh}"><title>${escape(money(from))} – ${escape(money(to))}: ${num(count)} records (lower bound inclusive${i===n-1?', upper bound inclusive':''})</title></rect>`;
  });
  for(let i=0;i<=4;i++)svg+=`<text x="${left+pw*i/4}" y="${h-22}" text-anchor="${i===0?'start':i===4?'end':'middle'}">${compact(inverse(lo+i/4*(hi-lo)))}</text>`;
  svg+=`<text class="chart-axis-label" x="${left+pw/2}" y="${h-4}" text-anchor="middle">Annual base salary${logarithmic?' · logarithmic scale':''}</text></svg>`;
  target.innerHTML=svg;
}
function renderScatter(){
  const canvas=$('scatter'),rect=canvas.getBoundingClientRect(),width=Math.max(rect.width,240),height=245,dpr=window.devicePixelRatio||1;
  canvas.width=width*dpr;canvas.height=height*dpr;
  const ctx=canvas.getContext('2d');ctx.scale(dpr,dpr);ctx.clearRect(0,0,width,height);
  scatterPoints=[];
  const rows=filtered.filter(r=>valid(r.salary)&&valid(r.fullTimePercent));
  $('scatter-note').textContent=`${num(rows.length)} points · ${num(filtered.length-rows.length)} records omitted for missing salary or full-time percentage. Linear axes.`;
  canvas.setAttribute('aria-label',`Salary versus full-time percentage for ${rows.length} records. Full record values are available in the table. Linear axes.`);
  if(!rows.length){ctx.fillStyle='#657075';ctx.font='12px sans-serif';ctx.fillText('No records with salary and full-time data.',15,100);return;}
  const maxSalary=Math.max(1,...rows.map(r=>r.salary)),maxFT=Math.max(100,...rows.map(r=>r.fullTimePercent)),left=57,top=14,bottom=36,right=15,pw=width-left-right,ph=height-top-bottom;
  ctx.font='10px -apple-system, sans-serif';
  for(let i=0;i<=4;i++){
    const y=top+ph-i*ph/4;ctx.strokeStyle='#ebede9';ctx.beginPath();ctx.moveTo(left,y);ctx.lineTo(width-right,y);ctx.stroke();ctx.fillStyle='#758086';ctx.textAlign='right';ctx.fillText(compact(maxSalary*i/4),left-8,y+3);
    const x=left+pw*i/4;ctx.textAlign='center';ctx.fillText(`${Math.round(maxFT*i/4)}%`,x,height-18);
  }
  ctx.fillText('Full-time percentage',left+pw/2,height-2);
  ctx.fillStyle='rgba(75,116,134,.33)';
  for(const r of rows){const x=left+r.fullTimePercent/maxFT*pw,y=top+ph-r.salary/maxSalary*ph;ctx.beginPath();ctx.arc(x,y,2.4,0,2*Math.PI);ctx.fill();scatterPoints.push({x,y,r});}
}
$('scatter').addEventListener('pointermove',e=>{
  const rect=e.target.getBoundingClientRect(),x=e.clientX-rect.left,y=e.clientY-rect.top;
  let nearest=null,distance=100;
  for(const p of scatterPoints){const d=(x-p.x)**2+(y-p.y)**2;if(d<distance){distance=d;nearest=p;}}
  const tip=$('scatter-tip');tip.hidden=!nearest;
  if(nearest){tip.textContent=`${nearest.r.rosterId??'No roster ID'} · ${nearest.r.jobTitle??'No title'} · ${money(nearest.r.salary)} · ${nearest.r.fullTimePercent}%`;tip.style.left=`${Math.max(0,Math.min(rect.width-210,x+10))}px`;tip.style.top=`${Math.max(0,y-60)}px`;}
});
$('scatter').addEventListener('pointerleave',()=>$('scatter-tip').hidden=true);
function grouped(key){
  const groups=new Map();for(const r of filtered){const label=r[key]??'Not reported';if(!groups.has(label))groups.set(label,[]);groups.get(label).push(r);}
  return [...groups].map(([label,rows])=>({label,rows,stats:summary(rows)}));
}
function renderBars(id,key,countMode){
  const groups=grouped(key).sort((a,b)=>(countMode?b.stats.count-a.stats.count:(b.stats.median??-1)-(a.stats.median??-1))||a.label.localeCompare(b.label));
  const max=Math.max(1,...groups.map(g=>countMode?g.stats.count:g.stats.median??0));
  $(id).innerHTML=groups.length?groups.map(g=>{
    const value=countMode?g.stats.count:g.stats.median;
    return `<div class="bar-row" role="listitem" title="${escape(g.label)}: ${countMode?num(value)+' records':money(value)+' median'}; ${num(g.stats.salaryCount)} known salaries"><div class="bar-label"><span>${escape(g.label)}</span><strong>${countMode?num(value):money(value)}</strong></div><div class="bar-track"><div class="bar-fill ${countMode?'blue':''}" style="width:${valid(value)?100*value/max:0}%"></div></div></div>`;
  }).join(''):'<p class="chart-empty">No matching job families.</p>';
}
function renderGroups(){
  const groups=grouped('departmentGroup').sort((a,b)=>(b.stats.median??-1)-(a.stats.median??-1));
  const max=Math.max(1,...groups.map(g=>quantile(g.stats.sorted,.75)??0));
  $('group-chart').innerHTML=groups.length?groups.map(g=>{
    const q1=quantile(g.stats.sorted,.25),q3=quantile(g.stats.sorted,.75),median=g.stats.median;
    return `<div class="group-row" role="listitem" title="${escape(g.label)} · Median ${money(median)} · 25th ${money(q1)} · 75th ${money(q3)} · ${num(g.stats.salaryCount)} known salary records"><span class="group-name">${escape(g.label)}</span><div class="group-track" aria-hidden="true">${median===null?'':`<span class="group-iqr" style="left:${q1/max*100}%;width:${(q3-q1)/max*100}%"></span><span class="group-dot" style="left:${median/max*100}%"></span>`}</div><span class="group-value">${money(median)}<small>${num(g.stats.salaryCount)} salary records</small></span></div>`;
  }).join(''):'<p class="chart-empty">No matching department groups.</p>';
  $('group-axis').innerHTML=groups.length?[0,.25,.5,.75,1].map(p=>`<span>${compact(max*p)}</span>`).join(''):'';
}
const columns=[['department','Department name'],['rosterId','Roster ID'],['jobTitle','Job title'],['jobFamily','Job family'],['salary','Total salary'],['fullTimePercent','Full-time %']];
function renderTable(){
  const sorted=sortRecords(filtered,sortKey,sortDirection),pages=Math.ceil(sorted.length/pageSize);
  page=Math.max(0,Math.min(page,Math.max(0,pages-1)));
  document.querySelector('#records thead tr').innerHTML=columns.map(([key,label])=>`<th scope="col" aria-sort="${sortKey===key?(sortDirection===1?'ascending':'descending'):'none'}"><button data-sort="${key}" aria-label="Sort by ${label}">${label}<span aria-hidden="true">${sortKey===key?(sortDirection===1?'↑':'↓'):'↕'}</span></button></th>`).join('');
  document.querySelector('#records tbody').innerHTML=sorted.slice(page*pageSize,(page+1)*pageSize).map(r=>`<tr data-id="${r.id}"><td data-label="Department name"><button class="info-button" data-peer="${r.id}" aria-label="Peer comparisons for ${escape(r.rosterId??r.jobTitle)}" aria-describedby="peer-tooltip">ⓘ</button>${escape(r.department)}</td><td data-label="Roster ID">${escape(r.rosterId)}</td><td data-label="Job title">${escape(r.jobTitle)}</td><td data-label="Job family">${escape(r.jobFamily)}</td><td data-label="Total salary">${money(r.salary)}</td><td data-label="Full-time %">${valid(r.fullTimePercent)?`${num(r.fullTimePercent)}%`:'—'}</td></tr>`).join('')||'<tr><td colspan="6">No matching appointment records.</td></tr>';
  $('page-label').textContent=sorted.length?`${num(page*pageSize+1)}–${num(Math.min((page+1)*pageSize,sorted.length))} of ${num(sorted.length)} records · Page ${page+1} of ${pages}`:'0 records';
  $('previous').disabled=page===0;$('next').disabled=page>=pages-1||!pages;
}
function showPeer(anchor,keep=false){
  if(pinned&&!keep)return;
  const row=all.find(r=>r.id===anchor.dataset.peer);if(!row)return;
  pinned=keep;activeAnchor=anchor;
  const peers=peerFor(row),labels=['Same job title + department group','Same job title + full-time within ±10 points','All CU Boulder salary records'];
  $('peer-tooltip').innerHTML=`<button class="peer-close" aria-label="Close peer comparisons">×</button><h3>${escape(row.jobTitle)}</h3><p class="peer-meta">${escape(row.rosterId)} · ${escape(row.campus)} · Employee record ${escape(row.employeeRecord)}</p><p class="peer-meta"><strong>Department group:</strong> ${escape(row.departmentGroup)}<br><strong>Group detail:</strong> ${escape(row.departmentGroupDetail)}</p>${peers.map((c,i)=>`<div class="peer-group"><h4>${labels[i]}</h4><div class="peer-stats"><span>Median <strong>${money(c.median)}</strong></span><span>Difference <strong>${signed(c.difference)}</strong></span><span>Percentile <strong>${pct(c.percentile)}</strong></span><span>Group size <strong>${num(c.size)}</strong></span></div>${!c.size?'<p class="peer-note">No eligible peers with reported matching fields and salary.</p>':''}</div>`).join('')}<p class="peer-note">Full Boulder snapshot; dashboard filters do not affect these groups. Includes this record. Group sizes count known salaries. Similar full-time group spans the same title across all Boulder departments. ${row.salary===null?'This record has no reported salary; its difference and percentile are unavailable.':''}</p>`;
  $('peer-tooltip').setAttribute('role',keep?'dialog':'tooltip');
  $('peer-tooltip').setAttribute('aria-label','Appointment peer comparisons');
  $('peer-tooltip').hidden=false;
  const rect=anchor.getBoundingClientRect(),tip=$('peer-tooltip'),size=tip.getBoundingClientRect();
  tip.style.left=`${Math.max(12,Math.min(innerWidth-size.width-12,rect.right+12))}px`;
  tip.style.top=`${Math.max(12,Math.min(innerHeight-size.height-12,rect.top-size.height/3))}px`;
  tip.querySelector('.peer-close').onclick=()=>hidePeer(true);
}
function hidePeer(force=false){if(pinned&&!force)return;$('peer-tooltip').hidden=true;pinned=false;activeAnchor=null;}
$('records').addEventListener('click',e=>{
  const sort=e.target.closest('[data-sort]');if(sort){hidePeer(true);if(sortKey===sort.dataset.sort)sortDirection*=-1;else{sortKey=sort.dataset.sort;sortDirection=['salary','fullTimePercent'].includes(sortKey)?-1:1;}renderTable();document.querySelector(`[data-sort="${sortKey}"]`).focus();}
  const peer=e.target.closest('[data-peer]');if(peer){const wasPinned=pinned&&activeAnchor===peer;hidePeer(true);if(!wasPinned)showPeer(peer,true);}
});
$('records').addEventListener('pointerover',e=>{const a=e.target.closest('[data-peer]');if(a)showPeer(a);});
$('records').addEventListener('pointerout',e=>{if(e.target.closest('[data-peer]')&&!$('peer-tooltip').contains(e.relatedTarget))hidePeer();});
$('peer-tooltip').addEventListener('pointerleave',()=>hidePeer());
$('records').addEventListener('focusin',e=>{const a=e.target.closest('[data-peer]');if(a)showPeer(a);});
$('records').addEventListener('focusout',e=>{if(!$('peer-tooltip').contains(e.relatedTarget))hidePeer();});
document.addEventListener('keydown',e=>{if(e.key==='Escape'){hidePeer(true);for(const [key] of definitions)$(key+'-details').open=false;}});
document.addEventListener('click',e=>{if(pinned&&!e.target.closest('[data-peer]')&&!$('peer-tooltip').contains(e.target))hidePeer(true);});
window.addEventListener('scroll',()=>hidePeer(true),{passive:true});
$('previous').onclick=()=>{hidePeer(true);page--;renderTable();};$('next').onclick=()=>{hidePeer(true);page++;renderTable();};
$('minimum').addEventListener('input',e=>{$('minimum-value').textContent=`${e.target.value}%`;update();});
$('your-salary').addEventListener('input',updateComparison);
$('log-scale').addEventListener('change',renderDistribution);
$('reset').onclick=reset;$('empty-reset').onclick=reset;
let resizeTimer;window.addEventListener('resize',()=>{clearTimeout(resizeTimer);resizeTimer=setTimeout(()=>{renderScatter();hidePeer(true);},120);});
$('export').onclick=()=>{
  const fields=['fiscalYear','campus','departmentGroup','departmentGroupDetail','department','rosterId','jobTitle','jobFamily','salary','fullTimePercent','employeeRecord'];
  // Neutralize spreadsheet formula prefixes in source strings.
  const csvCell=v=>{let text=v??'';if(typeof text==='string'&&/^[=+@\-\t\r]/.test(text))text="'"+text;return '"'+String(text).replace(/"/g,'""')+'"';};
  const csv='\ufeff'+[fields,...sortRecords(filtered,sortKey,sortDirection).map(r=>fields.map(k=>r[k]))].map(row=>row.map(csvCell).join(',')).join('\r\n');
  const url=URL.createObjectURL(new Blob([csv],{type:'text/csv;charset=utf-8'})),a=document.createElement('a');a.href=url;a.download='cu-boulder-filtered-salaries.csv';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
};
async function init(){
  try{
    const response=await fetch(new URL('../data/salaries.json',import.meta.url),{cache:'no-cache'});
    if(!response.ok)throw new Error(`Snapshot request failed (${response.status})`);
    const data=await response.json();
    if(data.schemaVersion!==1||!Array.isArray(data.records)||!data.records.length||data.records.length!==data.recordCount||data.records.some(r=>r.campus!=='CU Boulder'))throw new Error('Snapshot is missing or invalid');
    all=data.records;peerFor=buildPeers(all);window.snapshotDate=new Date(data.collectedAt).toLocaleDateString('en-US',{year:'numeric',month:'short',day:'numeric',timeZone:'UTC'});
    $('year').textContent=`FY ${data.fiscalYear}`;setupFilters();
    for(const id of ['reset','minimum','your-salary','log-scale'])$(id).disabled=false;
    update();
  }catch(error){
    $('snapshot').textContent='Salary snapshot unavailable';$('year').textContent='Data unavailable';
    $('load-error').textContent='The salary snapshot could not be loaded. Please reload the page. For local setup, run python3 -m http.server 8000 from the repository root.';$('load-error').hidden=false;
    $('metrics').setAttribute('aria-busy','false');console.error(error);
  }
}
init();
