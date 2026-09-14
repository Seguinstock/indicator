(function(){
  function rsComponentText(x,sale=false){
    const comps=sale?(x.sell_components||{}):(x.potential_components||{});
    return `<div class="checks"><span class="check neutral">Force relative 20 j ${comps.relative_strength_20??'—'} pts</span><span class="check neutral">Rendement 60 j ${comps.return_60??'—'} pts</span><span class="check neutral">Tendance ${comps.trend??'—'} pts</span><span class="check neutral">RVOL ${comps.rvol??'—'} pts</span><span class="check neutral">RSI ${comps.rsi??'—'} pts</span></div>`;
  }

  function rsRender(id,rows,type){
    const el=document.getElementById(id);el.innerHTML='';
    if(!rows.length){el.innerHTML=`<div class="empty">${type==='sell'?'Aucun titre détenu analysable dans ce portefeuille.':'Aucun titre ne respecte les seuils choisis.'}</div>`;return}
    rows.forEach(x=>{
      const row=document.createElement('details');row.className='stock';
      const cls=x.country==='CA'?'canada':x.country==='US'?'usa':'other';
      const labels={rsi:'RSI',reversal:'Rebond RSI',support:'Zone de rebond',rvol:'Volume relatif',macd:'MACD',trend:'Tendance'};
      const checks=Object.entries(x.filters||{}).map(([k,v])=>`<span class="check ${v?'ok':'no'}">${v?'✓':'✕'} ${labels[k]||k}</span>`).join('');
      const sale=type==='sell';
      const componentText=rsComponentText(x,sale);
      const potential=Number(x.potential_score??x.score);
      const timing=Number(x.buy_timing??x.timing_v14);
      const risk=marketRisk(x);
      const riskText=`Risque ${risk.toFixed(0)}`;
      const buyScoreText=`Potentiel ${Number.isFinite(potential)?potential.toFixed(1):'—'} <span class="score-separator">·</span> Timing ${Number.isFinite(timing)?timing.toFixed(1):'—'} <span class="score-separator">·</span> ${riskText}`;
      const rsDetails=`<div>Rendement 20 j <b>${x.return_20_pct??'—'} %</b></div><div>Force relative 20 j <b>${x.relative_strength_20_pct??'—'} %</b></div><div>Rendement 60 j <b>${x.return_60_pct??'—'} %</b></div>`;
      row.innerHTML=`<summary><span class="symbol ${cls}">${x.symbol}</span><span class="score">${sale?`Score vente ${Number(x.score).toFixed(1)}`:buyScoreText}</span></summary><div class="detail"><div>Nom <b>${escapeHtml(x.name)}</b></div><div>Prix <b>${x.price??'—'}</b></div><div>RSI <b>${x.rsi??'—'}</b></div><div>Δ RSI <b>${x.delta_rsi??'—'}</b></div><div>RVOL <b>${x.rvol??'—'}</b></div><div>Distance de la zone de rebond <b>${x.support_distance_pct??'—'} %</b></div><div>MACD <b>${x.macd_momentum??'—'}</b></div><div>Tendance <b>${x.trend??'—'}</b></div><div>Volatilité <b>${x.volatility_pct??'—'} %</b></div>${rsDetails}${sale?`<div>Dégradation RS <b>${x.sell_timing_v14??'—'}</b></div><div>Signal <b>${x.sell_signal??'—'}</b></div>${componentText}<div class="hint">Le score vente mesure la détérioration de la même thèse Relative Strength que le score achat. Cette formulation de vente n’a pas encore été validée par le microtest.</div>`:`<div>Score potentiel <b>${x.potential_score??x.score??'—'}</b></div><div>Timing actuel <b>${x.buy_timing??x.timing_v14??'—'}</b></div><div>Risque de marché <b>${risk.toFixed(0)}/100 — ${riskLabel(risk)}</b></div>${componentText}<div class="checks">${checks}</div><div class="hint">Les voyants restent des diagnostics de timing : ils ne bloquent pas le classement Relative Strength.</div>`}</div>`;
      el.appendChild(row);
    });
  }

  function hasResults(){return typeof RESULTS!=='undefined'&&RESULTS;}
  function activate(){
    if(!hasResults()||RESULTS.buy_model!=='relative_strength_v1') return false;
    window.render=rsRender;
    const model=document.getElementById('activeBuyModel');
    if(model) model.textContent='Modèle actif : Relative Strength · 40 % force relative 20 j · 25 % rendement 60 j · 20 % tendance · 10 % RVOL · 5 % RSI';
    if(typeof applyBuyFilters==='function') applyBuyFilters();
    if(typeof showSell==='function') showSell();
    return true;
  }

  const timer=setInterval(()=>{if(activate())clearInterval(timer);},250);
  window.addEventListener('load',activate);
})();
