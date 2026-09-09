const HOLDING_PENDING_KEY='stockIndicatorHoldingPending';
let HOLDING_TIMER=null;

function holdingNotice(message,bad=false){
  const el=document.getElementById('notice');
  if(!el)return;
  el.textContent=message;
  el.className=`notice ${bad?'bad':''}`;
}
function readPendingHolding(){try{return JSON.parse(localStorage.getItem(HOLDING_PENDING_KEY)||'null')}catch(e){return null}}
function savePendingHolding(v){if(v)localStorage.setItem(HOLDING_PENDING_KEY,JSON.stringify(v));else localStorage.removeItem(HOLDING_PENDING_KEY)}
async function fetchHoldingRows(file){const r=await fetch(`${file}?holding=${Date.now()}`,{cache:'no-store'});if(!r.ok)throw new Error(file);return parseCSV(await r.text())}
async function checkPendingHolding(){
  const p=readPendingHolding();if(!p)return false;
  try{
    const rows=await fetchHoldingRows(p.file);
    const exists=rows.some(x=>String(x.symbol||'').toUpperCase()===p.symbol);
    const done=p.action==='add'?exists:!exists;
    if(done){savePendingHolding(null);if(HOLDING_TIMER){clearInterval(HOLDING_TIMER);HOLDING_TIMER=null}holdingNotice(p.action==='add'?`✓ ${p.symbol} a été ajouté au portefeuille.`:`✓ ${p.symbol} a été supprimé du portefeuille.`);if(typeof window.reloadHoldingsList==='function')await window.reloadHoldingsList();return true}
    holdingNotice(p.action==='add'?`⏳ Ajout de ${p.symbol} en cours…`:`⏳ Suppression de ${p.symbol} en cours…`);
  }catch(e){holdingNotice(`⏳ Mise à jour de ${p.symbol} en cours…`)}
  return false;
}
function startHoldingPolling(){if(HOLDING_TIMER)clearInterval(HOLDING_TIMER);checkPendingHolding();HOLDING_TIMER=setInterval(checkPendingHolding,3000)}
window.addEventListener('holding-change-requested',e=>{const d=e.detail||{};if(!d.symbol||!d.file)return;savePendingHolding({action:d.action,portfolio:d.portfolio,file:d.file,symbol:String(d.symbol).toUpperCase(),started_at:Date.now()});holdingNotice(d.action==='add'?`⏳ Demande d’ajout de ${d.symbol} envoyée. En attente de GitHub…`:`⏳ Demande de suppression de ${d.symbol} envoyée. En attente de GitHub…`);setTimeout(startHoldingPolling,500)});
document.addEventListener('DOMContentLoaded',()=>{if(readPendingHolding())startHoldingPolling()});
window.addEventListener('focus',()=>{if(readPendingHolding())checkPendingHolding()});
document.addEventListener('visibilitychange',()=>{if(!document.hidden&&readPendingHolding())checkPendingHolding()});