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
function watchParameterPublication(expected){
  if(!expected.length)return;
  const started=Date.now();
  parameterNotice('Après avoir créé la demande GitHub, cette page vérifie automatiquement son enregistrement…');
  const timer=setInterval(async()=>{
    try{
      const cfg=await fetchParameterConfig();
      if(parameterChangesMatch(cfg,expected)){
        clearInterval(timer);
        syncParameterInputs(cfg);
        parameterNotice('✓ Paramètres enregistrés. Le classement Achat est en cours de mise à jour; avec le recalcul rapide, les changements de score devraient suivre presque immédiatement.');
      }else if(Date.now()-started>10*60*1000){
        clearInterval(timer);
        parameterNotice('La demande n’a pas encore été appliquée. Vérifie que la demande GitHub a bien été créée.',true);
      }
    }catch(e){/* nouvelle tentative au prochain passage */}
  },3000);
}

document.addEventListener('click',e=>{
  const save=e.target.closest('#saveParameters');
  const reset=e.target.closest('#resetParameters');
  if(!save&&!reset)return;
  setTimeout(()=>{
    let expected=parameterValuesFromPage();
    if(!expected.length)return;
    watchParameterPublication(expected);
  },100);
});
