export const valid = x => typeof x === 'number' && Number.isFinite(x);
export const salaries = rows => rows.map(r => r.salary).filter(valid).sort((a,b) => a-b);
export function quantile(sorted, p) {
  if (!sorted.length) return null;
  const i=(sorted.length-1)*p, lo=Math.floor(i), hi=Math.ceil(i);
  return sorted[lo]+(sorted[hi]-sorted[lo])*(i-lo);
}
export function percentile(sorted, value) {
  if (!sorted.length || !valid(value)) return null;
  let lo=0,hi=sorted.length;
  while(lo<hi){const mid=(lo+hi)>>>1;if(sorted[mid]<=value)lo=mid+1;else hi=mid;}
  return 100*lo/sorted.length;
}
export function summary(rows) {
  const s=salaries(rows);
  return {count:rows.length, salaryCount:s.length, missingSalary:rows.length-s.length,
    median:quantile(s,.5),average:s.length?s.reduce((a,b)=>a+b,0)/s.length:null,
    p90:quantile(s,.9),fullTime:rows.filter(r=>valid(r.fullTimePercent)&&r.fullTimePercent>=100).length,
    min:s[0]??null,max:s.at(-1)??null,sorted:s};
}
export function compare(sorted, value) {
  const median=quantile(sorted,.5), min=sorted[0], max=sorted.at(-1);
  return {median, difference:median!==null&&valid(value)?value-median:null,
    percentile:percentile(sorted,value),size:sorted.length,
    position:sorted.length&&valid(value)&&max>min?100*(value-min)/(max-min):null};
}
export function filterRecords(rows, filters, minimum=0) {
  return rows.filter(r=>Object.entries(filters).every(([k,values])=>!values.size||values.has(r[k]??'')) &&
    (minimum===0||(valid(r.fullTimePercent)&&r.fullTimePercent>=minimum)));
}
export function sortRecords(rows, key, direction) {
  return [...rows].sort((a,b)=>{
    const av=a[key],bv=b[key];
    if(av===null||av===undefined)return bv===null||bv===undefined?0:1;
    if(bv===null||bv===undefined)return -1;
    return direction*(typeof av==='number'?av-bv:String(av).localeCompare(String(bv)))||a.id.localeCompare(b.id);
  });
}
export function buildPeers(rows){
  const titleGroup=new Map(),title=new Map();
  for(const r of rows){
    if(r.jobTitle){
      if(!title.has(r.jobTitle))title.set(r.jobTitle,[]);
      title.get(r.jobTitle).push(r);
      if(r.departmentGroup){
        const key=JSON.stringify([r.jobTitle,r.departmentGroup]);
        if(!titleGroup.has(key))titleGroup.set(key,[]);
        titleGroup.get(key).push(r);
      }
    }
  }
  const salariesCache=salaries(rows);
  return r=>[
    compare(salaries(r.jobTitle&&r.departmentGroup?titleGroup.get(JSON.stringify([r.jobTitle,r.departmentGroup]))??[]:[]),r.salary),
    compare(salaries(r.jobTitle&&valid(r.fullTimePercent)?(title.get(r.jobTitle)??[]).filter(p=>valid(p.fullTimePercent)&&Math.abs(p.fullTimePercent-r.fullTimePercent)<=10):[]),r.salary),
    compare(salariesCache,r.salary)
  ];
}
