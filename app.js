let RESULTS=null;

function formatLocalUpdate(value){
  if(!value)return '—';
  let raw=String(value).trim();
  if(/^\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}(:\d{2}(\.\d+)?)?$/.test(raw)) raw=raw.replace(' ','T')+'Z';
  const date=new Date(raw);
  if(Number.isNaN(date.getTime()))return value;
  return new Intl.DateTimeFormat('fr-CA',{year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',second:'2-digit',hour12:false}).format(date);
}

function marketRisk(x){
  // Indicateur informatif seulement : il n'entre dans aucun calcul de potentiel, timing ou classement.
  const vol=Number(x.volatility_pct);
  const price=Number(x.price);
  const rvol=Number(x.rvol);
  let score=0;
  if(Number.isFinite(vol)) score+=Math.max(0,Math.min(70,(vol-15)/65*70));
  else score+=35;
  if(Number.isFinite(price)){
    if(price<1) score+=20;
    else if(price<2) score+=17;
    else if(price<5) score+=13;
    else if(price<10) score+=8;
    else if(price<20) score+=4;
  }
  if(Number.isFinite(rvol)){
    if(rvol>=3) score+=10;
    else if(rvol>=2) score+=7;
    else if(rvol>=1.5) score+=4;
    else if(rvol<0.5) score+=5;
  }
  return Math.max(0,Math.min(100,score));
}

function riskLabel(score){
  if(score>=75)return 'spéculatif';
  if(score>=55)return 'élevé';
  if(score>=30)return 'modéré';
  return 'faible';
}

async function loadResults(){
  const r=await fetch('data/results.json?'+Date.now(),{cache:'no-store'});
  const d=await r.json(); RESULTS=d;
  document.getElementById('updated').textContent=`Mise à jour : ${formatLocalUpdate(d.updated)} · ${d.analyzed||0}/${d.universe||0} titres analysés`;
  render('buyList',d.buy||[],'buy');
  const sel=document.getElementById('sellPortfolio');
  const portfolios=(d.portfolios&&d.portfolios.length)?d.portfolios:[{id:'michel',name:'Michel'},{id:'fils',name:'Loïc'}];
  sel.innerHTML=portfolios.map(p=>`<option value="${p.id}">${p.name}</option>`).join('');
  const saved=localStorage.getItem('sellPortfolio');
  if(saved&&portfolios.some(p=>p.id===saved))sel.value=saved;
  showSell();
  sel.addEventListener('change',()=>{localStorage.setItem('sellPortfolio',sel.value);showSell()});
  const refresh=document.getElementById('forceRefresh');
  if(refresh)refresh.addEventListener('click',()=>{
    const body=`STOCK_INDICATOR_REFRESH\n\nDemande de mise à jour forcée depuis Stock Indicator.`;
    const url=`https://github.com/Seguinstock/indicator/issues/new?title=${encodeURIComponent('Refresh Stock Indicator')}&body=${encodeURIComponent(body)}`;
    window.open(url,'_blank','noopener');
  });
}

function showSell(){
  if(!RESULTS)return;
  const pid=document.getElementById('sellPortfolio')?.value||'michel';
  const rows=RESULTS.sell_by_portfolio?.[pid]??(pid==='michel'?RESULTS.sell||[]:[]);
  render('sellList',rows,'sell');
}

function render(id,rows,type){
  const el=document.getElementById(id);el.innerHTML='';
  if(!rows.length){el.innerHTML=`<div class="empty">${type==='sell'?'Aucun titre détenu analysable dans ce portefeuille.':'Aucun titre analysable.'}</div>`;return}
  rows.forEach(x=>{
    const row=document.createElement('details');row.className='stock';
    const cls=x.country==='CA'?'canada':x.country==='US'?'usa':'other';
    const labels={rsi:'RSI',reversal:'Rebond RSI',support:'Zone de rebond',rvol:'Volume relatif',macd:'MACD',trend:'Tendance'};
    const checks=Object.entries(x.filters||{}).map(([k,v])=>`<span class="check ${v?'ok':'no'}">${v?'✓':'✕'} ${labels[k]||k}</span>`).join('');
    const sale=type==='sell';
    const comps=x.potential_components||{};
    const componentText=!sale?`<div class="checks"><span class="check neutral">Volatilité ${comps.volatility??'—'} pts</span><span class="check neutral">Tendance ${comps.trend??'—'} pts</span><span class="check neutral">RVOL ${comps.rvol??'—'} pts</span><span class="check neutral">RSI ${comps.rsi??'—'} pts</span><span class="check neutral">Zone ${comps.support??'—'} pts</span></div>`:'';
    const potential=Number(x.potential_score??x.score);
    const timing=Number(x.buy_timing??x.timing_v14);
    const risk=marketRisk(x);
    const riskText=`Risque ${risk.toFixed(0)}`;
    const buyScoreText=`Potentiel ${Number.isFinite(potential)?potential.toFixed(1):'—'} <span class="score-separator">·</span> Timing ${Number.isFinite(timing)?timing.toFixed(1):'—'} <span class="score-separator">·</span> ${riskText}`;
    row.innerHTML=`<summary><span class="symbol ${cls}">${x.symbol}</span><span class="score">${sale?`Score vente ${Number(x.score).toFixed(1)}`:buyScoreText}</span></summary><div class="detail"><div>Prix <b>${x.price??'—'}</b></div><div>RSI <b>${x.rsi??'—'}</b></div><div>Δ RSI <b>${x.delta_rsi??'—'}</b></div><div>RVOL <b>${x.rvol??'—'}</b></div><div>Distance de la zone de rebond <b>${x.support_distance_pct??'—'} %</b></div><div>MACD <b>${x.macd_momentum??'—'}</b></div><div>Tendance <b>${x.trend??'—'}</b></div><div>Volatilité <b>${x.volatility_pct??'—'} %</b></div>${sale?`<div>Timing vente <b>${x.sell_timing_v14??'—'}</b></div><div>Signal <b>${x.sell_signal??'—'}</b></div>`:`<div>Score potentiel <b>${x.potential_score??x.score??'—'}</b></div><div>Timing actuel <b>${x.buy_timing??x.timing_v14??'—'}</b></div><div>Risque de marché <b>${risk.toFixed(0)}/100 — ${riskLabel(risk)}</b></div><div class="hint">Risque = indicateur indépendant basé actuellement sur volatilité, faible prix et comportement du volume. Il n'influence ni le potentiel, ni le timing, ni le classement. Les données fondamentales (dette, bénéfices, valorisation) ne sont pas encore incluses.</div>${componentText}<div class="checks">${checks}</div><div class="hint">Les voyants sont maintenant des diagnostics de timing : ils ne bloquent plus le classement potentiel.</div>`}</div>`;
    el.appendChild(row);
  });
}

loadResults().catch(e=>{document.getElementById('updated').textContent='Erreur de chargement';console.error(e)});
