let LAST_RESULTS_UPDATED=null;
let RESULTS_CHECKING=false;

async function checkForFreshResults(){
  if(RESULTS_CHECKING||document.hidden)return;
  RESULTS_CHECKING=true;
  try{
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
