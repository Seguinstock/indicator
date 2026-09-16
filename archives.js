(async()=>{
  const box=document.getElementById('archiveList'), summary=document.getElementById('archiveSummary');
  try{
    const r=await fetch('data/daily_archive.json',{cache:'no-store'}); const d=await r.json(); const days=d.days||[];
    const done=days.filter(x=>Number.isFinite(Number(x.average_return_pct)));
    const avg=done.length?done.reduce((s,x)=>s+Number(x.average_return_pct),0)/done.length:null;
    const compounded=done.reduce((v,x)=>v*(1+Number(x.average_return_pct)/100),1)-1;
    summary.innerHTML=`<b>${done.length}</b> journées complétées${avg===null?'':` · Moyenne quotidienne <b>${avg.toFixed(2)} %</b> · Rendement composé théorique <b>${(compounded*100).toFixed(2)} %</b>`}`;
    if(!days.length){box.textContent='Aucune journée archivée pour le moment.';return;}
    box.innerHTML=days.map(day=>{
      const a=Number(day.average_return_pct); const av=Number.isFinite(a)?`${a>=0?'+':''}${a.toFixed(2)} %`:'En attente';
      const rows=(day.picks||[]).map((p,i)=>{const rr=Number(p.return_pct);return `<tr><td>${i+1}</td><td><b>${p.symbol||''}</b></td><td>${Number(p.score||0).toFixed(1)}</td><td>${Number(p.risk||0).toFixed(1)}</td><td>${p.start_price==null?'—':Number(p.start_price).toFixed(2)}</td><td>${p.end_price==null?'—':Number(p.end_price).toFixed(2)}</td><td>${Number.isFinite(rr)?`${rr>=0?'+':''}${rr.toFixed(2)} %`:'—'}</td></tr>`}).join('');
      return `<details class="stock" ${day===days[0]?'open':''}><summary><b>${day.date}</b> · ${day.count||0} titres · moyenne <b>${av}</b></summary><div style="overflow:auto"><table style="width:100%;margin-top:10px"><thead><tr><th>#</th><th>Titre</th><th>Potentiel</th><th>Risque</th><th>8 h</th><th>17 h</th><th>Rendement</th></tr></thead><tbody>${rows}</tbody></table></div></details>`;
    }).join('');
  }catch(e){box.textContent='Impossible de charger les archives.';console.error(e)}
})();