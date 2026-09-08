let PARAMETER_BASELINE=null;

function parameterPathGet(obj,path){return path.split('.').reduce((o,k)=>o?.[k],obj)}
function parameterValuesFromPage(){
  return [...document.querySelectorAll('#parameterRows .param')].map(card=>({
    path:card.dataset.path,
    value:Number(card.querySelector('input')?.value)
  })).filter(x=>x.path&&Number.isFinite(x.value));
}
function parameterNotice(msg,bad=false){
  const el=document.getElementById('notice');
  if(!el)return;
  el.textContent=msg;
  el.className=`notice ${bad?'bad':''}`;
}
async function fetchParameterConfig(){
  const r=await fetch(`config/parameters.json?status=${Date.now()}`,{cache:'no-store'});
  if(!r.ok)throw new Error('parameters');
  return r.json();
}
function parameterChangesMatch(cfg,expected){
  return expected.every(x=>Number(parameterPathGet(cfg,x.path))===Number(x.value));
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
function watchParameterPublication(expected){
  if(!expected.length)return;
  const started=Date.now();
  parameterNotice('Demande envoyée. Vérification automatique de l’enregistrement…');
  const timer=setInterval(async()=>{
    try{
      const cfg=await fetchParameterConfig();
      if(parameterChangesMatch(cfg,expected)){
        clearInterval(timer);
        PARAMETER_BASELINE=cfg;
        syncParameterInputs(cfg);
        parameterNotice('✓ Paramètres enregistrés et recalcul lancés. Le tableau Achat se met à jour automatiquement.');
      }else if(Date.now()-started>10*60*1000){
        clearInterval(timer);
        parameterNotice('La demande n’a pas encore été appliquée. Vérifie que la demande GitHub a bien été créée.',true);
      }
    }catch(e){/* nouvelle tentative au prochain passage */}
  },3000);
}

document.addEventListener('DOMContentLoaded',async()=>{
  try{PARAMETER_BASELINE=await fetchParameterConfig()}catch(e){}
});

document.addEventListener('click',e=>{
  const save=e.target.closest('#saveParameters');
  const reset=e.target.closest('#resetParameters');
  if(!save&&!reset)return;
  const expected=changedParameterValues();
  if(!expected.length)return;
  setTimeout(()=>watchParameterPublication(expected),100);
});
