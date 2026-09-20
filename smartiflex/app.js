const $ = s => document.querySelector(s);
const csrf = $('meta[name="csrf-token"]').content;
let snapshot = null, entities = [], step = 1, device = null, sensor = null, pending = false, editing = null;
const names = {switch:'Bryter', climate:'Termostat', number:'Tallstyring'};
const words = value => new Set(value.toLocaleLowerCase('nb-NO').replace(/[_.-]/g,' ').split(/\s+/).filter(w => w.length > 2 && !['sensor','switch','climate','number','power','effekt'].includes(w)));
function score(a,b) { const tokens=words(a.name+' '+a.entity_id); return [...words(b.name+' '+b.entity_id)].filter(w=>tokens.has(w)).length; }
function message(text, error=false) { const el=$(error?'#error':'#notice'); el.textContent=text; el.hidden=!text; }
async function request(path,method='GET',body) {
  const r=await fetch('./'+path,{method,headers:{'Content-Type':'application/json','X-CSRF-Token':csrf},body:body===undefined?undefined:JSON.stringify(body)});
  const data=await r.json().catch(()=>null);
  if(!r.ok) throw Error(typeof data?.detail==='string'?data.detail:'Dette gikk ikke. Prøv igjen.');
  return data;
}
function controls(){
  document.querySelectorAll('button').forEach(b=>b.disabled=pending);
  $('#next').disabled=pending || (step===1?!device:step===2?!sensor:!$('#confirm').checked);
}
async function action(fn){
  if(pending)return; pending=true;message('',true);message('');controls();
  try{await fn();}catch(e){message(e.message,true);}finally{pending=false;controls();}
}
function choice(item, group, checked, description, suggested, select) {
  const label=document.createElement('label');label.className='choice';
  const radio=document.createElement('input');radio.type='radio';radio.name=group;radio.value=item.entity_id;radio.checked=checked;
  const copy=document.createElement('span');copy.className='choice-text';
  const title=document.createElement('strong');title.textContent=item.name;
  const sub=document.createElement('small');sub.textContent=description;
  copy.append(title,sub);
  if(suggested){const tag=document.createElement('span');tag.className='suggestion';tag.textContent='Mulig match · sjekk at den tilhører enheten';copy.append(tag);}
  label.title=item.entity_id;
  radio.onchange=()=>{select(item);controls();};label.append(radio,copy);return label;
}
function drawChoices(){
  const deviceQuery=$('#device-search').value.toLocaleLowerCase('nb-NO');
  const sensorQuery=$('#sensor-search').value.toLocaleLowerCase('nb-NO');
  const used=new Set((snapshot?.bindings||[]).filter(b=>b.local_id!==editing?.local_id).flatMap(b=>[b.entity_id,b.power_entity]));
  const ds=entities.filter(e=>names[e.domain]&&!used.has(e.entity_id)&&(e.name+' '+e.entity_id).toLocaleLowerCase('nb-NO').includes(deviceQuery));
  $('#devices').replaceChildren(...ds.map(e=>choice(e,'device',device?.entity_id===e.entity_id,names[e.domain],false,item=>{if(device?.entity_id!==item.entity_id)sensor=null;device=item;})));
  const ss=entities.filter(e=>['W','kW'].includes(e.unit)&&!used.has(e.entity_id)&&(e.name+' '+e.entity_id).toLocaleLowerCase('nb-NO').includes(sensorQuery)).sort((a,b)=>(device?score(device,b)-score(device,a):0)||a.name.localeCompare(b.name,'nb'));
  $('#sensors').replaceChildren(...ss.map(e=>choice(e,'sensor',sensor?.entity_id===e.entity_id,e.power_w===null?'Ingen fersk måling akkurat nå':`${e.power_w.toLocaleString('nb-NO')} W · nylig målt`,device&&score(device,e)>=2,item=>{sensor=item;})));
  for(const [selector,list,text] of [['#devices',ds,'Ingen enheter passer søket. Prøv et annet navn.'],['#sensors',ss,'Ingen ledige effektmålinger funnet. Legg til en effektsensor i W eller kW i Home Assistant først, og prøv igjen.']]){if(!list.length){const p=document.createElement('p');p.className='empty';p.textContent=text;$(selector).append(p);}}
}
function showStep(next){
  step=next;for(let i=1;i<=3;i++){$('#step-'+i).hidden=i!==step;const item=$(`[data-step="${i}"]`);if(i===step)item.setAttribute('aria-current','step');else item.removeAttribute('aria-current');}
  $('#back').hidden=step===1;$('#next').textContent=step===3?(editing?'Lagre endringer':'Legg til enheten'):'Neste';$('#step-status').textContent=`Steg ${step} av 3`;
  if(step===2){$('#sensor-intro').textContent=`Du har valgt ${device.name}. Velg målingen som viser hvor mye strøm den bruker akkurat nå.`;drawChoices();}
  if(step===3){$('#review').replaceChildren();const title=document.createElement('strong');title.textContent=device.name;const p=document.createElement('p');p.textContent='Effektmåling: '+sensor.name;$('#review').append(title,p);}
  controls();$('#step-'+step+' h2').focus();
}
async function start(binding=null){
  await action(async()=>{
    $('#add').textContent='Henter enheter …';
    try{
      entities=await request('entities');editing=binding;device=null;sensor=null;$('#reporting-mode').value=binding?.reporting_mode||'on_change';
      $('#device-search').value='';$('#sensor-search').value='';$('#confirm').checked=false;
      $('#wizard').hidden=false;
      if(binding){
        device=entities.find(e=>e.entity_id===binding.entity_id)||null;
        sensor=entities.find(e=>e.entity_id===binding.power_entity)||null;
        $('#device-name').value=binding.name;$('#power').value=binding.estimated_w;
        const duration=$('#duration');
        if(![...duration.options].some(o=>Number(o.value)===binding.max_duration_seconds))duration.add(new Option(`${binding.max_duration_seconds/60} minutter`,String(binding.max_duration_seconds)));
        duration.value=String(binding.max_duration_seconds);
        $('#power-help').textContent='Ditt lagrede effektanslag. Du kan endre det her.';
      }else{$('#duration').value='900';}
      $('#edit-note').hidden=!binding;
      drawChoices();showStep(binding&&device&&sensor?3:1);
      $('#wizard').scrollIntoView({behavior:'instant',block:'start'});
    }finally{$('#add').textContent='Legg til enhet ＋';}
  });
}
function close(){ $('#wizard').hidden=true;$('#add').focus(); }
function renderBindings(){
  const bindings=snapshot.bindings;$('#count').textContent=`${bindings.length} ${bindings.length===1?'enhet':'enheter'}`;$('#bindings').replaceChildren();
  if(!bindings.length){const p=document.createElement('p');p.className='empty';p.textContent='Ingen enheter lagt til ennå. Start med én du kjenner godt.';$('#bindings').append(p);}
  for(const b of bindings){const row=document.createElement('div');row.className='binding';const copy=document.createElement('div');const name=document.createElement('strong');name.textContent=b.name;const status=document.createElement('small');status.textContent=b.local_enabled?(b.device_id?'Koblet til SMARTi · deler målinger':'Venter på synkronisering med SMARTi'):'Deling pauset lokalt';const duration=document.createElement('small');duration.textContent=`Lokal grense: ${b.max_duration_seconds/60} minutter`;const diagnostic=document.createElement('small');diagnostic.textContent=b.measurement_status||'Venter på første måling.';const reading=document.createElement('small');reading.textContent=b.last_observed_at?`${b.last_power_w} W · målt ${new Date(b.last_observed_at).toLocaleString('nb-NO')}`:'';const edit=document.createElement('button');edit.className='quiet';edit.textContent='Rediger';edit.onclick=()=>start(b);const raw=document.createElement('small');raw.textContent=b.sensor_state!==undefined?`Home Assistant: ${b.sensor_state} ${b.sensor_unit||''} · ${b.sensor_observed_at?new Date(b.sensor_observed_at).toLocaleString('nb-NO'):'ukjent tidspunkt'}`:'';copy.append(name,status,duration,diagnostic,reading,raw);const actions=document.createElement('div');actions.className='binding-actions';actions.append(edit);const button=document.createElement('button');button.className='quiet';button.textContent=b.local_enabled?'Pause deling':'Gjenoppta deling';button.onclick=()=>action(async()=>{await request('bindings/'+b.local_id+'/participation','POST',{enabled:!b.local_enabled});await refresh();});actions.append(button);row.append(copy,actions);$('#bindings').append(row);}
}
async function refresh(){
  snapshot=await request('status');$('#loading').hidden=true;$('#setup').hidden=snapshot.paired;$('#connected').hidden=!snapshot.paired;
  $('#connection').textContent=snapshot.connection==='ONLINE'?'● Tilkoblet SMARTi · oppdatert '+new Date(snapshot.last_sync).toLocaleTimeString('nb-NO'):'Venter på kontakt med SMARTi';
  $('#server-address').textContent=snapshot.cloud_url||'';renderBindings();if(snapshot.error)message(snapshot.error,true);controls();
}
$('#add').onclick=()=>start();$('#cancel').onclick=close;$('#back').onclick=()=>showStep(step-1);
$('#device-search').oninput=drawChoices;$('#sensor-search').oninput=drawChoices;$('#confirm').onchange=controls;
$('#next').onclick=()=>{
  if(step<3){if(step===2&&!editing){$('#device-name').value=device.name;$('#power').value=String(Math.min(1000000,Math.max(0,sensor.power_w||0)));$('#power-help').textContent=sensor.power_w>0?'Forhåndsutfylt fra den ferske effektmålingen. Juster hvis du kjenner enhetens kapasitet.':'Ingen positiv, fersk effektmåling. Anslaget er satt til 0 til du kjenner kapasiteten.';}showStep(step+1);return;}
  const name=$('#device-name'),power=$('#power');if(!name.reportValidity()||!power.reportValidity())return;
  if(!name.value.trim()){message('Gi enheten et navn.',true);name.focus();return;}
  void action(async()=>{await request(editing?'bindings/'+editing.local_id+'/edit':'bindings','POST',{entity_id:device.entity_id,power_entity:sensor.entity_id,name:name.value.trim(),estimated_w:Number(power.value)||0,reporting_mode:$('#reporting-mode').value,max_duration_seconds:Number($('#duration').value)});close();await refresh();message(`${name.value.trim()} er ${editing?'oppdatert':'lagt til'}. Aktiver kommunikasjonstest i SMARTi-portalen når endringen er synkronisert.`);});
};
$('#pair').onsubmit=e=>{e.preventDefault();const form=e.currentTarget;void action(async()=>{await request('pair','POST',Object.fromEntries(new FormData(form)));form.reset();await refresh();message('Du er koblet til. Legg til den første enheten din.');});};
$('#disconnect').onclick=()=>{if(confirm('Fjerne tilkoblingen og de lokale enhetskoblingene? Trekk også tilbake tilgangen i SMARTi-portalen.'))void action(async()=>{await request('disconnect','POST');close();await refresh();});};
void refresh().catch(e=>{message(e.message,true);$('#loading').textContent='Kunne ikke hente status. Last siden på nytt.';});
setInterval(()=>{if(!pending&&!document.hidden)void refresh().catch(()=>message('Kunne ikke oppdatere status. Kontroller forbindelsen.',true));},15000);
