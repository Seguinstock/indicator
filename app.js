let RESULTS=null;

function formatLocalUpdate(value){
  if(!value)return '—';
  let raw=String(value).trim();
  if(/^\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}(:\d{2}(\.\d+)?)?$/.test(raw)) raw=raw.replace(' ','T')+'Z';
  const date=new Date(raw);
  if(Number.isNaN(date.getTime()))return value;
  return new Intl.DateTimeFormat('fr-CA',{year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',second:'2-digit',hour12:false}).format(date);
}
function escapeHtml(value){return String(value??'—').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[c]));}
function confidenceBadge(letter){const l=['A','B','C'].includes(letter)?letter:'C';return `<span class="confidence confidence-${l.toLowerCase()}">${l}</span>`;}
function filteredBuyRows(){
 if(!RESULTS)return[];
 const riskMax=100-Number(document.getElementById('riskSelectivity')?.value??0),timingMin=Number(document.getElementById('timingMin')?.value??0),healthMin=Number(document.getElementById('healthMin')?.value??0);
 const eligible=(RESULTS.buy||[]).filter(x=>Number(x.risk)<=riskMax&&Number(x.timing)>=timingMin&&Number(x.health)>=healthMin);
 const limit=30,v=RESULTS.parameter_snapshot?.visualisation||{},caPct=Number(v.min_canada_pct??30),usPct=Number(v.min_usa_pct??30);
 const minCA=Math.ceil(limit*Math.max(0,Math.min(100,caPct))/100),minUS=Math.ceil(limit*Math.max(0,Math.min(100,usPct))/100);
 const isCA=x=>x.country==='CA'||['XTSE','XTSX','XCNQ'].includes(x.market),isUS=x=>x.country==='US';
 const selected=[],seen=new Set();
 const add=x=>{if(x&&!seen.has(x.symbol)&&selected.length<limit){selected.push(x);seen.add(x.symbol)}};
 eligible.filter(isCA).slice(0,minCA).forEach(add);eligible.filter(isUS).slice(0,minUS).forEach(add);eligible.forEach(add);
 return selected.sort((x,y)=>Number(y.potential_score??y.score??0)-Number(x.potential_score??x.score??0));
}
function applyBuyFilters(){
 if(!RESULTS)return;
 const riskMax=100-Number(document.getElementById('riskSelectivity')?.value??0),timingMin=Number(document.getElementById('timingMin')?.value??0),healthMin=Number(document.getElementById('healthMin')?.value??0);
 document.getElementById('riskMaxValue').textContent=riskMax.toFixed(0);document.getElementById('timingMinValue').textContent=timingMin.toFixed(0);document.getElementById('healthMinValue').textContent=healthMin.toFixed(0);
 const rows=filteredBuyRows(),ca=rows.filter(x=>x.country==='CA'||['XTSE','XTSX','XCNQ'].includes(x.market)).length,us=rows.filter(x=>x.country==='US').length;
 const count=document.getElementById('buyFilterCount');if(count)count.textContent=`${rows.length} titres affichés · Canada ${ca} · États-Unis ${us} · glisser vers la droite = plus sélectif`;
 render('buyList',rows,'buy');
}
function setupBuyFilters(){
 const risk=document.getElementById('riskSelectivity'),timing=document.getElementById('timingMin'),health=document.getElementById('healthMin');
 const sr=localStorage.getItem('buyRiskSelectivity'),st=localStorage.getItem('buyTimingMin'),sh=localStorage.getItem('buyHealthMin');
 if(risk&&sr!==null)risk.value=sr;if(timing&&st!==null)timing.value=st;if(health&&sh!==null)health.value=sh;
 [[risk,'buyRiskSelectivity'],[timing,'buyTimingMin'],[health,'buyHealthMin']].forEach(([el,key])=>el&&el.addEventListener('input',()=>{localStorage.setItem(key,el.value);applyBuyFilters()}));applyBuyFilters();
}
function saveRankPdf(){
  const rows=filteredBuyRows();if(!rows.length){alert('Aucun titre affiché à enregistrer.');return;}
  const now=new Date(),yy=String(now.getFullYear()).slice(-2),mm=String(now.getMonth()+1).padStart(2,'0'),dd=String(now.getDate()).padStart(2,'0');const title=`Rank ${yy}-${mm}-${dd}`;
  const riskMax=100-Number(document.getElementById('riskSelectivity')?.value??0),timingMin=Number(document.getElementById('timingMin')?.value??0),healthMin=Number(document.getElementById('healthMin')?.value??0);
  const body=rows.map((x,i)=>`<tr><td>${i+1}</td><td><b>${escapeHtml(x.symbol)}</b></td><td>${escapeHtml(x.name||'—')}</td><td>${Number(x.potential_score??x.score).toFixed(1)}</td><td>${Number(x.timing).toFixed(1)}</td><td>${Number(x.risk).toFixed(1)}</td><td>${Number(x.health).toFixed(1)}</td><td>${x.price??'—'}</td></tr>`).join('');
  const w=window.open('','_blank');if(!w){alert('Le navigateur a bloqué la fenêtre PDF. Autorise les fenêtres surgissantes pour cette page.');return;}
  w.document.write(`<!doctype html><html><head><meta charset="utf-8"><title>${title}</title><style>@page{size:A4;margin:14mm}body{font-family:Arial,sans-serif;color:#111}h1{margin:0 0 5px;font-size:22px}.meta{font-size:12px;color:#555;margin-bottom:16px}table{width:100%;border-collapse:collapse;font-size:11px}th,td{padding:6px;border-bottom:1px solid #ddd;text-align:left}th{background:#f2f2f2}td:nth-child(1),td:nth-child(4),td:nth-child(5),td:nth-child(6){text-align:right}</style></head><body><h1>${title}</h1><div class="meta">Liste exacte affichée dans Tableau · Risque maxi ${riskMax} · Timing minimum ${timingMin} · Santé minimum ${healthMin} · ${rows.length} titres</div><table><thead><tr><th>Rang</th><th>Titre</th><th>Nom</th><th>Potentiel</th><th>Timing</th><th>Risque</th><th>Santé</th><th>Prix</th></tr></thead><tbody>${body}</tbody></table><script>window.onload=()=>{document.title='${title}';setTimeout(()=>window.print(),250)}<\/script></body></html>`);w.document.close();
}
async function loadResults(){const r=await fetch('data/results.json?'+Date.now(),{cache:'no-store'});const d=await r.json();RESULTS=d;document.getElementById('updated').textContent=`Mise à jour : ${formatLocalUpdate(d.updated)} · ${d.analyzed||0}/${d.universe||0} titres analysés`;setupBuyFilters();document.getElementById('saveRankPdf')?.addEventListener('click',saveRankPdf);const sel=document.getElementById('sellPortfolio');const portfolios=(d.portfolios&&d.portfolios.length)?d.portfolios:[{id:'michel',name:'Michel'},{id:'fils',name:'Loïc'}];sel.innerHTML=portfolios.map(p=>`<option value="${p.id}">${p.name}</option>`).join('');const saved=localStorage.getItem('sellPortfolio');if(saved&&portfolios.some(p=>p.id===saved))sel.value=saved;showSell();sel.addEventListener('change',()=>{localStorage.setItem('sellPortfolio',sel.value);showSell()});const refresh=document.getElementById('forceRefresh');if(refresh)refresh.addEventListener('click',()=>{const body=`STOCK_INDICATOR_REFRESH\n\nDemande de mise à jour forcée depuis Stock Indicator.`;const url=`https://github.com/Seguinstock/indicator/issues/new?title=${encodeURIComponent('Refresh Stock Indicator')}&body=${encodeURIComponent(body)}`;window.open(url,'_blank','noopener');});}
function showSell(){if(!RESULTS)return;const pid=document.getElementById('sellPortfolio')?.value||'michel';const rows=RESULTS.sell_by_portfolio?.[pid]??(pid==='michel'?RESULTS.sell||[]:[]);render('sellList',rows,'sell');}
function render(id,rows,type){
 const el=document.getElementById(id);el.innerHTML='';if(!rows.length){el.innerHTML=`<div class="empty">${type==='sell'?'Aucun titre détenu analysable dans ce portefeuille.':'Aucun titre ne respecte les seuils choisis.'}</div>`;return}
 rows.forEach(x=>{const row=document.createElement('details');row.className='stock';const cls=x.country==='CA'?'canada':x.country==='US'?'usa':'other',sale=type==='sell';
 const p=Number(x.potential_score??x.score),t=Number(x.timing),r=Number(x.risk),h=Number(x.health);
 const compact=`P: ${Number.isFinite(p)?p.toFixed(1):'—'} · T: ${Number.isFinite(t)?t.toFixed(1):'—'} ${confidenceBadge(x.timing_confidence)} · R: ${Number.isFinite(r)?r.toFixed(1):'—'} ${confidenceBadge(x.risk_confidence)} · S: ${Number.isFinite(h)?h.toFixed(1):'—'} ${confidenceBadge(x.health_confidence)}`;
 const fc=x.filter_components||{},raw=x.filter_raw||{};
 const families=(obj)=>Object.entries(obj||{}).map(([k,v])=>`<span class="check neutral">${escapeHtml(k)} ${Number(v)>=0?'+':''}${Number(v).toFixed(1)}</span>`).join('');
 row.innerHTML=`<summary><span class="symbol ${cls}">${x.symbol}</span><span class="score">${sale?`Score vente ${Number(x.score).toFixed(1)}`:compact}</span></summary><div class="detail"><div>Nom <b>${escapeHtml(x.name||x.symbol)}</b></div><div>Prix <b>${x.price??'—'}</b></div>${sale?`<div>Timing vente <b>${x.sell_timing_v14??'—'}</b></div><div>Signal <b>${x.sell_signal??'—'}</b></div>`:`<div>Score principal P <b>${Number.isFinite(p)?p.toFixed(1):'—'}</b></div><div>Timing T <b>${Number.isFinite(t)?t.toFixed(1):'—'} ${confidenceBadge(x.timing_confidence)}</b></div><div>Risque R <b>${Number.isFinite(r)?r.toFixed(1):'—'} ${confidenceBadge(x.risk_confidence)}</b></div><div>Santé S <b>${Number.isFinite(h)?h.toFixed(1):'—'} ${confidenceBadge(x.health_confidence)}</b></div><div>Force relative 20 j <b>${x.relative_strength_20_pct??'—'} %</b></div><div>Rendement 60 j <b>${x.return_60_pct??'—'} %</b></div><div>RSI <b>${x.rsi??'—'}</b></div><div>RVOL <b>${x.rvol??'—'}</b></div><div>Volatilité <b>${x.volatility_pct??'—'} %</b></div><div class="checks">${families(fc.timing)}${families(fc.risk)}${families(fc.health)}</div>`}</div>`;el.appendChild(row);
 });
}
loadResults().catch(e=>{document.getElementById('updated').textContent='Erreur de chargement';console.error(e)});
