'use strict';
let setupWizard=null, cleanupProposal=null, cleanupReview=null, cleanupTransfer=null;
const cleanupMethod={windows_recycle_bin:'Corbeille Windows',manual_android:'Retrait manuel sur Android',manual_local:'Retrait manuel contrôlé'};
async function renderSetup(){
 if(!setupWizard){const data=await api('/api/setup/discover');setupWizard={step:1,data,roots:[],protected_ack:false,destination:'',diagnostic:null,rules:structuredClone(data.config.archive_rules),themes:structuredClone(data.config.keyword_categories),automation:{...data.config.automation},run:null};}
 const w=setupWizard;
 const headings=['Supports accessibles','Dossiers personnels','Protections','Destination d’archivage','Catégories et règles','Première analyse'];
 let body='';
 if(w.step===1)body=`<h2>Vos fichiers restent sous votre contrôle.</h2><p class="help">Les supports sont détectés en lecture seule. Aucun fichier d’essai n’est créé. Le Seagate doit être identifié et diagnostiqué avant toute écriture.</p><div class="devices-grid">${w.data.volumes.map(v=>`<article class="device-card"><h3>${esc(v.path)}</h3><p class="help">${esc(v.filesystem)} · ${bytes(v.capacity||0)} · ${bytes(v.free||0)} libres</p><span class="badge ${v.accessible?'keep':''}">${v.accessible?'Accessible':'Inaccessible / unknown'}</span><button class="link-button" data-wizard-volume="${esc(v.path)}">Diagnostiquer ce support</button></article>`).join('')}</div><div id="wizard-volume-diagnostic"></div>`;
 if(w.step===2)body=`<h2>Choisir des dossiers personnels précis</h2><p class="help">Cochez des dossiers physiques contenant vos fichiers personnels. Les sources déjà autorisées restent conservées. Aucun disque entier, profil entier ni dossier applicatif n’est accepté.</p>${w.data.sources.map(r=>`<label class="source-choice"><input type="checkbox" data-wizard-source="${esc(r.path)}" data-label="${esc(r.label)}" ${w.roots.some(p=>p.path===r.path)?'checked':''} ${r.available?'':'disabled'}><span><strong>${esc(r.label)}</strong><small>${esc(r.path)}${r.reason?' · '+esc(r.reason):''}</small></span></label>`).join('')}<form id="wizard-source-form" class="form-inline"><label>Autre dossier personnel — chemin absolu<input name="path" required placeholder="C:\\Users\\VotreNom\\Pictures"></label><button type="submit" class="button secondary">Ajouter à l’assistant</button></form><p id="wizard-source-count" class="help">${w.roots.length} source(s) choisie(s)</p>`;
 if(w.step===3)body=`<h2>Les protections restent actives</h2><p class="help">Windows, programmes, jeux, données d’applications Android et dépendances ne seront pas analysés. Les liens, jonctions et noms sensibles sont exclus. Un média n’est jamais considéré supprimable à cause de son extension.</p><div class="tag-list">${w.data.protected_names.map(n=>`<span>${esc(n)}</span>`).join('')}</div><label class="force-option"><input type="checkbox" id="wizard-protection-ack" ${w.protected_ack?'checked':''}>Je confirme que les dossiers choisis contiennent mes fichiers personnels, hors système et applications.</label><p class="help">Cet assistant n’autorise aucun nettoyage. Les propositions de retrait nécessiteront une autorisation séparée par dossier.</p>`;
 if(w.step===4)body=`<h2>Vérifier le dossier de destination</h2><p class="help">Le dossier doit exister. Si le disque est « unknown », ne créez pas de dossier : revenez au diagnostic du support. Aucun formatage, initialisation ou réparation ne sera effectué.</p><form id="wizard-destination-form" class="form-inline"><label>Dossier d’archivage existant<input name="path" value="${esc(w.destination)}" placeholder="E:\\Archives"></label><button type="submit" class="button secondary">Vérifier la destination</button></form><div id="wizard-destination-diagnostic">${w.diagnostic?diagnostic(w.diagnostic):''}</div><label class="force-option"><input type="checkbox" id="wizard-no-archive" ${w.destination?'':'checked'}>Commencer par l’inventaire, sans destination d’archivage</label><p class="help">Aucune écriture sur la destination pendant l’assistant. Une archive sur un seul disque n’est pas une sauvegarde indépendante.</p>`;
 if(w.step===5)body=`<h2>Préparer le classement</h2><p class="help">Types techniques : images, vidéos, documents, audio, archives et autres. Les mots-clés personnalisent les étiquettes dans l’index ; les fichiers ne sont pas déplacés.</p><div id="wizard-themes">${Object.entries(w.themes).map(([name,words])=>`<div class="wizard-theme-row"><label>Catégorie<input class="wizard-theme-name" value="${esc(name)}" required></label><label>Mots-clés séparés par des virgules<input class="wizard-theme-words" value="${esc(words.join(', '))}" required></label></div>`).join('')}</div><h3 class="section-top">Règles d’archivage en simulation</h3><div id="wizard-rules">${w.rules.map(ruleRow).join('')}</div><label class="force-option"><input type="checkbox" id="wizard-auto" ${w.automation.enabled?'checked':''}>Activer les analyses et simulations périodiques (aucune copie automatique)</label><label>Intervalle en secondes<input id="wizard-interval" type="number" min="30" max="86400" value="${w.automation.interval_seconds}"></label>`;
 if(w.step===6)body=`<h2>Première analyse, sans modifier vos fichiers</h2><p>${w.roots.length} dossier(s) choisi(s) · exclusions actives · ${w.destination?'destination diagnostiquée':'inventaire uniquement'}</p><p class="help">L’analyse lit les fichiers, calcule leurs SHA-256 et classe l’inventaire. Aucune copie ni mise à la Corbeille n’est déclenchée.</p>${w.run?'<div id="wizard-results"></div>':'<button class="button primary" data-action="wizard-apply">Lancer ma première analyse</button>'}`;
 $('#view-content').innerHTML=`<section class="panel"><div class="wizard-steps">${headings.map((h,i)=>`<span class="${w.step===i+1?'active':''}">${i+1}. ${h}</span>`).join('')}</div>${body}<div class="wizard-navigation">${w.step>1&&!w.run?'<button class="button secondary" data-action="wizard-prev">Précédent</button>':''}${w.step<6?'<button class="button primary" data-action="wizard-next">Suivant</button>':''}</div></section>`;
 if(w.run)await refreshSetup();
}
function saveWizardStep(){
 const w=setupWizard;
 if(w.step===2&&!w.roots.length)throw new Error('Choisissez au moins un dossier personnel.');
 if(w.step===3){w.protected_ack=$('#wizard-protection-ack').checked;if(!w.protected_ack)throw new Error('Confirmez les protections des dossiers.');}
 if(w.step===4){if($('#wizard-no-archive').checked){w.destination='';w.diagnostic=null;}else if(!w.diagnostic?.safe_to_write)throw new Error('Vérifiez une destination saine ou commencez sans archivage.');}
 if(w.step===5){
  const interval=$('#wizard-interval');if(!interval.reportValidity())throw new Error('Intervalle invalide.');
  w.automation={enabled:$('#wizard-auto').checked,interval_seconds:Number(interval.value),destination:w.destination};
  w.rules=[...document.querySelectorAll('#wizard-rules .rule-row')].map(row=>({name:row.querySelector('[name=name]').value,category:row.querySelector('[name=category]').value,older_than_days:Number(row.querySelector('[name=days]').value),enabled:row.querySelector('[name=enabled]').checked}));
  w.themes=Object.fromEntries([...document.querySelectorAll('.wizard-theme-row')].map(row=>[row.querySelector('.wizard-theme-name').value.trim(),row.querySelector('.wizard-theme-words').value.split(',').map(v=>v.trim()).filter(Boolean)]));
 }
}
async function refreshSetup(){
 if(view!=='onboarding'||!setupWizard?.run||!$('#wizard-results'))return;
 const r=await api('/api/setup/result?id='+setupWizard.run.id);setupWizard.run=r;
 $('#wizard-results').innerHTML=`<div class="notice ${r.ready?'':'neutral'}"><p><strong>${esc(r.scan.message||r.scan.status)}</strong><br>${r.stats.files} fichiers dans l’inventaire · ${r.stats.duplicate_groups} groupes de doublons · ${bytes(r.stats.media_bytes)} de médias</p></div>${r.ready?`<button class="button primary" data-action="wizard-finish">Afficher les actions sécurisées</button>`:'<p class="help">Laissez l’analyse se terminer. Les erreurs restent consultables dans Historique.</p>'}`;
}
async function renderCleanup(){
 const jobs=state.transfers.filter(j=>j.verified>0);
 $('#view-content').innerHTML=notice('<strong>Le retrait est une opération séparée.</strong> Seules les copies actuellement vérifiées sont proposées. Autorisez d’abord le dossier comme personnel et autonome dans Dossiers autorisés / Appareils. Aucun original n’est retiré automatiquement.','warning')+`<section class="panel"><h2>Libérer l’espace après archivage</h2><p class="help">Windows : Corbeille lorsque le recyclage sûr est disponible ; le vidage reste manuel dans Windows. Android : retrait effectué par vous dans Galerie/Fichiers, puis contrôle de l’absence et de l’archive. La Corbeille ne libère l’espace qu’après vidage.</p><form id="cleanup-proposal-form" class="form-inline"><label>Transfert à revérifier<select name="transfer_id">${jobs.map(j=>`<option value="${j.id}" ${cleanupTransfer===j.id?'selected':''}>${date(j.created)} · ${j.verified} copie(s) vérifiée(s) · ${esc(j.destination)}</option>`).join('')}</select></label><button type="submit" class="button primary" ${jobs.length?'':'disabled'}>Revérifier et proposer un nettoyage</button></form><p class="help">La relecture complète des SHA-256 peut être longue. Cette vérification ne modifie ni source ni archive.</p><div id="cleanup-proposals"></div></section><div id="cleanup-jobs"></div>`;
 if(cleanupProposal)showCleanupCandidates(cleanupProposal);
 await refreshCleanupJobs();
}
function showCleanupCandidates(report){
 cleanupProposal=report;
 $('#cleanup-proposals').innerHTML=`${notice(esc(report.warning),'warning')}<h3>${report.items.length} fichiers éligibles · ${bytes(report.bytes)} potentiellement retirables</h3><div class="table-wrap"><table><thead><tr><th>Choix</th><th>Source personnelle</th><th>Archive revérifiée</th><th>Action</th></tr></thead><tbody>${report.items.map(i=>`<tr><td><input type="checkbox" class="cleanup-choice" data-id="${i.file_id}" aria-label="Choisir ${esc(i.source)}"></td><td class="file-path">${esc(i.source)}</td><td class="file-path">${esc(i.destination)}</td><td>${esc(cleanupMethod[i.method])}</td></tr>`).join('')}</tbody></table></div>${report.items.length?'<button class="button primary section-top" data-action="prepare-cleanup">Préparer le retrait sélectionné</button>':''}${report.excluded.length?`<details class="section-top"><summary>${report.excluded.length} fichier(s) exclu(s)</summary>${report.excluded.map(i=>`<p class="help">${esc(i.source)} : ${esc(i.reason)}</p>`).join('')}</details>`:''}`;
}
async function refreshCleanupJobs(){
 if(view!=='cleanup'||!$('#cleanup-jobs'))return;
 const names={running:'Retrait explicitement autorisé en cours',completed:'Terminé · voir les reçus',manual_required:'Action manuelle attendue',blocked:'Bloqué · consulter le motif',interrupted:'Interrompu · contrôle manuel requis'};
 $('#cleanup-jobs').innerHTML=`<section class="panel"><h2>Journal des retraits</h2>${state.cleanup.length?state.cleanup.map(j=>`<article class="transfer-card"><h3>${esc(names[j.status]||j.status)}</h3><p class="help">${date(j.created)} · ${esc(j.message)}</p>${j.items.map(i=>{let r={};try{r=JSON.parse(i.receipt);}catch{}return `<p class="file-path"><strong>${esc(i.source)}</strong><br>${esc(i.status)} · ${esc(i.message)}${r.recycled_path?`<br>Corbeille : ${esc(r.recycled_path)}<br>${esc(r.restoration_note||'')}`:''}${r.recovery_path?`<br>Fichier conservé sous : ${esc(r.recovery_path)}`:''}</p>`;}).join('')}${j.items.some(i=>i.status==='manual_required')?`<button class="button secondary" data-manual-cleanup="${j.id}">J’ai effectué le retrait manuel</button><p class="help">Dans Galerie ou Fichiers sur Android / dans votre gestionnaire local, sélectionnez uniquement les chemins indiqués. Contrôlez la destination et votre sauvegarde indépendante avant toute suppression. Aucun ordre ADB de suppression n’est envoyé.</p>`:''}</article>`).join(''):'<p class="help">Aucun retrait enregistré.</p>'}</section>`;
}
async function workflowClick(event){
 const el=event.target.closest('button');if(!el)return;
 if(el.dataset.wizardVolume){const info=await api('/api/storage/diagnose',{path:el.dataset.wizardVolume});$('#wizard-volume-diagnostic').innerHTML=diagnostic(info);return;}
 if(el.dataset.cleanupTransfer){cleanupTransfer=el.dataset.cleanupTransfer;cleanupProposal=null;location.hash='cleanup';return;}
 if(el.dataset.manualCleanup){$('#details-content').innerHTML=`<h2>Confirmer votre retrait manuel</h2><p>La destination doit rester accessible. L’application revérifiera son SHA-256 et l’absence de chaque source, sans envoyer d’ordre de suppression.</p><form id="manual-cleanup-form" data-id="${el.dataset.manualCleanup}"><label>Saisissez RETRAIT EFFECTUÉ<input name="confirmation" required pattern="RETRAIT EFFECTUÉ" autocomplete="off"></label><button class="button primary" type="submit">Contrôler le retrait</button></form>`;$('#details').showModal();return;}
 const action=el.dataset.action;
 if(action==='wizard-next'){saveWizardStep();setupWizard.step++;await renderSetup();}
 if(action==='wizard-prev'){setupWizard.step--;await renderSetup();}
 if(action==='wizard-apply'){
  el.disabled=true;try{setupWizard.run=await api('/api/setup/apply',{roots:setupWizard.roots,protected_ack:setupWizard.protected_ack,destination:setupWizard.destination,archive_rules:setupWizard.rules,keyword_categories:setupWizard.themes,automation:setupWizard.automation});await refreshState();await renderSetup();}finally{el.disabled=false;}
 }
 if(action==='wizard-finish'){
  const r=await api('/api/setup/finish',{id:setupWizard.run.id});await refreshState();
  $('#wizard-results').innerHTML=`${notice('<strong>Inventaire terminé.</strong> Aucun fichier personnel copié ou retiré pendant la configuration.')}<div class="toolbar"><a class="button secondary" href="#files">Explorer les ${r.stats.files} fichiers</a><a class="button secondary" href="#duplicates">Examiner les ${r.stats.duplicate_groups} groupes de doublons</a>${r.plan_id?`<button class="button primary" data-load-plan="${r.plan_id}">Voir les fichiers archivables</button>`:'<a class="button primary" href="#archive">Préparer une simulation</a>'}</div>`;setupWizard.finished=true;
 }
 if(action==='prepare-cleanup'){
  const ids=[...document.querySelectorAll('.cleanup-choice:checked')].map(c=>Number(c.dataset.id));
  cleanupReview=await api('/api/cleanup/prepare',{transfer_id:cleanupProposal.transfer_id,file_ids:ids});
  const native=cleanupReview.items.some(i=>i.method==='windows_recycle_bin');
  $('#details-content').innerHTML=`<h2>Confirmer le retrait après archivage</h2>${notice(esc(cleanupReview.warning),'warning')}<p>${cleanupReview.items.length} fichier(s) · ${bytes(cleanupReview.bytes)}</p><p class="help">${native?'Les fichiers Windows seront renommés temporairement pour contrôler leur identité, puis envoyés à la Corbeille. Si le recyclage est refusé, la remise en place est tentée sans écrasement. Le reçu indique tout chemin de récupération.':'Une procédure manuelle sera préparée. L’application n’exécutera aucune suppression Android ou Linux.'}</p><ul>${cleanupReview.items.map(i=>`<li class="file-path">${esc(i.source)} · ${esc(cleanupMethod[i.method])}</li>`).join('')}</ul><form id="cleanup-confirm-form"><label class="force-option"><input type="checkbox" id="cleanup-risk" required>Je comprends le risque de copie unique et j’ai vérifié ma sauvegarde indépendante ou j’accepte ce risque.</label><label>Saisissez NETTOYER<input name="confirmation" required pattern="NETTOYER" autocomplete="off"></label><button type="submit" class="button primary">Valider ce retrait précis</button></form>`;
  $('#details').showModal();
 }
}
async function workflowSubmit(event){
 const form=event.target;
 if(!['wizard-source-form','wizard-destination-form','cleanup-proposal-form','cleanup-confirm-form','manual-cleanup-form'].includes(form.id))return;
 event.preventDefault();const button=form.querySelector('button');button.disabled=true;
 try{
  if(form.id==='wizard-source-form'){
   const source=await api('/api/setup/source',{path:form.elements.path.value});
   if(!setupWizard.data.sources.some(r=>r.path===source.path))setupWizard.data.sources.push({...source,available:true});
   if(!setupWizard.roots.some(r=>r.path===source.path))setupWizard.roots.push(source);
   await renderSetup();
  }
  if(form.id==='wizard-destination-form'){
   const raw=form.elements.path.value;
   const info=await api('/api/storage/diagnose',{path:raw});setupWizard.diagnostic=info;setupWizard.destination=raw;
   $('#wizard-destination-diagnostic').innerHTML=diagnostic(info);$('#wizard-no-archive').checked=false;
  }
  if(form.id==='cleanup-proposal-form'){cleanupTransfer=form.elements.transfer_id.value;const report=await api('/api/cleanup/candidates?transfer_id='+cleanupTransfer);showCleanupCandidates(report);}
  if(form.id==='cleanup-confirm-form'){
   await api('/api/cleanup/start',{review_id:cleanupReview.review_id,confirmation:form.elements.confirmation.value,acknowledge_single_copy:$('#cleanup-risk').checked});$('#details').close();cleanupReview=null;cleanupProposal=null;await refreshState();await renderCleanup();
  }
  if(form.id==='manual-cleanup-form'){await api('/api/cleanup/manual',{id:form.dataset.id,confirmation:form.elements.confirmation.value});$('#details').close();await refreshState();await refreshCleanupJobs();}
 }finally{button.disabled=false;}
}
document.addEventListener('click',e=>{workflowClick(e).catch(error);});
document.addEventListener('submit',e=>{workflowSubmit(e).catch(error);});
document.addEventListener('change',e=>{
 const input=e.target;
 if(input.dataset.wizardSource){const path=input.dataset.wizardSource;setupWizard.roots=setupWizard.roots.filter(r=>r.path!==path);if(input.checked)setupWizard.roots.push({path,label:input.dataset.label,device:'Cet ordinateur'});$('#wizard-source-count').textContent=setupWizard.roots.length+' source(s) choisie(s)';}
 if(input.dataset.cleanupPermission){const enabled=input.checked;api('/api/cleanup/permission',{root_id:input.dataset.cleanupPermission,enabled,kind:input.dataset.kind||'local'}).then(refreshState).then(()=>toast('Autorisation de propositions de nettoyage mise à jour.')).catch(e=>{input.checked=!enabled;error(e);});}
});
