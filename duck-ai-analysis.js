function buildDuckAiPrompt(){
  const rows=[...document.querySelectorAll('#buyList details.stock')].slice(0,30);
  if(!rows.length)return null;
  const stocks=rows.map(row=>{
    const symbol=row.querySelector('.symbol')?.textContent?.trim()||'';
    const score=row.querySelector('.score')?.textContent?.replace(/\s+/g,' ')?.trim()||'';
    const name=[...row.querySelectorAll('.detail>div')].find(x=>x.textContent.trim().startsWith('Nom '))?.querySelector('b')?.textContent?.trim()||'';
    return `- ${symbol}${name&&name!=='—'?` — ${name}`:''} — ${score}`;
  }).join('\n');
  return `Analyse les ${rows.length} titres boursiers ci-dessous. Je veux une validation INDÉPENDANTE du classement technique de Stock Indicator.\n\nPour chaque entreprise :\n1. identifie correctement l’entreprise et son secteur;\n2. analyse sa santé financière et opérationnelle : revenus, bénéfices, marges, dette, liquidités, flux de trésorerie, dilution éventuelle et tendance des derniers résultats connus;\n3. analyse l’actualité récente disponible : résultats, guidance, contrats majeurs, acquisitions, poursuites, réglementation, changements de direction, analystes et événements sectoriels;\n4. sépare clairement la santé de l’ENTREPRISE de l’attrait de l’ACTION;\n5. donne une cote Santé entreprise de 0 à 100 et un statut parmi Très sain / Sain / À surveiller / Préoccupant / Données insuffisantes;\n6. donne une cote Actualité récente de -2 à +2;\n7. indique au maximum 3 points positifs, 2 risques et le principal catalyseur;\n8. classe finalement les titres du plus rassurant au plus préoccupant.\n\nIMPORTANT : utilise l’information la plus récente à laquelle tu as réellement accès. Si tu n’as pas accès au Web ou à l’actualité en temps réel, dis-le clairement au début et N’INVENTE aucune nouvelle récente, aucun résultat financier ni aucune source.\n\nTitres actuellement affichés dans Stock Indicator :\n${stocks}`;
}

function copyTextFallback(text){
  const ta=document.createElement('textarea');
  ta.value=text;ta.style.position='fixed';ta.style.left='-9999px';document.body.appendChild(ta);ta.select();
  let ok=false;try{ok=document.execCommand('copy')}catch(e){}ta.remove();return ok;
}

async function launchDuckAi(){
  const notice=document.getElementById('aiAnalysisNotice');
  const prompt=buildDuckAiPrompt();
  if(!prompt){if(notice)notice.textContent='Aucun titre Achat n’est actuellement affiché.';return;}
  let copied=false;
  try{await navigator.clipboard.writeText(prompt);copied=true}catch(e){copied=copyTextFallback(prompt)}
  if(copied){
    localStorage.setItem('lastDuckAiPrompt',prompt);
    localStorage.setItem('lastDuckAiCount',String(document.querySelectorAll('#buyList details.stock').length));
    if(notice)notice.innerHTML='✓ Les titres et la consigne ont été copiés. Duck.ai s’ouvre : <b>colle simplement le texte dans la zone de discussion</b>.';
    window.open('https://duck.ai/','_blank','noopener');
  }else{
    if(notice)notice.textContent='Le navigateur a bloqué la copie automatique. Le texte est affiché ci-dessous pour le copier manuellement.';
    const box=document.getElementById('aiPromptFallback');
    if(box){box.value=prompt;box.hidden=false;box.focus();box.select();}
  }
}

document.addEventListener('click',e=>{if(e.target.closest('#analyzeBuyAi'))launchDuckAi();});
