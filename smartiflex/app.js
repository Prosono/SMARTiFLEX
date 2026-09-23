const deviceKinds = {"HEAT_PUMP": "Varmepumpe", "EV_CHARGER": "Elbillader", "OVEN": "Panelovn / elektrisk ovn", "WATER_HEATER": "Varmtvannsbereder", "UNDERFLOOR_HEATING": "Varmekabler / gulvvarme", "BATTERY": "Batteri", "HVAC": "Ventilasjon / kjøling", "SAUNA": "Badstue", "GENERIC_LOAD": "Annen styrbar last"};
const $ = s => document.querySelector(s);
const csrf = $('meta[name="csrf-token"]').content;
let openedDevice = null;
let snapshot = null, entities = [], step = 1, device = null, sensor = null, pending = false, editing = null;
const names = {switch:'Bryter', climate:'Termostat', number:'Tallstyring'};
const words = value => new Set(value.toLocaleLowerCase('nb-NO').replace(/[_.-]/g,' ').split(/\s+/).filter(w => w.length > 2 && !['sensor','switch','climate','number','power','effekt'].includes(w)));
function score(a,b) { const tokens=words(a.name+' '+a.entity_id); return [...words(b.name+' '+b.entity_id)].filter(w=>tokens.has(w)).length; }
function message(text, error=false) { const el=$(error?'#error':'#notice'); el.textContent=text; el.hidden=!text; if ($('#device-dialog').open) { const feedback=$('#dialog-feedback'); feedback.textContent=text; feedback.hidden=!text; feedback.className=error?'feedback-error':''; } }
async function request(path,method='GET',body) {
  const r=await fetch('./'+path,{method,headers:{'Content-Type':'application/json','X-CSRF-Token':csrf},body:body===undefined?undefined:JSON.stringify(body)});
  const data=await r.json().catch(()=>null);
  if(!r.ok) throw Error(typeof data?.detail==='string'?data.detail:'Dette gikk ikke. Prøv igjen.');
  return data;
}
function controls(){
  document.querySelectorAll('button').forEach(b=>b.disabled=pending || b.dataset.unavailable==='true');
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
      $('#device-kind').value=binding&&deviceKinds[binding.kind]?binding.kind:'';
      $('#device-search').value='';$('#sensor-search').value='';$('#confirm').checked=true;
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
      drawChoices();showStep(1);
      $('#wizard').scrollIntoView({behavior:'instant',block:'start'});
    }finally{$('#add').textContent='Legg til enhet ＋';}
  });
}
function close(){ $('#wizard').hidden=true;$('#add').focus(); }
const iconPaths = {
  HEAT_PUMP:'M12 12c-6-1-7-6-3-8 4-2 5 4 3 8Zm0 0c4-5 9-3 8 1-1 4-6 3-8-1Zm0 0c2 6-2 9-5 6-3-3 1-7 5-6Z',
  EV_CHARGER:'M4 15V9l2-4h12l2 4v6M4 10h16M6 15v3M18 15v3M7 13h1M16 13h1M13 7l-2 4h3l-2 4',
  WATER_HEATER:'M12 3s-7 8-7 12a7 7 0 0 0 14 0c0-4-7-12-7-12Z',
  OVEN:'M4 5h16v15H4ZM7 8h10M8 11v6M12 11v6M16 11v6',
  UNDERFLOOR_HEATING:'M3 7c3-4 3 4 6 0s3 4 6 0 3 4 6 0M3 12c3-4 3 4 6 0s3 4 6 0 3 4 6 0M3 17c3-4 3 4 6 0s3 4 6 0 3 4 6 0',
  BATTERY:'M3 7h16v10H3ZM22 10v4M11 9l-2 3h4l-2 3',
  HVAC:'M3 8h12a3 3 0 1 0-3-3M3 12h16a3 3 0 1 1-3 3M3 16h5',
  SAUNA:'M5 20h14M7 16c-5-5 5-5 0-11M12 16c-5-5 5-5 0-11M17 16c-5-5 5-5 0-11',
  GENERIC_LOAD:'M8 3v5M16 3v5M6 8h12v3a6 6 0 0 1-12 0ZM12 17v4'
};
function deviceIcon(kind){
  const svg=document.createElementNS('http://www.w3.org/2000/svg','svg');
  for(const [key,value] of Object.entries({viewBox:'0 0 24 24',width:'28',height:'28',fill:'none',stroke:'currentColor','stroke-width':'1.6','stroke-linecap':'round','stroke-linejoin':'round','aria-hidden':'true'}))svg.setAttribute(key,value);
  const path=document.createElementNS(svg.namespaceURI,'path');path.setAttribute('d',iconPaths[kind]||iconPaths.GENERIC_LOAD);svg.append(path);return svg;
}
function hideDevice(){ $('#device-dialog').close(); }
$('#dialog-close').onclick=hideDevice;
$('#device-dialog').addEventListener('close',()=>{const id=openedDevice;openedDevice=null;[...document.querySelectorAll('.device-tile')].find(el=>el.dataset.id===id)?.focus();});
function renderBindings(){
  const focusedTile=document.activeElement?.classList.contains('device-tile')?document.activeElement.dataset.id:null;
  const bindings=snapshot.bindings;
  $('#count').textContent=`${bindings.length} ${bindings.length===1?'enhet':'enheter'}`;
  $('#bindings').replaceChildren();
  if(!bindings.length){const p=document.createElement('p');p.className='empty';p.textContent='Ingen enheter lagt til ennå. Start med én du kjenner godt.';$('#bindings').append(p);}
  if(openedDevice&&!bindings.some(b=>b.local_id===openedDevice))hideDevice();
  for(const b of bindings){
    const row=document.createElement('div');row.className='binding';
    const copy=document.createElement('div');
    const name=document.createElement('strong');name.textContent=b.name;
    const status=document.createElement('small');status.textContent=b.pending_remove?'Fjerning venter på synkronisering':b.portal_measurements_paused?'Måledeling pauset i SMARTi Flex':b.local_enabled?(b.device_id?'Koblet til SMARTi · deler målinger':'Venter på synkronisering med SMARTi'):'Deling pauset lokalt';
    const duration=document.createElement('small');duration.textContent='Måledeling, styring og tidsgrenser administreres i SMARTi Flex-portalen.';
    const diagnostic=document.createElement('small');diagnostic.textContent=b.measurement_status||'Venter på første måling.';
    const reading=document.createElement('small');reading.textContent=b.last_observed_at?`${b.last_power_w} W · målt ${new Date(b.last_observed_at).toLocaleString('nb-NO')}`:'';
    const raw=document.createElement('small');raw.textContent=b.sensor_state!==undefined?`Home Assistant: ${b.sensor_state} ${b.sensor_unit||''} · ${b.sensor_observed_at?new Date(b.sensor_observed_at).toLocaleString('nb-NO'):'ukjent tidspunkt'}`:'';
    const category=document.createElement('small');category.textContent=deviceKinds[b.kind]||'Velg enhetstype under Rediger';
    const actual=document.createElement('small');actual.textContent=haStatus(b.ha_status);
    copy.append(name,category,status,actual,duration,diagnostic,reading,raw);
    const control=(snapshot.controls||[]).find(c=>c.local_id===b.local_id);
    const controlStatus=document.createElement('small');controlStatus.className='control-status';
    controlStatus.textContent=control?.error || (control?`Styring pågår · tilbake senest ${new Date(control.expires_at).toLocaleTimeString('nb-NO')}`:['switch','climate'].includes(b.entity_id?.split('.')[0])?'Styring følger tillatelsene i SMARTi Flex. Tidligere tilstand gjenopprettes ved slutt.':'Styring av denne enhetstypen støttes ikke ennå. Målinger deles.');
    if(control?.error)controlStatus.classList.add('control-fault');
    copy.append(controlStatus);
    const actions=document.createElement('div');actions.className='binding-actions';
    const remove=document.createElement('button');remove.className='quiet';remove.textContent=b.pending_remove?'Fjerning venter på forbindelse':'Fjern enhet';remove.dataset.unavailable=String(!!b.pending_remove);
    remove.onclick=()=>{if(confirm(`Fjerne ${b.name} fra SMARTi Flex-appen? Måledeling og styring stoppes. Enheten i Home Assistant og tidligere historikk beholdes.`))void action(async()=>{await request('bindings/'+b.local_id+'/remove','POST');await refresh();message('Enheten er stoppet lokalt. Frakoblingen synkroniseres med SMARTi Flex.');});};
    const edit=document.createElement('button');edit.textContent='Endre enhet og effektsensor';
    edit.onclick=()=>{hideDevice();void start(b);};
    actions.append(edit,remove);
    row.append(copy,actions);
    const tile=document.createElement('button');tile.className='device-tile';tile.dataset.id=b.local_id;tile.setAttribute('aria-haspopup','dialog');tile.setAttribute('aria-label',b.name+' – åpne innstillinger');
    const top=document.createElement('span');top.className='device-tile-top';const arrow=document.createElement('span');arrow.textContent='↗';arrow.setAttribute('aria-hidden','true');top.append(deviceIcon(b.kind),arrow);
    const kind=document.createElement('span');kind.className='device-tile-kind';kind.textContent=deviceKinds[b.kind]||'Enhet';
    const title=document.createElement('strong');title.className='device-tile-name';title.textContent=b.name;
    const state=document.createElement('span');state.className='device-tile-status';
    const recentUpload=b.last_upload_at && Date.now()-Date.parse(b.last_upload_at)<120000;
    state.textContent=b.pending_remove?'● Fjernes':b.portal_measurements_paused?'● Måledeling pauset':control?.error?'● Styring trenger oppfølging':control?'● Av/på-test pågår':!b.local_enabled?'● Deling pauset':!b.device_id||b.needs_sync?'● Venter på synkronisering':snapshot.connection!=='ONLINE'?'● Venter på forbindelse':recentUpload?'● Deler målinger':'● Sjekk målestatus';
    if(!b.portal_measurements_paused&&!b.pending_remove&&recentUpload&&b.local_enabled&&snapshot.connection==='ONLINE'&&!control&&!b.needs_sync)state.classList.add('active');
    const bottom=document.createElement('span');bottom.className='device-tile-bottom';
    const power=document.createElement('span');const label=document.createElement('small');label.textContent='Siste kjente effekt';const value=document.createElement('strong');value.textContent=typeof b.last_power_w==='number'&&Number.isFinite(b.last_power_w)?(b.last_power_w/1000).toLocaleString('nb-NO',{maximumFractionDigits:3})+' kW':'–';power.append(label,value);
    const hint=document.createElement('span');hint.className='device-tile-hint';hint.textContent='Innstillinger';bottom.append(power,hint);tile.append(top,kind,title,state,actual.cloneNode(true),bottom);
    tile.onclick=()=>{openedDevice=b.local_id;$('#dialog-feedback').hidden=true;$('#device-dialog-title').textContent=b.name;$('#device-details').replaceChildren(row);$('#device-dialog').showModal();};
    $('#bindings').append(tile);
    if(focusedTile===b.local_id)tile.focus();
    if(openedDevice===b.local_id){
      // Preserve keyboard focus across the periodic status refresh.
      const buttons=[...$('#device-details').querySelectorAll('button')];const focused=buttons.indexOf(document.activeElement);
      $('#device-dialog-title').textContent=b.name;$('#device-details').replaceChildren(row);
      if(focused>=0)row.querySelectorAll('button')[focused]?.focus();
    }
  }
}
async function refresh(){
  snapshot=await request('status');$('#loading').hidden=true;$('#setup').hidden=snapshot.paired;$('#connected').hidden=!snapshot.paired;
  $('#connection').textContent=snapshot.connection==='ONLINE'?'● Tilkoblet SMARTi · oppdatert '+new Date(snapshot.last_sync).toLocaleTimeString('nb-NO'):'Venter på kontakt med SMARTi';
  $('#server-address').textContent=snapshot.cloud_url||'';renderBindings();const fault=(snapshot.controls||[]).find(c=>c.error);if(fault)message(fault.error,true);else if(snapshot.error)message(snapshot.error,true);controls();
}
$('#add').onclick=()=>start();$('#cancel').onclick=close;$('#back').onclick=()=>showStep(step-1);
$('#device-search').oninput=drawChoices;$('#sensor-search').oninput=drawChoices;$('#confirm').onchange=controls;
$('#next').onclick=()=>{
  if(step<3){if(step===2&&!editing){$('#device-name').value=device.name;$('#power').value=String(Math.min(1000000,Math.max(0,sensor.power_w||0)));$('#power-help').textContent=sensor.power_w>0?'Forhåndsutfylt fra den ferske effektmålingen. Juster hvis du kjenner enhetens kapasitet.':'Ingen positiv, fersk effektmåling. Anslaget er satt til 0 til du kjenner kapasiteten.';}showStep(step+1);return;}
  const name=$('#device-name'),power=$('#power');if(!name.reportValidity()||!$('#device-kind').reportValidity()||!power.reportValidity())return;
  if(!name.value.trim()){message('Gi enheten et navn.',true);name.focus();return;}
  void action(async()=>{await request(editing?'bindings/'+editing.local_id+'/edit':'bindings','POST',{entity_id:device.entity_id,power_entity:sensor.entity_id,name:name.value.trim(),kind:$('#device-kind').value,estimated_w:Number(power.value)||0,reporting_mode:$('#reporting-mode').value,max_duration_seconds:Number($('#duration').value)});close();await refresh();message(`${name.value.trim()} er ${editing?'oppdatert':'lagt til'}. Administrer måledeling og styring i SMARTi Flex-portalen.`);});
};
$('#pair').onsubmit=e=>{e.preventDefault();const form=e.currentTarget;void action(async()=>{await request('pair','POST',Object.fromEntries(new FormData(form)));form.reset();await refresh();message('Du er koblet til. Legg til den første enheten din.');});};
$('#disconnect').onclick=()=>{if(confirm('Fjerne tilkoblingen og de lokale enhetskoblingene? Trekk også tilbake tilgangen i SMARTi-portalen.'))void action(async()=>{await request('disconnect','POST');close();await refresh();});};
void refresh().catch(e=>{message(e.message,true);$('#loading').textContent='Kunne ikke hente status. Last siden på nytt.';});
setInterval(()=>{if(!pending&&!document.hidden)void refresh().catch(()=>message('Kunne ikke oppdatere status. Kontroller forbindelsen.',true));},15000);

function haStatus(status){
  if(!status)return 'Enhetsstatus venter på Home Assistant';
  const labels={on:'På',off:'Av',heat:'Varmemodus',cool:'Kjølemodus',heating:'Varmer',cooling:'Kjøler',idle:'Hviler',auto:'Automatisk',unavailable:'Utilgjengelig',unknown:'Ukjent'};
  const value=status.state==='off'?'off':status.action||status.state;
  return (Date.now()-Date.parse(status.checked_at)>90000?'Sist kjent: ':'Status: ')+(labels[value]||value);
}
