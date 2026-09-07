const LABELS={rsi:'RSI',reversal:'Rebond RSI',support:'Zone de rebond',rvol:'RVOL',macd:'MACD',trend:'Tendance'};
let POLL_TIMER=null;
let REQUESTED_ASOF=null;
let REQUESTED_END=null;

function fmt(v,d=1){return v==null||Number.isNaN(Number(v))?'—':Number(v).toFixed(d)}
function pct(v){return v==null||Number.isNaN(Number(v))?'—':`${Number(v)>=0?'+':''}${Number(v).toFixed(2)} %`}
function tone(v){if(v==null)return 'neutral';return v?'ok':'no'}

async function loadBacktest(showFeedback=false){
  const meta=document.getElementById('btMeta');
  const reload=document.getElementById('reloadBacktest');
  const reloadNotice=document.getElementById('reloadNotice');
  if(showFeedback){
    reload.disabled=true;
    reload.textContent='↻ Actualisation…';
    reloadNotice.textContent='Vérification du dernier résultat…';
    reloadNotice.className='notice';
  }
  try{
    const r=await fetch('data/backtest.json?'+Date.now(),{cache:'no-store'});
    if(!r.ok)throw new Error('Aucun résultat');
    const d=await r.json();
    meta.textContent=`Photo du ${d.asof} · observation jusqu’au ${d.end} · ${d.tested||0}/${d.universe||0} titres`;
    renderSummary(d);
    renderRows(d.all_rows||d.top_by_score||[]);
    if(showFeedback){
      reloadNotice.textContent=`Résultat chargé : ${d.asof} → ${d.end}`;
      reloadNotice.className='notice';
    }
    if(REQUESTED_ASOF&&d.asof===REQUESTED_ASOF&&d.end===REQUESTED_END){
      const n=document.getElementById('requestNotice');
      n.textContent='✓ Backtest terminé. Les résultats ci-dessous sont à jour.';
      n.className='notice';
      stopPolling();
    }
    return d;
  }catch(e){
    meta.textContent='Aucun backtest disponible.';
    document.getElementById('btSummary').innerHTML='';
    document.getElementById('btList').innerHTML='<div class="empty">Lance un premier backtest.</div>';
    if(showFeedback){
      reloadNotice.textContent='Impossible de charger le résultat pour le moment.';
      reloadNotice.className='notice bad';
    }
    return null;
  }finally{
    if(showFeedback){
      reload.disabled=false;
      reload.textContent='↻ Actualiser maintenant';
    }
  }
}

function equalWeightPortfolio(rows,count){
  const sample=(rows||[]).slice(0,count).filter(x=>Number.isFinite(Number(x.return_pct)));
  if(!sample.length)return null;
  const invested=sample.length;
  const endValue=sample.reduce((sum,x)=>sum+(1+Number(x.return_pct)/100),0);
  const gainPct=(endValue/invested-1)*100;
  return {n:sample.length,invested,endValue,gainPct};
}

function renderSummary(d){
  const rows=d.all_rows||d.top_by_score||[];
  const p30=equalWeightPortfolio(rows,30);
  const p100=equalWeightPortfolio(rows,100);
  const portfolioCards=[p30&&`<div class="bt-stat portfolio-result"><b>Portefeuille Top 30</b><span class="${p30.gainPct>=0?'ok':'no'}">${pct(p30.gainPct)}</span><small>1 $ par titre · ${p30.invested.toFixed(0)} $ → ${p30.endValue.toFixed(2)} $</small></div>`,p100&&`<div class="bt-stat portfolio-result"><b>Portefeuille Top 100</b><span class="${p100.gainPct>=0?'ok':'no'}">${pct(p100.gainPct)}</span><small>1 $ par titre · ${p100.invested.toFixed(0)} $ → ${p100.endValue.toFixed(2)} $</small></div>`].filter(Boolean).join('');

  const effects=d.filter_effects||{};
  const order=['macd','rvol','reversal','rsi','support','trend'];
  const filterCards=order.map(k=>{
    const x=effects[k]; if(!x?.pass||!x?.fail)return '';
    const diff=Number(x.pass.avg_return_pct)-Number(x.fail.avg_return_pct);
    const cls=diff>0.25?'ok':diff<-0.25?'no':'neutral';
    return `<div class="bt-stat"><b>${LABELS[k]||k}</b><span class="${cls}">Passe ${pct(x.pass.avg_return_pct)}</span><small>Échoue ${pct(x.fail.avg_return_pct)} · gagnants ${fmt(x.pass.win_rate_pct)} %</small></div>`;
  }).join('');
  document.getElementById('btSummary').innerHTML=portfolioCards+filterCards;
}

function renderRows(rows){
  const el=document.getElementById('btList'); el.innerHTML='';
  if(!rows.length){el.innerHTML='<div class="empty">Aucun titre analysable.</div>';return}
  rows.slice(0,100).forEach(x=>{
    const row=document.createElement('details'); row.className='stock';
    const cls=x.country==='CA'?'canada':x.country==='US'?'usa':'other';
    const checks=Object.entries(x.filters||{}).map(([k,v])=>`<span class="check ${tone(v)}">${v?'✓':'✕'} ${LABELS[k]||k}</span>`).join('');
    row.innerHTML=`<summary><span class="symbol ${cls}">${x.symbol}</span><span class="score">Score ${fmt(x.score)} · ${pct(x.return_pct)}</span></summary><div class="detail"><div>Prix historique <b>${fmt(x.price,2)}</b></div><div>RSI <b>${fmt(x.rsi)}</b></div><div>Δ RSI <b>${fmt(x.delta_rsi)}</b></div><div>RVOL <b>${fmt(x.rvol,2)}</b></div><div>Zone de rebond <b>${fmt(x.support_distance_pct)} %</b></div><div>MACD <b>${fmt(x.macd_momentum)}</b></div><div>Tendance <b>${fmt(x.trend)}</b></div><div>Volatilité <b>${fmt(x.volatility_pct)} %</b></div><div class="path-stat">Fin de période <b class="${Number(x.return_pct)>=0?'ok':'no'}">${pct(x.return_pct)}</b></div><div class="path-stat">Pic observé <b class="ok">${pct(x.max_upside_pct)}</b></div><div class="path-stat">Creux observé <b class="no">${pct(x.max_drawdown_pct)}</b></div><div class="checks">${checks}</div></div>`;
    el.appendChild(row);
  });
}

function setDefaults(){
  const asof=document.getElementById('asof'), end=document.getElementById('end');
  const now=new Date();
  const a=new Date(now); a.setMonth(a.getMonth()-1);
  const e=new Date(a); e.setDate(e.getDate()+28);
  const iso=d=>d.toISOString().slice(0,10);
  asof.value=iso(a); end.value=iso(e);
  asof.max=iso(new Date(now.getTime()-86400000));
  asof.addEventListener('change',()=>{
    if(!asof.value)return;
    const d=new Date(asof.value+'T12:00:00'); d.setDate(d.getDate()+28); end.value=iso(d);
  });
}

function startPolling(){
  stopPolling();
  POLL_TIMER=setInterval(()=>loadBacktest(false),15000);
}
function stopPolling(){
  if(POLL_TIMER){clearInterval(POLL_TIMER);POLL_TIMER=null;}
}

function launch(){
  const asof=document.getElementById('asof').value;
  const end=document.getElementById('end').value;
  const notice=document.getElementById('requestNotice');
  if(!asof||!end){notice.textContent='Choisis les deux dates.';notice.className='notice bad';return}
  if(end<=asof){notice.textContent='La date d’observation doit être après la date historique.';notice.className='notice bad';return}
  REQUESTED_ASOF=asof; REQUESTED_END=end;
  const body=`STOCK_INDICATOR_BACKTEST\n\nBACKTEST_ASOF=${asof}\nBACKTEST_END=${end}\n\nDemande créée depuis la page Backtest de Stock Indicator.`;
  const url=`https://github.com/Seguinstock/indicator/issues/new?title=${encodeURIComponent('Run Stock Indicator Backtest')}&body=${encodeURIComponent(body)}`;
  notice.textContent='Après avoir confirmé la demande GitHub, cette page vérifiera automatiquement le résultat toutes les 15 secondes. Le calcul complet prend généralement environ 15 à 20 minutes.';
  notice.className='notice';
  startPolling();
  window.open(url,'_blank','noopener');
}

document.getElementById('runBacktest').addEventListener('click',launch);
document.getElementById('reloadBacktest').addEventListener('click',()=>loadBacktest(true));
setDefaults(); loadBacktest(false);
