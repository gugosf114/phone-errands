// A persistent conversation view shared by voice calls and the selected Claude chat.
const fs=require('fs');
const path=require('path');
const crypto=require('crypto');
const {active}=require('./active.js');
const ROOT=process.env.ASSISTANT_DATA_DIR||'/root/.local/state/phone-errands';
const DIR=path.join(ROOT,'threads');
fs.mkdirSync(DIR,{recursive:true,mode:0o700});
function read(file,fallback){try{return JSON.parse(fs.readFileSync(file,'utf8'));}catch(e){if(e.code==='ENOENT')return fallback;throw e;}}
function write(file,value){fs.mkdirSync(path.dirname(file),{recursive:true,mode:0o700});fs.writeFileSync(file+'.tmp',JSON.stringify(value,null,2),{mode:0o600});fs.renameSync(file+'.tmp',file);}
function current(){return read(path.join(ROOT,'current-thread.json'),{id:'main',label:'Personal assistant'});}
function forCall(id){return read(path.join(ROOT,'call-threads',String(id).replace(/[^a-zA-Z0-9_-]/g,'')+'.json'),current());}
function folder(id){if(!/^[a-zA-Z0-9_-]{1,80}$/.test(id))throw new Error('Invalid thread ID');return path.join(DIR,id);}
function select(spec){
  const id=String(spec.id||'').trim();folder(id);
  const result={id,label:String(spec.label||id)};
  if(spec.transcript){
    if(!path.isAbsolute(spec.transcript)||!spec.transcript.endsWith('.jsonl')||!fs.existsSync(spec.transcript))throw new Error('Choose an existing absolute chat transcript path');
    result.transcript=spec.transcript;
  }
  write(path.join(ROOT,'current-thread.json'),result);return result;
}
function putCall(call,messages,thread=forCall(call?.id)){
  if(!/^[a-zA-Z0-9_-]{1,120}$/.test(call?.id||'')||!Array.isArray(messages))return;
  const prior=read(path.join(folder(thread.id),'calls',call.id+'.json'),{});
  const started=call.startedAt||call.createdAt||prior.startedAt||new Date().toISOString();
  const previous=new Map((prior.messages||[]).map(m=>[m.id,m]));
  const clean=messages.filter(m=>['user','assistant','bot'].includes(m.role)).map((m,index)=>{
    const text=typeof m.content==='string'?m.content:String(m.message||m.transcript||'');
    const old=previous.get(call.id+':'+index);
    const stamp=typeof m.time==='number'&&m.time>=1e9?new Date(m.time<1e11?m.time*1000:m.time).toISOString():
      typeof m.secondsFromStart==='number'?new Date(Date.parse(started)+m.secondsFromStart*1000).toISOString():
      old?.text===text?old.timestamp:new Date(Date.now()+index).toISOString();
    return {id:call.id+':'+index,role:m.role==='bot'?'assistant':m.role,text,timestamp:stamp,source:'phone',callId:call.id};
  }).filter(m=>m.text.trim());
  write(path.join(folder(thread.id),'calls',call.id+'.json'),{callId:call.id,startedAt:started,messages:clean});
}
function append(role,text,thread=current()){
  if(!['user','assistant'].includes(role))throw new Error('Use a user or assistant message');
  const row={id:crypto.randomUUID(),role,text:String(text),timestamp:new Date().toISOString(),source:'chat'};
  fs.mkdirSync(folder(thread.id),{recursive:true,mode:0o700});
  fs.appendFileSync(path.join(folder(thread.id),'manual.jsonl'),JSON.stringify(row)+'\n',{mode:0o600});return row;
}
function syncChat(thread=current()){
  const file=thread.transcript||active().jsonl;if(!file||!fs.existsSync(file))return;
  const sourceId=crypto.createHash('sha256').update(file).digest('hex').slice(0,20);
  const stateFile=path.join(folder(thread.id),'sources',sourceId+'.json');
  const state=read(stateFile,{file,offset:0,messages:[]});const size=fs.statSync(file).size;
  if(size===state.offset)return;
  if(size<state.offset)throw new Error('The linked chat transcript shrank; choose it again before syncing.');
  const fd=fs.openSync(file,'r');const buf=Buffer.alloc(size-state.offset);
  try{fs.readSync(fd,buf,0,buf.length,state.offset);}finally{fs.closeSync(fd);}
  const boundary=buf.lastIndexOf(10);if(boundary<0)return;
  const seen=new Set(state.messages.map(m=>m.id));
  for(const line of buf.subarray(0,boundary+1).toString('utf8').split('\n')){
    let row;try{row=JSON.parse(line);}catch(_){continue;}
    if(row.isSidechain||row.isMeta)continue;
    let role=row.type,content=row.message?.content;
    if(row.type==='event_msg'&&row.payload?.type==='user_message'){role='user';content=row.payload.message;}
    else if(row.type==='response_item'&&row.payload?.type==='message'&&row.payload.role==='assistant'){role='assistant';content=row.payload.content;}
    else if(!['user','assistant'].includes(role))continue;
    let text=typeof content==='string'?content:Array.isArray(content)?content.filter(b=>['text','output_text'].includes(b.type)).map(b=>b.text).join('\n'):'';
    if(text.startsWith('(Job from George')&&text.includes('George’s request: '))text=text.slice(text.lastIndexOf('George’s request: ')+'George’s request: '.length);
    else if(text.startsWith('(Question from George')||text.startsWith('(Voice call with George'))text=text.slice(text.indexOf(') ')+2);
    if(row.isCompactSummary||text.startsWith('This session is being continued from a previous conversation'))continue;
    if(!text.trim()||text.startsWith('<local-command')||text.startsWith('<command-name>'))continue;
    const id=row.uuid||sourceId+':'+state.offset+':'+state.messages.length;
    if(seen.has(id))continue;seen.add(id);
    state.messages.push({id,role,text,timestamp:row.timestamp||new Date().toISOString(),source:'chat',transcript:file});
  }
  state.offset+=boundary+1;write(stateFile,state);
}
function history({thread=current(),excludeCallId,limit=40,maxChars=18000,source,query}={}){
  syncChat(thread);const dir=folder(thread.id);let rows=[];
  for(const group of ['sources','calls']){
    const p=path.join(dir,group);if(!fs.existsSync(p))continue;
    for(const name of fs.readdirSync(p).filter(n=>n.endsWith('.json'))){
      const item=read(path.join(p,name),{});
      if(item.callId&&item.callId===excludeCallId)continue;
      rows.push(...(item.messages||[]));
    }
  }
  const manual=path.join(dir,'manual.jsonl');
  if(fs.existsSync(manual))for(const line of fs.readFileSync(manual,'utf8').split('\n')){try{rows.push(JSON.parse(line));}catch(_){}}
  rows=rows.filter(m=>(!source||m.source===source)&&(!query||String(query).toLowerCase().split(/\s+/).every(word=>m.text.toLowerCase().includes(word)))).sort((a,b)=>a.timestamp.localeCompare(b.timestamp));
  const selected=[];let remaining=maxChars;
  for(let i=rows.length-1;i>=0&&selected.length<limit&&remaining>0;i--){
    const text=rows[i].text.slice(-remaining);selected.unshift({...rows[i],text});remaining-=text.length;
  }
  return {threadId:thread.id,label:thread.label,totalMessages:rows.length,messages:selected};
}
function callState(call,thread=current()){
  if(!/^[a-zA-Z0-9_-]{1,120}$/.test(call.id||''))return;
  const binding=path.join(ROOT,'call-threads',call.id+'.json');
  if(!fs.existsSync(binding))write(binding,thread);
  thread=forCall(call.id);
  const file=path.join(ROOT,'active-personal-call.json');
  if(['ended','forwarding'].includes(call.status)){const old=read(file,{});if(old.id===call.id)write(file,{...old,status:call.status});return;}
  write(file,{id:call.id,status:call.status||'in-progress',threadId:thread.id,updatedAt:new Date().toISOString()});
}
function activeCall(){return read(path.join(ROOT,'active-personal-call.json'),null);}
module.exports={current,forCall,select,putCall,append,syncChat,history,callState,activeCall};
