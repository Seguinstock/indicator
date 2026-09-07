const REPO='Seguinstock/indicator';
const ISSUE_BASE=`https://github.com/${REPO}/issues/new`;

function esc(s=''){return String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}
function parseCSV(text){
  const rows=[]; let row=[],cell='',q=false;
  for(let i=0;i<text.length;i++){
    const c=text[i],n=text[i+1];
    if(c==='"'&&q&&n==='"'){cell+='"';i++;continue}
    if(c==='"'){q=!q;continue}
    if(c===','&&!q){row.push(cell);cell='';continue}
    if((c==='\n'||c==='\r')&&!q){if(c==='\r'&&n==='\n')i++;row.push(cell);cell='';if(row.some(x=>x!==''))rows.push(row);row=[];continue}
    cell+=c;
  }
  if(cell||row.length){row.push(cell);rows.push(row)}
  if(!rows.length)return[];
  const h=rows.shift(); return rows.map(r=>Object.fromEntries(h.map((k,i)=>[k,r[i]??''])));
}
function issueUrl(title,payload){
  const body=`STOCK_INDICATOR_CONFIG\n\n\`\`\`json\n${JSON.stringify(payload,null,2)}\n\`\`\`\n\nModification demandée depuis Stock Indicator.`;
  return `${ISSUE_BASE}?title=${encodeURIComponent(title)}&body=${encodeURIComponent(body)}`;
}
function openChange(title,payload){window.open(issueUrl(title,payload),'_blank','noopener')}
async function getText(path){const r=await fetch(`${path}?v=${Date.now()}`,{cache:'no-store'});if(!r.ok)throw new Error(path);return r.text()}
async function getJSON(path){return JSON.parse(await getText(path))}
function notice(msg,bad=false){const el=document.getElementById('notice');if(el){el.textContent=msg;el.className=`notice ${bad?'bad':''}`}}

async function initWatchlist(){
  const rows=parseCSV(await getText('config/symbols.csv'));
  const list=document.getElementById('watchRows'),search=document.getElementById('watchSearch');
  function draw(){const q=(search.value||'').trim().toUpperCase();const shown=rows.filter(x=>!q||x.symbol.includes(q)).slice(0,250);document.getElementById('watchCount').textContent=`${rows.length} titres suivis`;list.innerHTML=shown.map(x=>`<div class="manage-row"><div><b class="${x.country==='CA'?'canada':x.country==='US'?'usa':'other'}">${esc(x.symbol)}</b><small>${esc(x.market)} · ${esc(x.country||'—')}</small></div><button class="danger" data-remove="${esc(x.symbol)}">Supprimer</button></div>`).join('')||'<div class="empty">Aucun résultat.</div>'}
  search.addEventListener('input',draw);draw();
  list.addEventListener('click',e=>{const s=e.target.dataset.remove;if(s)openChange(`Config: supprimer suivi ${s}`,{action:'remove_symbol',symbol:s})});
  document.getElementById('watchAdd').addEventListener('submit',e=>{e.preventDefault();const symbol=document.getElementById('newSymbol').value.trim().toUpperCase();const market=document.getElementById('newMarket').value;const country=document.getElementById('newCountry').value;if(!symbol)return;openChange(`Config: ajouter suivi ${symbol}`,{action:'add_symbol',symbol,market,country,enabled:true})});
}

async function initHoldings(){
  const portfolios=await getJSON('config/portfolios.json'),sel=document.getElementById('portfolioSelect');
  sel.innerHTML=portfolios.filter(x=>x.active).map(x=>`<option value="${esc(x.id)}">${esc(x.name)}</option>`).join('');
  async function load(){const p=portfolios.find(x=>x.id===sel.value)||portfolios[0];const rows=parseCSV(await getText(p.file));document.getElementById('holdingCount').textContent=`${rows.length} titres détenus`;document.getElementById('holdingRows').innerHTML=rows.map(x=>`<div class="manage-row"><div><b>${esc(x.symbol)}</b><small>${esc(x.name||'')}</small></div><button class="danger" data-remove="${esc(x.symbol)}">Supprimer</button></div>`).join('')||'<div class="empty">Aucun titre dans ce portefeuille.</div>';document.getElementById('portfolioName').textContent=p.name}
  sel.addEventListener('change',load);await load();
  document.getElementById('holdingRows').addEventListener('click',e=>{const s=e.target.dataset.remove;if(!s)return;const p=portfolios.find(x=>x.id===sel.value);openChange(`Config: retirer ${s} de ${p.name}`,{action:'remove_holding',portfolio:p.id,symbol:s})});
  document.getElementById('holdingAdd').addEventListener('submit',e=>{e.preventDefault();const p=portfolios.find(x=>x.id===sel.value);const symbol=document.getElementById('holdingSymbol').value.trim().toUpperCase();const name=document.getElementById('holdingName').value.trim();if(!symbol)return;openChange(`Config: ajouter ${symbol} à ${p.name}`,{action:'add_holding',portfolio:p.id,symbol,name})});
}
function pathGet(obj,path){return path.split('.').reduce((o,k)=>o?.[k],obj)}
async function initParameters(){
  const current=await getJSON('config/parameters.json'),meta=await getJSON('config/parameter_defaults.json'),root=document.getElementById('parameterRows');
  root.innerHTML=Object.entries(meta).map(([path,m])=>{const v=pathGet(current,path);return `<article class="param" data-path="${esc(path)}"><div class="param-head"><div><b>${esc(m.label)}</b></div><span>Défaut <strong>${m.default}</strong></span></div><div class="param-edit"><input type="number" value="${v}" min="${m.min}" max="${m.max}" step="${m.step}"><button class="apply">Appliquer</button><button class="secondary reset">Défaut</button></div><div class="effect"></div><details class="param-help"><summary>Explication</summary><div class="param-help-body"><p><b>Ce que ça mesure</b><br>${esc(m.description)}</p><p><b>Logique du filtre</b><br>${esc(m.logic)}</p><p><b>Si tu augmentes</b><br>${esc(m.higher)}</p><p><b>Si tu diminues</b><br>${esc(m.lower)}</p></div></details></article>`}).join('');
  function updateCard(card){const path=card.dataset.path,m=meta[path],v=Number(card.querySelector('input').value);let txt='Valeur de référence : réglage standard.';if(v>m.default)txt='Avec cette valeur : '+m.higher;else if(v<m.default)txt='Avec cette valeur : '+m.lower;card.querySelector('.effect').textContent=txt}
  root.querySelectorAll('.param').forEach(c=>{updateCard(c);c.querySelector('input').addEventListener('input',()=>updateCard(c));c.querySelector('.reset').addEventListener('click',()=>{c.querySelector('input').value=meta[c.dataset.path].default;updateCard(c)});c.querySelector('.apply').addEventListener('click',()=>{const path=c.dataset.path,value=Number(c.querySelector('input').value),m=meta[path];if(!Number.isFinite(value)||value<m.min||value>m.max){notice(`Valeur invalide pour ${m.label}.`,true);return}openChange(`Config: paramètre ${m.label}`,{action:'set_parameter',path,value})})});
  const tech=document.getElementById('technicalReference');tech.innerHTML=`RSI : ${current.indicators.rsi_period} périodes · RVOL : ${current.indicators.rvol_period} périodes · Zone de rebond : ${current.indicators.support_lookback} jours. Ces paramètres techniques restent verrouillés pour l'instant afin de ne pas modifier les formules pendant cette étape.`;
}

document.addEventListener('DOMContentLoaded',()=>{
  const page=document.body.dataset.page;
  const fn=page==='watchlist'?initWatchlist:page==='holdings'?initHoldings:page==='parameters'?initParameters:null;
  if(fn)fn().catch(e=>{console.error(e);notice('Erreur de chargement de la configuration.',true)})
});
