const WATCH_PENDING_KEY='stockIndicatorWatchPending';
let WATCH_TIMER=null;

function watchNotice(message,bad=false){
  const el=document.getElementById('notice');
  if(!el)return;
  el.textContent=message;
  el.className=`notice ${bad?'bad':''}`;
}

function readPendingWatch(){
  try{return JSON.parse(localStorage.getItem(WATCH_PENDING_KEY)||'null')}catch(e){return null}
}
function savePendingWatch(value){
  if(value)localStorage.setItem(WATCH_PENDING_KEY,JSON.stringify(value));
  else localStorage.removeItem(WATCH_PENDING_KEY);
}

async function fetchWatchSymbols(){
  const r=await fetch(`config/symbols.csv?watch=${Date.now()}`,{cache:'no-store'});
  if(!r.ok)throw new Error('symbols');
  const text=await r.text();
  return parseCSV(text);
}

async function checkPendingWatch(){
  const pending=readPendingWatch();
  if(!pending)return false;
  try{
    const rows=await fetchWatchSymbols();
    const exists=rows.some(x=>String(x.symbol||'').toUpperCase()===pending.symbol);
    const done=pending.action==='add'?exists:!exists;
    if(done){
      savePendingWatch(null);
      watchNotice(pending.action==='add'?`✓ ${pending.symbol} a été ajouté à la liste suivie.`:`✓ ${pending.symbol} a été supprimé de la liste suivie.`);
      if(WATCH_TIMER){clearInterval(WATCH_TIMER);WATCH_TIMER=null;}
      setTimeout(()=>window.location.reload(),700);
      return true;
    }
    watchNotice(pending.action==='add'?`⏳ Ajout de ${pending.symbol} en cours…`:`⏳ Suppression de ${pending.symbol} en cours…`);
  }catch(e){
    watchNotice(`⏳ Mise à jour de ${pending.symbol} en cours…`);
  }
  return false;
}

function startWatchPolling(){
  if(WATCH_TIMER)clearInterval(WATCH_TIMER);
  checkPendingWatch();
  WATCH_TIMER=setInterval(checkPendingWatch,3000);
}

document.addEventListener('DOMContentLoaded',()=>{
  const add=document.getElementById('watchAdd');
  if(add){
    add.addEventListener('submit',()=>{
      const symbol=document.getElementById('newSymbol')?.value.trim().toUpperCase();
      if(!symbol)return;
      savePendingWatch({action:'add',symbol,started_at:Date.now()});
      watchNotice(`⏳ Demande d’ajout de ${symbol} envoyée. En attente de GitHub…`);
      setTimeout(startWatchPolling,500);
    });
  }
  const list=document.getElementById('watchRows');
  if(list){
    list.addEventListener('click',e=>{
      const symbol=e.target?.dataset?.remove;
      if(!symbol)return;
      savePendingWatch({action:'remove',symbol:String(symbol).toUpperCase(),started_at:Date.now()});
      watchNotice(`⏳ Demande de suppression de ${symbol} envoyée. En attente de GitHub…`);
      setTimeout(startWatchPolling,500);
    });
  }
  if(readPendingWatch())startWatchPolling();
});

window.addEventListener('focus',()=>{if(readPendingWatch())checkPendingWatch();});
document.addEventListener('visibilitychange',()=>{if(!document.hidden&&readPendingWatch())checkPendingWatch();});
