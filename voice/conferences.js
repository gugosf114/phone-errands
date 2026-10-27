// A dedicated Twilio room preserves the business call through human takeover and AI return.
const fs=require('fs');const path=require('path');const crypto=require('crypto');
const jobs=require('./jobs.js');
const ROOT=process.env.ASSISTANT_DATA_DIR||'/root/.local/state/phone-errands';
const DIR=path.join(ROOT,'conferences');fs.mkdirSync(DIR,{recursive:true,mode:0o700});
const SETTINGS='/root/.twilio/voice-api.json';
const locks=new Map();
function serial(id,action){
 const prior=locks.get(id)||Promise.resolve();
 const next=prior.catch(()=>{}).then(action);locks.set(id,next);
 next.finally(()=>{if(locks.get(id)===next)locks.delete(id);}).catch(()=>{});return next;
}
function settings(){
 if(!fs.existsSync(SETTINGS))return {enabled:false};
 return JSON.parse(fs.readFileSync(SETTINGS,'utf8'));
}
function available(){const c=settings();return Boolean(c.enabled&&c.accountSid&&c.authToken&&c.conferenceNumber);}
function config(){const c=settings();if(!available())throw new Error('The conference phone account is not configured.');return c;}
function base(){return 'https://'+fs.readFileSync('/root/.vapi/bridge/ngrok_domain.txt','utf8').trim();}
function file(id){if(!/^[a-f0-9]{24}$/.test(String(id)))throw new Error('Invalid room ID');return path.join(DIR,id+'.json');}
function read(id){return JSON.parse(fs.readFileSync(file(id),'utf8'));}
function save(room){room.updatedAt=new Date().toISOString();fs.writeFileSync(file(room.id)+'.tmp',JSON.stringify(room,null,2),{mode:0o600});fs.renameSync(file(room.id)+'.tmp',file(room.id));}
function all(){return fs.readdirSync(DIR).filter(n=>n.endsWith('.json')).map(n=>read(n.slice(0,-5)));}
function publicRoom(room){const {request,allowedFrom,...data}=room;return data;}
function list(){return all().map(publicRoom);}
async function twilio(method,resource,params){
 const c=config();const body=params?new URLSearchParams(Object.entries(params).map(([k,v])=>[k,String(v)])):undefined;
 const r=await fetch('https://api.twilio.com/2010-04-01/Accounts/'+c.accountSid+'/'+resource,{method,headers:{Authorization:'Basic '+Buffer.from(c.accountSid+':'+c.authToken).toString('base64'),...(body?{'Content-Type':'application/x-www-form-urlencoded'}:{})},body,signal:AbortSignal.timeout(10000)});
 const result=await r.json();if(!r.ok)throw new Error('Twilio '+r.status+': '+(result.message||'request failed'));return result;
}
async function bland(method,resource,body){
 const key=fs.readFileSync('/root/.bland/key','utf8').trim();
 const r=await fetch('https://api.bland.ai/v1/'+resource,{method,headers:{authorization:key,'Content-Type':'application/json','User-Agent':'curl/8'},body:body?JSON.stringify(body):undefined,signal:AbortSignal.timeout(15000)});
 const data=await r.json();if(!r.ok||data.errors?.length||data.status==='error'||data.success===false)throw new Error('Bland request failed: '+JSON.stringify(data.errors||data));return data;
}
function escaped(text){return String(text).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&apos;'}[c]));}
function xml(room,label){return '<Response><Dial><Conference beep="false" record="do-not-record" participantLabel="'+label+'" startConferenceOnEnter="true" endConferenceOnExit="'+(label==='customer'?'true':'false')+'" statusCallback="'+escaped(base()+'/twilio/events?room='+room.id)+'" statusCallbackMethod="POST" statusCallbackEvent="start end join leave">'+room.id+'</Conference></Dial></Response>';}
function verify(req,body){
 const c=config();const values=Object.fromEntries(new URLSearchParams(body));let source=base()+req.url;
 for(const key of Object.keys(values).sort())source+=key+values[key];
 const expected=crypto.createHmac('sha1',c.authToken).update(source).digest('base64');const actual=String(req.headers['x-twilio-signature']||'');
 return actual.length===expected.length&&crypto.timingSafeEqual(Buffer.from(actual),Buffer.from(expected));
}
async function register(data){
 config();const job=jobs.detail(data.job_id);if(!job)throw new Error('Job not found');
 if(!(job.evidence||[]).some(e=>e.provider==='bland'&&e.externalId===data.call_id))throw new Error('Call is not registered to this job');
 const existing=all().find(r=>r.originalCallId===data.call_id);if(existing)return publicRoom(existing);
 if(all().some(r=>!['ended','cancelled'].includes(r.state)))throw new Error('The dedicated conference line already has a call.');
 const detail=await bland('GET','calls/'+encodeURIComponent(data.call_id));const c=detail.data||detail;
 const id=crypto.randomBytes(12).toString('hex');
 const room={id,jobId:job.id,originalCallId:data.call_id,customerNumber:data.request.phone_number,request:data.request,
   allowedFrom:[c.from,c.from_number,data.request.phone_number].filter(Boolean),state:'awaiting-transfer',
   createdAt:new Date().toISOString(),expiresAt:new Date(Date.now()+Number(data.request.max_duration||12)*60000).toISOString(),segments:[{callId:data.call_id}],ownerSummaries:[]};
 save(room);return publicRoom(room);
}
async function ringOwner(id){
 let room=read(id);if(room.ownerSid&&room.state==='owner-ringing')return publicRoom(room);
 const phone=JSON.parse(fs.readFileSync(path.join(ROOT,'profile.json'),'utf8')).identity.phone;
 room.state='owner-ringing';save(room);
 try{
  const result=await twilio('POST','Calls.json',{To:phone,From:config().conferenceNumber,Twiml:xml(room,'owner'),Timeout:30,TimeLimit:remaining(room),StatusCallback:base()+'/twilio/events?room='+room.id+'&leg=owner',StatusCallbackMethod:'POST'});
  room=read(id);room.ownerSid=result.sid;save(room);
  if(['ended','cancelled'].includes(room.state))await twilio('POST','Calls/'+result.sid+'.json',{Status:'completed'});
  return publicRoom(room);
 }catch(e){room=read(id);room.lastError=e.message;save(room);await finish(id);throw e;}
}
function remaining(room){const seconds=Math.floor((Date.parse(room.expiresAt)-Date.now())/1000);if(seconds<1)throw new Error('The approved call time has ended.');return seconds;}
async function entry(form,attempt=0){
 const from=form.From;let room;
 for(const candidate of all().filter(r=>!['ended','cancelled'].includes(r.state))){
  if(candidate.customerSid===form.CallSid)return xml(candidate,'customer');
  if(candidate.aiSid===form.CallSid)return xml(candidate,'agent');
  if(candidate.state==='awaiting-transfer'&&candidate.allowedFrom.includes(from)){room=candidate;break;}
  if(candidate.state==='resuming'&&candidate.pendingAiCallId){
   const detail=await bland('GET','calls/'+encodeURIComponent(candidate.pendingAiCallId));const c=detail.data||detail;
   if([c.from,c.from_number].filter(Boolean).includes(from)){room=candidate;break;}
  }
 }
 if(!room){
  if(attempt<6){await new Promise(resolve=>setTimeout(resolve,500));return entry(form,attempt+1);}
  return '<Response><Reject reason="rejected"/></Response>';
 }
 if(room.state==='awaiting-transfer'){
  room.customerSid=form.CallSid;room.state='customer-connected';save(room);
  setImmediate(()=>ringOwner(room.id).catch(e=>{const r=read(room.id);r.lastError=e.message;save(r);}));return xml(room,'customer');
 }
 room.aiSid=form.CallSid;room.state='ai';room.activeAiCallId=room.pendingAiCallId;delete room.pendingAiCallId;save(room);
 return xml(room,'agent');
}
async function stopAi(room){
 if(room.aiSid&&room.conferenceSid)await twilio('POST','Conferences/'+room.conferenceSid+'/Participants/'+room.aiSid+'.json',{Muted:true});
 if(room.activeAiCallId)await bland('POST','calls/'+encodeURIComponent(room.activeAiCallId)+'/stop',{});
}
async function takeover(id){
 const room=read(id);if(['human','owner-ringing'].includes(room.state))return publicRoom(room);
 if(room.state==='awaiting-transfer'){
  await bland('POST','calls/active/transfer',{call_id:room.originalCallId,transfer_number:config().conferenceNumber});
  return {...publicRoom(read(id)),instruction:'Transfer requested. The call room will ring George when the other side connects.'};
 }
 if(room.state!=='ai')throw new Error('This room is not ready for takeover.');
 room.state='taking-over';save(room);
 try{await stopAi(room);return await ringOwner(id);}
 catch(e){const latest=read(id);latest.lastError=e.message;save(latest);await finish(id);throw e;}
}
async function resume(id,summary){
 let room=read(id);if(room.state!=='human')throw new Error('George must be in the call before returning it to AI.');
 if(!String(summary||'').trim())throw new Error('Give a short account of what was agreed during the human part.');
 const secondsLeft=remaining(room);
 room.ownerSummaries.push({text:String(summary),at:new Date().toISOString()});room.state='resuming';save(room);
 const body={...room.request,max_duration:secondsLeft/60,phone_number:config().conferenceNumber,wait_for_greeting:false,
   metadata:{...room.request.metadata,conference_room_id:room.id,assistant_job_id:room.jobId},
   task:room.request.task+'\n\nGeorge explicitly returns this same live call to you now. For this call, continue with the person rather than applying the initial human-transfer rule again. What George says happened: '+summary+'. Continue from that point. If George needs to take over again, use handoff_to_george. You are joining an existing call, so use a brief continuation rather than repeating the original introduction.'};
 body.first_sentence='I’m back. Let’s continue.';
 let result;
 try{result=await bland('POST','calls',body);}catch(e){room=read(id);room.state='human';room.lastError=e.message;save(room);if(room.ownerLeft)await finish(id);throw e;}
 const callId=result.call_id||result.data?.call_id;
 if(!callId){room=read(id);room.state='human';room.lastError='AI return did not provide a call ID';save(room);if(room.ownerLeft)await finish(id);throw new Error(room.lastError);}
 room=read(id);
 if(['ended','cancelled'].includes(room.state)){await bland('POST','calls/'+encodeURIComponent(callId)+'/stop',{});throw new Error('The call ended before the AI returned.');}
 room.pendingAiCallId=callId;room.resumeStartedAt=new Date().toISOString();room.segments.push({callId,resumedAt:room.resumeStartedAt});save(room);
 jobs.record({receiptId:'conference-call-'+callId,jobId:room.jobId,evidence:{provider:'bland',externalId:callId,channel:'phone',status:'resuming',conferenceId:room.id}});
 return publicRoom(room);
}
async function finish(id){
 let room=read(id);
 if(['ended','cancelled'].includes(room.state))return publicRoom(room);
 if(room.conferenceSid)await twilio('POST','Conferences/'+room.conferenceSid+'.json',{Status:'completed'});
 else if(room.customerSid)await twilio('POST','Calls/'+room.customerSid+'.json',{Status:'completed'});
 else await bland('POST','calls/'+encodeURIComponent(room.originalCallId)+'/stop',{});
 room=read(id);room.state='ended';room.endedAt=new Date().toISOString();save(room);
 if(room.ownerSid)await twilio('POST','Calls/'+room.ownerSid+'.json',{Status:'completed'}).catch(()=>{});
 if(room.pendingAiCallId)await bland('POST','calls/'+encodeURIComponent(room.pendingAiCallId)+'/stop',{}).catch(()=>{});
 return publicRoom(room);
}
async function event(form,id,leg){
 let room=read(id);const kind=form.StatusCallbackEvent;
 if(['ended','cancelled'].includes(room.state))return;
 if(form.ConferenceSid)room.conferenceSid=form.ConferenceSid;
 if(kind==='conference-end'){
  room.state='ended';room.endedAt=new Date().toISOString();save(room);
  if(room.ownerSid)await twilio('POST','Calls/'+room.ownerSid+'.json',{Status:'completed'}).catch(()=>{});
  if(room.pendingAiCallId)await bland('POST','calls/'+encodeURIComponent(room.pendingAiCallId)+'/stop',{}).catch(()=>{});
  return;
 }
 if(kind==='participant-join'&&form.ParticipantLabel==='owner'){room.ownerSid=form.CallSid;room.ownerLeft=false;room.state='human';}
 if(kind==='participant-join'&&form.ParticipantLabel==='agent'){
  room.aiSid=form.CallSid;room.state='ai';const ownerSid=room.ownerSid;delete room.ownerSid;save(room);
  if(ownerSid)await twilio('POST','Calls/'+ownerSid+'.json',{Status:'completed'});return;
 }
 if(kind==='participant-leave'&&form.ParticipantLabel==='owner'&&room.state==='human'){save(room);await finish(id);return;}
 if(kind==='participant-leave'&&form.ParticipantLabel==='owner'&&room.state==='resuming')room.ownerLeft=true;
 if(kind==='participant-leave'&&form.ParticipantLabel==='agent'&&room.state==='ai'){save(room);await finish(id);return;}
 if(leg==='owner'&&['busy','no-answer','failed','canceled'].includes(form.CallStatus)){
  room.state='owner-unavailable';room.lastError='George did not answer the takeover call.';save(room);
  if(room.customerSid)await twilio('POST','Calls/'+room.customerSid+'.json',{Twiml:'<Response><Say voice="Polly.Matthew">The caller is unavailable right now. Thank you. Goodbye.</Say><Hangup/></Response>'});
  room=read(id);room.state='ended';room.endedAt=new Date().toISOString();
 }
 save(room);
}
async function providerTakeover(data){
 const room=all().find(r=>r.jobId===data.job_id&&r.segments.some(s=>s.callId===data.call_id));
 if(!room)throw new Error('No conference belongs to this call');
 if(room.state==='awaiting-transfer')return {id:room.id,state:room.state,instruction:'Say “One second, the caller will be right with you.” Then use your transfer action to '+config().conferenceNumber+'.'};
 return serial(room.id,()=>takeover(room.id));
}
function cancel(id){const room=read(id);if(room.state!=='awaiting-transfer')throw new Error('A connected room needs the end action.');room.state='cancelled';save(room);return publicRoom(room);}
async function maintain(){
 if(!available())return;
 for(const room of all().filter(r=>!['ended','cancelled'].includes(r.state))){
  try{
   if(Date.now()>=Date.parse(room.expiresAt)){await serial(room.id,()=>finish(room.id));continue;}
   if(room.state==='resuming'&&room.pendingAiCallId){
    const response=await bland('GET','calls/'+encodeURIComponent(room.pendingAiCallId));const call=response.data||response;
    if(call.completed||Date.now()-Date.parse(room.resumeStartedAt)>45000){
     await serial(room.id,async()=>{let latest=read(room.id);if(latest.state!=='resuming')return;
      await bland('POST','calls/'+encodeURIComponent(latest.pendingAiCallId)+'/stop',{}).catch(()=>{});
      latest=read(room.id);latest.state='human';latest.lastError='The AI did not rejoin. George’s call remains connected.';delete latest.pendingAiCallId;save(latest);
      if(latest.ownerLeft)await finish(latest.id);
     });
    }
   }
  }catch(e){const latest=read(room.id);latest.lastError=e.message;save(latest);}
 }
}
module.exports={cancel,available,register:data=>serial('register',()=>register(data)),entry,verify,event,takeover:id=>serial(id,()=>takeover(id)),resume:(id,summary)=>serial(id,()=>resume(id,summary)),finish:id=>serial(id,()=>finish(id)),maintain,providerTakeover,list,get:id=>publicRoom(read(id))};
