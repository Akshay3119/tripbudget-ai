'use strict';
const $ = id => document.getElementById(id);
const money = cents => new Intl.NumberFormat('en-US', {style:'currency',currency:'USD'}).format(cents/100);
let token = sessionStorage.getItem('tripbudget-token') || '';
let episode = sessionStorage.getItem('tripbudget-episode') || '';
let current = null, catalog = null, prefVersion = 0, busy = false;
const seen = new Set();
const key = () => crypto.randomUUID();
function el(tag, text, cls) { const node=document.createElement(tag); if(text!==undefined)node.textContent=text; if(cls)node.className=cls; return node; }
function status(text) { $('status-message').textContent=text; }
function setBusy(value) { busy=value; $('plan-button').disabled=value; $('plan-button').textContent=value?'Checking your plan…':'Build our itinerary ↗'; }
async function api(path, options={}) {
  const response=await fetch(path, {...options, headers:{'Content-Type':'application/json',Authorization:'Bearer '+token,...options.headers}});
  if(!response.ok){const error=await response.json().catch(()=>({message:'Request failed'}));if(response.status===401){token='';sessionStorage.removeItem('tripbudget-token');$('login-dialog').showModal();}throw new Error(error.message || error.error);}
  return response.json();
}
async function signedIn() {
  const meta=await api('/api/meta');
  $('account').textContent='Studio connected · '+meta.role;
  $('build-info').textContent=`Release ${meta.version} · ${meta.revision} · boot ${meta.boot_id}`;
  $('test-controls').classList.toggle('hidden',!['admin','evaluation'].includes(meta.role));
  catalog=await api('/api/catalog');
  const preference=await api('/api/preferences'); prefVersion=preference.version;
  if(preference.data){$('diet').value=preference.data.diet;$('walking').value=preference.data.maximum_walk_meters;$('preference-status').textContent='Confirmed preferences loaded · version '+prefVersion;}
  if(episode){await refresh(); await loadEvents();}
}
$('account').addEventListener('click',()=>{$('login-dialog').showModal();});
$('close-login').addEventListener('click',()=>$('login-dialog').close());
$('login-form').addEventListener('submit',async event=>{event.preventDefault();$('login-error').textContent='';try{const result=await api('/api/login',{method:'POST',body:JSON.stringify({username:$('username').value,password:$('password').value})});token=result.token;sessionStorage.setItem('tripbudget-token',token);$('password').value='';$('login-dialog').close();await signedIn();}catch(error){$('login-error').textContent=error.message;}});
$('firebase-signin').addEventListener('click',async()=>{token=$('firebase-token').value.trim();sessionStorage.setItem('tripbudget-token',token);$('firebase-token').value='';try{await signedIn();$('login-dialog').close();}catch(error){$('login-error').textContent=error.message;}});
const start=new Date();start.setDate(start.getDate()+3);$('start-date').value=start.toLocaleDateString('en-CA');
const maxDate=new Date();maxDate.setDate(maxDate.getDate()+90);$('start-date').max=maxDate.toLocaleDateString('en-CA');
const minDate=new Date();minDate.setDate(minDate.getDate()+1);$('start-date').min=minDate.toLocaleDateString('en-CA');
$('trip-form').addEventListener('submit',async event=>{
  event.preventDefault();if(busy)return;if(!token){$('login-dialog').showModal();return;}
  status('');seen.clear();$('trace-list').replaceChildren();$('ledger-banner').classList.add('hidden');
  current=null;$('approval-card').classList.add('hidden');$('trip-results').classList.add('hidden');$('empty-state').classList.remove('hidden');updateBudget(0,null);
  const cities=[...document.querySelectorAll('input[name=city]:checked')].map(x=>x.value);
  const count=Number($('travelers').value), cap=Math.round(Number($('budget').value)*100);
  const request={start_date:$('start-date').value,days:Number($('days').value),cities,
    travelers:Array.from({length:count},(_,i)=>({id:'t'+(i+1),budget_cents:cap,diet:$('diet').value,maximum_walk_meters:Number($('walking').value)})),
    meal_cents:Math.round(Number($('meal').value)*100),lodging_standard_cents:Math.round(Number($('room-standard').value)*100),
    lodging_economy_cents:Math.round(Number($('room-economy').value)*100),room_capacity:Number($('room-capacity').value),
    estimates_confirmed:$('estimate-consent').checked,request:$('trip-request').value};
  try{setBusy(true);const result=await api('/api/episodes',{method:'POST',headers:{'Idempotency-Key':key()},body:JSON.stringify(request)});episode=result.id;sessionStorage.setItem('tripbudget-episode',episode);await run();}catch(error){status(error.message);}finally{setBusy(false);}
});
function updateBudget(total,totals) {
  $('group-total').textContent=money(total);
  const cap=current?.request?.travelers.reduce((sum,t)=>sum+t.budget_cents,0)||Number($('budget').value)*100*Number($('travelers').value);
  const percentage=cap?Math.round(total/cap*100):0;
  $('budget-percent').textContent=percentage+'%';$('budget-fill').style.width=Math.min(100,percentage)+'%';
  $('budget-fill').style.background=percentage>100?'#ef9b71':'#d8ef7a';
  $('budget-context').textContent=totals?Object.values(totals).map(money).join(' · ')+' per traveler':'Declared group cap '+money(cap);
}
const titles={admitted:'Request accepted',preferences_loaded:'Cross-session memory',model_request:'Model selected',model_result:'Model completed',model_failure:'Provider attempt failed',retrieval:'Evidence retrieved',query_rewritten:'Query refined',plan_proposed:'Supervisor proposal',specialist_observation:'Specialist observation',catalog_facts_read:'Source facts checked',critic:'Deterministic verification',approval_pending:'Paused for your approval',human_decision:'Human decision recorded',ledger_committed:'Ledger saved once',terminal:'Planning outcome',mcp_search:'Live MCP discovery'};
function trace(row) {
  if(seen.has(row.id))return;seen.add(row.id);const data=row.data;
  const node=el('article',undefined,'trace-item');node.append(el('span',String(seen.size).padStart(2,'0')));
  const content=el('div');content.append(el('strong',titles[row.kind]||row.kind));
  let detail='';
  if(row.kind==='model_request'||row.kind==='model_result'||row.kind==='model_failure'){
    detail=`${data.provider.toUpperCase()} · ${data.task} · ${data.model}`;
    if(row.kind==='model_result'){detail+=` · ${(data.latency_ms/1000).toFixed(2)}s`;$('model-badge').textContent=data.provider.toUpperCase()+' · COMPLETED';}
    if(data.error)detail+=' · '+data.error;
  }else if(row.kind==='critic'){
    detail=`Pass ${data.pass} · ${money(data.total_cents)} · ${data.valid?'All constraints passed':data.violations.map(v=>v.code).join(', ')}`;
    updateBudget(data.total_cents,data.traveler_totals);
  }else if(row.kind==='retrieval'){detail=`${data.city} · round ${data.round} · ${data.chunks.length} chunks · ${data.relevant?'coverage sufficient':'refinement needed'}`;}
  else if(row.kind==='preferences_loaded'){detail=data.applied?'Applied confirmed preference version '+data.version:'No confirmed preferences applied.';}
  else if(row.kind==='plan_proposed'){detail=`Pass ${data.pass} · ${data.choice.lodging_tier} lodging · ${data.choice.explanation}`;}
  else if(row.kind==='specialist_observation'){detail=data.agent+' · '+data.observation;}
  else if(row.kind==='query_rewritten'){detail=data.query;}
  else if(row.kind==='terminal'){detail=data.outcome+(data.message?' · '+data.message:'');}
  else if(row.kind==='human_decision'){detail=data.action+' · revision '+data.revision;}
  else if(row.kind==='approval_pending'){detail='Revision '+data.revision+' · hash-bound decision required';}
  else if(row.kind==='mcp_search'){detail='Actual tavily_search result · untrusted discovery';}
  else {detail='Recorded in the durable execution trail.';}
  content.append(el('p',detail));const raw=el('details');raw.append(el('summary','Inspect event'));raw.append(el('pre',JSON.stringify(data,null,2)));content.append(raw);node.append(content);
  const list=$('trace-list');list.querySelector('.trace-placeholder')?.remove();list.append(node);list.scrollTop=list.scrollHeight;
}
async function loadEvents(){if(!episode)return;const rows=await api(`/api/episodes/${episode}/events`);rows.forEach(trace);}
async function run(){
  setBusy(true);$('state-badge').textContent='PLANNING IN PROGRESS';$('recover').classList.add('hidden');
  try{
    const response=await fetch(`/api/episodes/${episode}/run`,{method:'POST',headers:{'Content-Type':'application/json',Authorization:'Bearer '+token,'Idempotency-Key':key()},body:JSON.stringify({simulate_cloud_429:$('simulate-429').checked,repair_enabled:true})});
    if(!response.ok){const error=await response.json();throw new Error(error.message||'Run failed');}
    const reader=response.body.getReader(),decoder=new TextDecoder();let pending='';
    while(true){const {done,value}=await reader.read();if(done)break;pending+=decoder.decode(value,{stream:true});let boundary;while((boundary=pending.indexOf('\n\n'))!==-1){const frame=pending.slice(0,boundary);pending=pending.slice(boundary+2);const type=frame.split('\n').find(x=>x.startsWith('event: '))?.slice(7);const raw=frame.split('\n').filter(x=>x.startsWith('data: ')).map(x=>x.slice(6)).join('\n');if(!raw)continue;const data=JSON.parse(raw);if(type==='trace')trace(data);if(type==='failure')status(data.error+' · '+data.message);}}
    await refresh();
  }catch(error){status(error.message);$('recover').classList.remove('hidden');}finally{setBusy(false);}
}
async function refresh(){
  if(!episode)return;current=await api(`/api/episodes/${episode}`);$('state-badge').textContent=current.status.replaceAll('_',' ');
  const proposal=current.proposal;$('approval-card').classList.toggle('hidden',current.status!=='PENDING_APPROVAL');$('ledger-banner').classList.toggle('hidden',current.status!=='COMMITTED');
  if(current.approval){$('approval-text').textContent=`Revision ${current.approval.revision} · expires ${new Date(current.approval.expires_at).toLocaleTimeString()}`;$('proposal-hash').textContent='Exact proposal SHA-256 · '+current.approval.hash;}
  if(!proposal){$('recover').classList.toggle('hidden',['NEW','CANCELLED','PROVEN_INFEASIBLE','NO_FEASIBLE_PLAN_FOUND'].includes(current.status));return;}
  $('empty-state').classList.add('hidden');$('trip-results').classList.remove('hidden');updateBudget(proposal.total_cents,proposal.traveler_totals);
  $('traveler-totals').replaceChildren(...Object.entries(proposal.traveler_totals).map(([id,cents])=>el('span',id.toUpperCase()+' · '+money(cents),'traveler-pill')));
  $('evidence-version').textContent='Catalog '+proposal.corpus_version;
  const days=new Map();for(const item of proposal.schedule){if(!days.has(item.day))days.set(item.day,[]);days.get(item.day).push(item);}
  const cards=[];for(const [day,items] of days){const card=el('article',undefined,'day-card'),header=el('div',undefined,'day-header');header.append(el('strong',`Day ${day+1} · ${items[0].city}`));header.append(el('span',new Date(items[0].start).toLocaleDateString('en-US',{timeZone:'America/New_York',month:'short',day:'numeric'})));card.append(header);
    for(const item of items){const activity=el('div',undefined,'activity');activity.append(el('span',new Date(item.start).toLocaleTimeString('en-US',{timeZone:'America/New_York',hour:'numeric',minute:'2-digit'})));const body=el('div');const title=catalog?.activities.find(x=>x.id===item.activity_id)?.title||item.activity_id.replaceAll('-',' ');body.append(el('strong',title));body.append(el('p',`${Math.round((new Date(item.end)-new Date(item.start))/60000)} min · ${item.walk_meters}m walk · planning window/transfer estimate`));activity.append(body);card.append(activity);}cards.push(card);}
  $('itinerary').replaceChildren(...cards);
  $('cost-rows').replaceChildren(...proposal.cost_items.map(item=>{const row=el('tr');row.append(el('td',item.description));row.append(el('td',`${item.quantity} × ${money(item.unit_cents)}`));row.append(el('td',money(item.total_cents)));const evidence=el('td');evidence.append(el('span',item.evidence_state==='VERIFIED_SNAPSHOT'?'REVIEWED SOURCE':'CONFIRMED ESTIMATE','evidence-tag'+(item.evidence_state==='VERIFIED_SNAPSHOT'?' verified':'')));row.append(evidence);return row;}));
  $('cost-buffer').textContent=`Base ${money(proposal.subtotal_cents)} + 10% contingency ${money(proposal.buffer_cents)} = ${money(proposal.total_cents)}. ${proposal.scope}`;
}
async function decide(action,newBudget){if(!current?.approval)return;const body={action,proposal_hash:current.approval.hash,revision:current.approval.revision};if(newBudget!==undefined)body.new_budget_cents=newBudget;
  try{status('');await api(`/api/approvals/${current.approval.id}/decision`,{method:'POST',headers:{'Idempotency-Key':key()},body:JSON.stringify(body)});await run();}catch(error){status(error.message);}}
$('approve').addEventListener('click',()=>decide('approve'));
$('reject').addEventListener('click',()=>decide('reject'));
$('cancel').addEventListener('click',()=>decide('cancel'));
$('edit').addEventListener('click',()=>{$('new-budget').value=Number($('budget').value)-50;$('edit-dialog').showModal();});
$('close-edit').addEventListener('click',()=>$('edit-dialog').close());
$('edit-form').addEventListener('submit',event=>{event.preventDefault();$('edit-dialog').close();decide('edit',Math.round(Number($('new-budget').value)*100));});
$('recover').addEventListener('click',()=>run());
$('save-preference').addEventListener('click',async()=>{try{if(!token){$('login-dialog').showModal();return;}const result=await api('/api/preferences/confirm',{method:'POST',body:JSON.stringify({group_id:'demo-group',expected_version:prefVersion,values:{diet:$('diet').value,maximum_walk_meters:Number($('walking').value),preferred_categories:[]},confirmed:true})});prefVersion=result.version;$('preference-status').textContent='Confirmed and saved · version '+prefVersion;status('Group preferences saved durably. A new session can load them.');}catch(error){status(error.message);}});
$('normalize-note').addEventListener('click',async()=>{const button=$('normalize-note');button.disabled=true;try{const result=await api('/api/notes/normalize',{method:'POST',body:JSON.stringify({note:$('private-note').value})});$('private-note').value='';$('note-result').textContent=JSON.stringify(result.candidate,null,2)+'\nNot saved. Review the fields above, then confirm explicitly.';$('diet').value=result.candidate.diet;$('walking').value=result.candidate.maximum_walk_meters;}catch(error){$('note-result').textContent=error.message;}finally{button.disabled=false;}});
$('sources-open').addEventListener('click',async()=>{try{if(!token){$('login-dialog').showModal();return;}catalog=await api('/api/catalog');$('sources-list').replaceChildren(...catalog.sources.map(source=>{const node=el('div',undefined,'source-record');node.append(el('strong',source.publisher+' · '+source.source_id));const link=el('a',source.url);link.href=source.url;link.target='_blank';link.rel='noopener noreferrer';node.append(link);node.append(el('small',source.fetch_status+' · captured '+source.fetched_at));node.append(el('p',source.excerpt||'No verified source excerpt. Estimates stay labeled.'));return node;}));$('sources-dialog').showModal();}catch(error){status(error.message);}});
$('close-sources').addEventListener('click',()=>$('sources-dialog').close());
$('discover').addEventListener('click',async()=>{if(!episode){status('Create a trip first.');return;}try{await api(`/api/episodes/${episode}/discover`,{method:'POST',body:'{}'});await loadEvents();status('Live MCP discovery completed. New results remain untrusted.');}catch(error){status(error.message);}});
if(token)signedIn().catch(error=>status(error.message));
