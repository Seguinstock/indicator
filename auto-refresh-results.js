let LAST_RESULTS_UPDATED=null;
let RESULTS_CHECKING=false;

async function refreshActiveBuyModel(){
  const el=document.getElementById('activeBuyModel');
  if(!el)return;
  try{
    const r=await fetch(`config/parameters.json?model=${Date.now()}`,{cache:'no-store'});
    if(!r.ok)return;
    const cfg=await r.json();
    const b=cfg.buy_model||{};
    el.textContent=`Réglages actifs : Volatilité ${b.volatility_weight ?? '—'} · Tendance ${b.trend_weight ?? '—'} · RVOL ${b.rvol_weight ?? '—'} · RSI ${b.rsi_weight ?? '—'} · Zone ${b.support_weight ?? '—'} · Cible RSI ${b.rsi_target ?? '—'}`;
  }catch(e){}
}

async function checkForFreshResults(){
  if(RESULTS_CHECKING||document.hidden)return;
  RESULTS_CHECKING=true;
  try{
    await refreshActiveBuyModel();
    const r=await fetch(`data/results.json?watch=${Date.now()}`,{cache:'no-store'});
    if(!r.ok)return;
    const d=await r.json();
    if(LAST_RESULTS_UPDATED===null){
      LAST_RESULTS_UPDATED=d.updated||null;
      return;
    }
    if(d.updated&&d.updated!==LAST_RESULTS_UPDATED){
      LAST_RESULTS_UPDATED=d.updated;
      location.reload();
    }
  }catch(e){}finally{RESULTS_CHECKING=false}
}

setInterval(checkForFreshResults,5000);
document.addEventListener('visibilitychange',()=>{if(!document.hidden)checkForFreshResults()});
window.addEventListener('focus',checkForFreshResults);
checkForFreshResults();
