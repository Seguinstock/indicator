function buildAiPrompt(){
  const rows=[...document.querySelectorAll('#buyList details.stock')].slice(0,30);
  if(!rows.length)return null;
  const stocks=rows.map(row=>{
    const symbol=row.querySelector('.symbol')?.textContent?.trim()||'';
    const name=[...row.querySelectorAll('.detail>div')].find(x=>x.textContent.trim().startsWith('Nom '))?.querySelector('b')?.textContent?.trim()||'';
    const market=row.querySelector('.symbol')?.classList.contains('canada')?'Canada':row.querySelector('.symbol')?.classList.contains('usa')?'États-Unis':'Marché à vérifier';
    return `- ${symbol}${name&&name!=='—'?` — ${name}`:''} — ${market}`;
  }).join('\n');
  return `Analyse les ${rows.length} titres boursiers ci-dessous comme des OPPORTUNITÉS D'ACHAT, en combinant le potentiel fondamental à long terme, les catalyseurs à court/moyen terme et la qualité du point d'entrée actuel.

IMPORTANT : fais une analyse indépendante. Ignore complètement le score, le potentiel, le risque et le classement calculés par Stock Indicator. Ne critique pas sa formule et ne cherche pas à valider ou invalider son score. Les titres transmis servent uniquement de liste de candidats à analyser.

Pour chaque titre :
1. identifie correctement l'entreprise, son marché et son secteur;
2. recherche l'actualité boursière et corporative la plus récente disponible;
3. analyse les derniers résultats connus : revenus, bénéfices, marges, dette, liquidités, flux de trésorerie, guidance et changements importants;
4. recherche les catalyseurs à court/moyen terme : résultats à venir, guidance, contrats, acquisitions, lancements, réglementation, analystes et événements sectoriels;
5. analyse le TIMING d'achat avec une importance élevée : tendance récente du cours, momentum, réaction aux nouvelles/résultats, proximité d'un catalyseur, risque de mouvement déjà trop avancé et éléments techniques disponibles;
6. distingue la qualité de l'entreprise de la qualité du point d'entrée. Le timing actuel est important, mais ne pénalise pas excessivement une entreprise de grande qualité dont le potentiel structurel à long terme demeure important. Un timing temporairement moins favorable doit réduire le classement de façon raisonnable, sans effacer une forte thèse long terme. À l'inverse, un excellent momentum à court terme ne doit pas suffire à placer très haut une entreprise aux fondamentaux fragiles;
7. indique brièvement pour chaque titre : thèse d'achat, principal catalyseur, principal risque et horizon probable;
8. utilise l'information la plus récente à laquelle tu as réellement accès. Si une donnée n'est pas disponible, indique-le et n'invente rien.

PRÉSENTATION OBLIGATOIRE :
- Produis exactement deux tableaux principaux : CANADA et ÉTATS-UNIS.
- Dans chacun, classe les titres de la meilleure à la moins bonne opportunité d'achat selon ton analyse indépendante.
- Colonnes : Rang | Titre | Opportunité / timing | Catalyseur | Risque principal | Horizon.
- Le rang doit rechercher le meilleur équilibre entre : (1) qualité et potentiel fondamental à long terme, (2) catalyseurs à court/moyen terme et (3) qualité du timing/point d'entrée actuel. Le timing compte beaucoup, mais ne doit pas dominer au point d'écarter une excellente opportunité structurelle.
- Après les deux tableaux, ajoute une courte section « Points à surveiller » uniquement pour les événements imminents susceptibles de modifier rapidement le classement.
- Ne reproduis pas et ne commente pas le score Stock Indicator.

Titres actuellement affichés :
${stocks}`;
}
function copyTextFallback(text){const ta=document.createElement('textarea');ta.value=text;ta.style.position='fixed';ta.style.left='-9999px';document.body.appendChild(ta);ta.select();let ok=false;try{ok=document.execCommand('copy')}catch(e){}ta.remove();return ok;}
async function launchAi(provider){
  const notice=document.getElementById('aiAnalysisNotice'),prompt=buildAiPrompt();
  if(!prompt){if(notice)notice.textContent='Aucun titre Achat n’est actuellement affiché.';return;}
  let copied=false;try{await navigator.clipboard.writeText(prompt);copied=true}catch(e){copied=copyTextFallback(prompt)}
  const isChat=provider==='chatgpt';
  const label=isChat?'ChatGPT':'Duck.ai';
  const url=isChat?'https://chatgpt.com/':'https://duck.ai/';
  if(copied){
    localStorage.setItem('lastAiPrompt',prompt);
    if(notice)notice.innerHTML=`✓ Les ${document.querySelectorAll('#buyList details.stock').length} titres affichés et la consigne ont été copiés. ${label} s’ouvre : <b>colle simplement le texte dans la discussion</b>.`;
    window.open(url,'_blank','noopener');
  }else{
    if(notice)notice.textContent=`Le navigateur a bloqué la copie automatique. Copie le texte ci-dessous puis ouvre ${label}.`;
    const box=document.getElementById('aiPromptFallback');if(box){box.value=prompt;box.hidden=false;box.focus();box.select();}
    window.open(url,'_blank','noopener');
  }
}
document.addEventListener('click',e=>{if(e.target.closest('#analyzeBuyChatGpt'))launchAi('chatgpt');if(e.target.closest('#analyzeBuyDuck'))launchAi('duck');});
