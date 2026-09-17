(async()=>{
  const box=document.getElementById('archiveList'), summary=document.getElementById('archiveSummary');
  const money=n=>Number(n).toLocaleString('fr-CA',{style:'currency',currency:'CAD'});
  const metric=v=>v==null||!Number.isFinite(Number(v))?'—':Number(v).toFixed(1);
  const hasReturn=day=>day.average_return_pct!==null&&day.average_return_pct!==undefined&&day.average_return_pct!==''&&Number.isFinite(Number(day.average_return_pct));
  const fmtDate=s=>{const [y,m,d]=String(s||'').split('-');return y&&m&&d?`${d}-${m}-${y.slice(-2)}`:s};
  // Historical fallback for 16-09-26, independently rechecked after the close.
  // Same open-to-close window as the strategy: 7 Canadian picks / 5 US picks.
  const historicalBenchmarks={'2026-09-16':{tsx_composite_return_pct:-0.517,sp500_return_pct:-0.650,canada_picks:7,usa_picks:5,return_pct:-0.573,method:'open_to_close_weighted_by_pick_market'}};
  const benchmarkOf=day=>day.benchmark||historicalBenchmarks[day.date]||null;
  try{
    const r=await fetch('data/daily_archive.json',{cache:'no-store'}); const d=await r.json(); const days=d.days||[];
    const chronological=[...days].sort((a,b)=>String(a.date).localeCompare(String(b.date)));
    let capital=10000;
    chronological.forEach(day=>{
      day._capitalStart=capital;
      if(hasReturn(day)){const a=Number(day.average_return_pct);capital*=1+a/100;day._capitalEnd=capital}else day._capitalEnd=null;
    });
    const done=chronological.filter(hasReturn);
    const avg=done.length?done.reduce((s,x)=>s+Number(x.average_return_pct),0)/done.length:null;
    const total=(capital/10000-1)*100;
    const annualized=done.length?((capital/10000)**(252/done.length)-1)*100:null;
    summary.innerHTML=`<div><b>Portefeuille théorique : 10 000 $ le 14-09-26</b> · Capital actuel <b>${money(capital)}</b> · Rendement total <b>${total>=0?'+':''}${total.toFixed(2)} %</b>${annualized===null?'':` · Taux annualisé <b>${annualized>=0?'+':''}${annualized.toFixed(2)} %</b>`}</div><div style="margin-top:5px"><b>${done.length}</b> journées complétées${avg===null?'':` · Moyenne quotidienne <b>${avg.toFixed(2)} %</b>`}</div><div class="hint" style="margin-top:5px">Une journée n'entre dans les statistiques qu'après réception de son rendement final. Comparatif marché : S&P/TSX pour les titres canadiens et S&P 500 pour les titres américains, pondérés selon le nombre de titres, sur la même fenêtre ouverture → clôture. Taux annualisé : rendement composé extrapolé sur 252 séances; avec peu de journées, il peut être extrêmement élevé ou faible et n'est pas une projection. PO. = potentiel · RI. = risque · TI. = timing.</div>`;
    if(!days.length){box.textContent='Aucune journée archivée pour le moment.';return;}
    const newest=[...chronological].reverse();
    box.innerHTML=newest.map((day,idx)=>{
      const complete=hasReturn(day), a=complete?Number(day.average_return_pct):null; const av=complete?`${a>=0?'+':''}${a.toFixed(2)} %`:'En attente';
      const capitalText=day._capitalEnd==null?`${money(day._capitalStart)} → en attente`:`${money(day._capitalStart)} → ${money(day._capitalEnd)}`;
      const allocation=(day.picks||[]).length?day._capitalStart/(day.picks||[]).length:0;
      const bm=benchmarkOf(day); const br=bm&&Number.isFinite(Number(bm.return_pct))?Number(bm.return_pct):null;
      const diff=complete&&br!==null?Number(day.average_return_pct)-br:null;
      const benchmarkText=br===null?'Marché : —':`Marché <b>${br>=0?'+':''}${br.toFixed(2)} %</b> · Écart <b>${diff>=0?'+':''}${diff.toFixed(2)} pt</b>${bm?` · TSX ${Number(bm.tsx_composite_return_pct)>=0?'+':''}${Number(bm.tsx_composite_return_pct).toFixed(2)} % · S&P 500 ${Number(bm.sp500_return_pct)>=0?'+':''}${Number(bm.sp500_return_pct).toFixed(2)} %`:''}`;
      const rows=(day.picks||[]).map((p,i)=>{const rr=p.return_pct==null?null:Number(p.return_pct);return `<tr><td>${i+1}</td><td><b>${p.symbol||''}</b></td><td>${metric(p.score)}</td><td>${metric(p.risk)}</td><td>${metric(p.timing??p.buy_timing??p.timing_v14)}</td><td>${p.start_price==null?'—':Number(p.start_price).toFixed(2)}</td><td>${p.end_price==null?'—':Number(p.end_price).toFixed(2)}</td><td>${rr!==null&&Number.isFinite(rr)?`${rr>=0?'+':''}${rr.toFixed(2)} %`:'—'}</td></tr>`}).join('');
      return `<details class="stock" ${idx===0?'open':''}><summary><b>${fmtDate(day.date)}</b> · ${day.count||0} titres · moyenne <b>${av}</b> · capital <b>${capitalText}</b></summary><div class="hint" style="margin:8px 0">Montant théorique par titre : <b>${money(allocation)}</b> · ${benchmarkText}</div><div style="overflow:auto"><table style="width:100%;margin-top:6px"><thead><tr><th>#</th><th>Titre</th><th>PO.</th><th>RI.</th><th>TI.</th><th>Ouverture</th><th>Clôture</th><th>Rendement</th></tr></thead><tbody>${rows}</tbody></table></div></details>`;
    }).join('');
  }catch(e){box.textContent='Impossible de charger les archives.';console.error(e)}
})();