let PARAMETER_BASELINE=null;
const PARAM_STATUS_KEY='stockIndicatorParameterStatusV2';
let PARAM_STATUS_TIMER=null;

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
  el.innerHTML=`<div>${msg}</div>${showButton?'<div style="margin-top:10px"><button id="viewBuyResults" type="button">Voir Achat avec ces résultats</button></div>':''}`;
}
function saveParameterStatus(state){
  try{localStorage.setItem(PARAM_STATUS_KEY,JSON.stringify(state))}catch(e){}
}
function loadParameterStatus(){
  try{return JSON.parse(localStorage.getItem(PARAM_STATUS_KEY)||'null')}catch(e){return null}
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
function renderStoredStatus(state){
  if(!state)return;
  if(state.phase==='requested')parameterNotice('Demande envoyée. Enregistrement en cours…');
  else if(state.phase==='calculating')parameterNotice('✓ Paramètres enregistrés. Calcul des résultats en cours…');
  else if(state.phase==='done')parameterNotice(`✓ Calcul terminé${state.scoredAt?` à ${new Date(state.scoredAt).toLocaleTimeString('fr-CA',{hour:'2-digit',minute:'2-digit',second:'2-digit'})}`:''}. Les résultats utilisent ces paramètres.`,false,true);
  else if(state.phase==='timeout')parameterNotice('Le calcul n’est pas encore confirmé. La vérification automatique continue lorsque tu reviens sur cette page.',true);
}
function watchParameterPublication(expected,started=Date.now()){
  if(!expected?.length)return;
  if(PARAM_STATUS_TIMER)clearInterval(PARAM_STATUS_TIMER);
  const tick=async()=>{
    try{
      const cfg=await fetchParameterConfig();
      if(!parameterChangesMatch(cfg,expected)){
        const state={phase:'requested',expected,started};
        saveParameterStatus(state);renderStoredStatus(state);return;
      }

      PARAMETER_BASELINE=cfg;
      syncParameterInputs(cfg);
      let state={phase:'calculating',expected,started};
      saveParameterStatus(state);renderStoredStatus(state);

      const results=await fetchResultsStatus();
      if(resultSnapshotMatches(results,expected)){
        if(PARAM_STATUS_TIMER){clearInterval(PARAM_STATUS_TIMER);PARAM_STATUS_TIMER=null}
        state={phase:'done',expected,started,scoredAt:results.scored_at||results.updated||null};
        saveParameterStatus(state);renderStoredStatus(state);
        return;
      }

      if(Date.now()-started>20*60*1000){
        state={phase:'timeout',expected,started};
        saveParameterStatus(state);renderStoredStatus(state);
      }
    }catch(e){/* nouvelle tentative au prochain passage */}
  };
  tick();
  PARAM_STATUS_TIMER=setInterval(tick,3000);
}

document.addEventListener('DOMContentLoaded',async()=>{
  try{PARAMETER_BASELINE=await fetchParameterConfig()}catch(e){}
  const stored=loadParameterStatus();
  if(stored?.expected?.length){
    renderStoredStatus(stored);
    if(stored.phase!=='done')watchParameterPublication(stored.expected,stored.started||Date.now());
  }
});

document.addEventListener('click',e=>{
  const view=e.target.closest('#viewBuyResults');
  if(view){window.location.href=`index.html?refresh=${Date.now()}`;return}
  const save=e.target.closest('#saveParameters');
  const reset=e.target.closest('#resetParameters');
  if(!save&&!reset)return;
  const expected=changedParameterValues();
  if(!expected.length)return;
  const started=Date.now();
  const state={phase:'requested',expected,started};
  saveParameterStatus(state);
  renderStoredStatus(state);
  setTimeout(()=>watchParameterPublication(expected,started),100);
});
