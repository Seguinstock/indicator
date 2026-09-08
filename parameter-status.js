let PARAMETER_BASELINE=null;
let RESULTS_BASELINE=null;

function parameterPathGet(obj,path){return path.split('.').reduce((o,k)=>o?.[k],obj)}
function parameterValuesFromPage(){
  return [...document.querySelectorAll('#parameterRows .param')].map(card=>({
    path:card.dataset.path,
    value:Number(card.querySelector('input')?.value)
  })).filter(x=>x.path&&Number.isFinite(x.value));
}
function parameterNotice(msg,bad=false,showButton=false){
  const el=document.getElementById('notice');
  if(!el)return;
  el.className=`notice ${bad?'bad':''}`;
  el.innerHTML=`<div>${msg}</div>${showButton?'<div style="margin-top:10px"><button id="viewBuyResults" type="button">Actualiser / voir Achat</button></div>':''}`;
}
async function fetchParameterConfig(){
  const r=await fetch(`config/parameters.json?status=${Date.now()}`,{cache:'no-store'});
  if(!r.ok)throw new Error('parameters');
  return r.json();
}
async function fetchResultsStatus(){
  const r=await fetch(`data/results.json?status=${Date.now()}`,{cache:'no-store'});
  if(!r.ok)throw new Error('results');
  return r.json();
}
function parameterChangesMatch(cfg,expected){
  return expected.every(x=>Number(parameterPathGet(cfg,x.path))===Number(x.value));
}
function resultSnapshotMatches(results,expected){
  const snap=results?.parameter_snapshot;
  if(!snap)return false;
  return expected.every(x=>Number(parameterPathGet(snap,x.path))===Number(x.value));
}
function syncParameterInputs(cfg){
  document.querySelectorAll('#parameterRows .param').forEach(card=>{
    const input=card.querySelector('input');
    const v=parameterPathGet(cfg,card.dataset.path);
    if(input&&v!==undefined)input.value=v;
  });
}
function changedParameterValues(){
  const values=parameterValuesFromPage();
  if(!PARAMETER_BASELINE)return values;
  return values.filter(x=>Number(parameterPathGet(PARAMETER_BASELINE,x.path))!==Number(x.value));
}
function resultsChangedSinceBaseline(results){
  if(!RESULTS_BASELINE)return true;
  const current=results?.scored_at||results?.updated||null;
  const before=RESULTS_BASELINE?.scored_at||RESULTS_BASELINE?.updated||null;
  return Boolean(current&&current!==before);
}
function watchParameterPublication(expected){
  if(!expected.length)return;
  const started=Date.now();
  let configApplied=false;
  parameterNotice('Demande envoyée. Enregistrement en cours…');
  const timer=setInterval(async()=>{
    try{
      const cfg=await fetchParameterConfig();
      if(parameterChangesMatch(cfg,expected)){
        if(!configApplied){
          configApplied=true;
          PARAMETER_BASELINE=cfg;
          syncParameterInputs(cfg);
          parameterNotice('✓ Paramètres enregistrés. Recalcul des résultats en cours…');
        }
        const results=await fetchResultsStatus();
        if(resultSnapshotMatches(results,expected)||resultsChangedSinceBaseline(results)){
          clearInterval(timer);
          RESULTS_BASELINE=results;
          parameterNotice('✓ Recalcul terminé. Les nouveaux résultats sont publiés.',false,true);
        }
      }
      if(Date.now()-started>10*60*1000){
        clearInterval(timer);
        parameterNotice('Le traitement n’est pas terminé. Tu peux utiliser Actualiser / voir Achat pour vérifier les derniers résultats publiés.',true,true);
      }
    }catch(e){/* nouvelle tentative au prochain passage */}
  },3000);
}

document.addEventListener('DOMContentLoaded',async()=>{
  try{PARAMETER_BASELINE=await fetchParameterConfig()}catch(e){}
  try{RESULTS_BASELINE=await fetchResultsStatus()}catch(e){}
});

document.addEventListener('click',e=>{
  const view=e.target.closest('#viewBuyResults');
  if(view){window.location.href=`index.html?refresh=${Date.now()}`;return}
  const save=e.target.closest('#saveParameters');
  const reset=e.target.closest('#resetParameters');
  if(!save&&!reset)return;
  const expected=changedParameterValues();
  if(!expected.length)return;
  setTimeout(()=>watchParameterPublication(expected),100);
});
