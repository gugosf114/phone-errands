// Vapi bridge -> the ACTIVE claude session (a tmux room).
//   POST /chat/completions : custom-LLM lane (whole turn through the brain). Used by the OLD brain line.
//   POST /tools            : Vapi function tools for the FAST line (Sonnet 5 inside Vapi):
//                            brain_job (queue + result delivery), brain_ask (up to 20 s), memory_lookup (notes).
const http = require('http');
const fs = require('fs');
const { spawnSync } = require('child_process');
const { ask, tmux } = require('./brain_tmux.js');
const jobs = require('./jobs.js');
const { active } = require('./active.js');

const PORT = parseInt(process.env.BRIDGE_PORT || '8790', 10);
const LOG = '/root/.vapi/bridge/live.log';
const FILLER = 'Okay.';
const LINE_KEY = (()=>{try{return fs.readFileSync('/root/.vapi/bridge/line.key','utf8').trim().split('=')[1];}catch(e){return '';}})();
const VOICE_TAG = '(Voice call with George, spoken aloud. Answer in 1-3 short spoken sentences, no lists or markdown, answer first. If a task takes more than a few seconds, say you are on it and will report back, then do it.) ';
const JOB_TAG = '(Job from George, given by voice on the phone line. Do it fully, start to finish. Keep the work in this turn until it is complete or blocked; do not send a background task and end early. When done, write the short outcome and its proof. The bridge returns your final answer to the phone call.) ';
const BRAIN_INSTRUCTIONS=fs.readFileSync(__dirname+'/brain_instructions.txt','utf8');
const REVISION=(()=>{try{return fs.readFileSync(__dirname+'/REVISION','utf8').trim();}catch(_){return 'working-tree';}})();
const ASK_TAG = '(Question from George on the phone line, relayed by the fast line. Answer in 1-3 short plain sentences, answer first, no lists, no markdown, no paths or URLs.) ';

function logline(s){try{fs.appendFileSync(LOG,new Date().toTimeString().slice(0,8)+' '+s+'\n');}catch(e){}}
function roomAlive(target=active()){ try{ tmux(['has-session','-t',target.tmux]); return tmux(['display-message','-p','-t',target.tmux,'#{pane_dead}']).trim()==='0'; }catch(e){ return false; } }

// one queue into the brain: chat turns, asks and jobs take turns
let busy=false,q=[];
function enqueue(job){job.target=job.target||active();q.push(job);setImmediate(pump);}
function pump(){
  if(busy||!q.length)return;
  const job=q.shift();
  if(!roomAlive(job.target)){job.onDone('The brain session is not available.',{state:'failed'});return pump();}
  busy=true;logline('THINKING…');
  if(job.onStart)job.onStart();
  ask(null, job.text, {
    onDelta:t=>job.onDelta&&job.onDelta(t),
    onDone:(full,meta)=>{busy=false;logline('BRAIN: '+full.replace(/\s+/g,' ').slice(0,300));job.onDone(full,meta);pump();}
  }, 0, job.target);
}
function queueJob(task,context,done){
  try {
    const {job,existing}=jobs.create(task,context,active());
    if(existing)return done('This request is already '+job.state+'. Do not submit it again.',job);
    const contextText=JSON.stringify({jobId:job.id,channel:job.channel,card:job.card,recentMessages:job.recentMessages});
    const instructions=BRAIN_INSTRUCTIONS.replaceAll('{{JOB_ID}}',job.id);
    enqueue({target:job.target,text:JOB_TAG+instructions+'\nJob context: '+contextText+'\nGeorge’s request: '+task,
      onStart:()=>{job.state='running';jobs.save(job);},
      onDone:(answer,meta)=>{logline('JOB RESULT '+job.id+': '+answer.replace(/\s+/g,' ').slice(0,300));jobs.finish(job,answer,meta).catch(e=>logline('JOB SAVE ERROR '+e.message));}});
    done('Job '+job.id+' is queued. Keep talking with George. Its result will be sent into this call automatically when the brain returns.',job);
  } catch(e){done('The job was not queued: '+e.message);}
}

// ---- tools ----
function memoryLookup(topic){
  const dir='/root/.claude/projects/-root/memory';
  const words=String(topic||'').toLowerCase().split(/[^a-z0-9]+/).filter(w=>w.length>2);
  if(!words.length) return 'Say a topic word.';
  let out=[];
  try{
    const idx=fs.readFileSync(dir+'/MEMORY.md','utf8').split('\n').filter(l=>l.startsWith('- '));
    for(const l of idx) if(words.some(w=>l.toLowerCase().includes(w))) out.push(l.replace(/\[([^\]]+)\]\([^)]+\)/g,'$1'));
    if(out.length<4){
      const r=spawnSync('grep',['-i','-l','-E',words.join('|'),...fs.readdirSync(dir).filter(f=>f.endsWith('.md')&&f!=='MEMORY.md').map(f=>dir+'/'+f)],{encoding:'utf8'});
      for(const f of (r.stdout||'').split('\n').filter(Boolean).slice(0,3)){
        const txt=fs.readFileSync(f,'utf8');
        const hits=txt.split('\n').filter(l=>words.some(w=>l.toLowerCase().includes(w))).slice(0,3);
        out.push('['+f.split('/').pop()+'] '+hits.join(' ').slice(0,500));
      }
    }
  }catch(e){ return 'memory lookup failed: '+e.message; }
  return out.length? out.join('\n').slice(0,1500) : 'Nothing in memory about '+topic+'.';
}

function handleTool(name,args,done,context={}){
  args=args||{};
  if(name==='brain_job'){
    const task=String(args.task||'').trim(); if(!task) return done('No task given.');
    logline('JOB from fast line: '+task.slice(0,200));
    return queueJob(task,context,done);
  }
  if(name==='brain_ask'){
    const qn=String(args.question||'').trim(); if(!qn) return done('No question given.');
    logline('ASK from fast line: '+qn.slice(0,200));
    if(busy||q.length)return queueJob(qn,context,done);
    let answered=false,lateJob=null;
    const timer=setTimeout(()=>{
      if(answered)return;answered=true;
      try{lateJob=jobs.create(qn,context,active()).job;lateJob.state='running';jobs.save(lateJob);}catch(e){logline('LATE JOB '+e.message);}
      done('The brain is still checking. Keep talking with George; its answer will be sent into this call when it returns.');
    },20000);
    enqueue({text:ASK_TAG+qn,onDone:(answer,meta)=>{
      clearTimeout(timer);
      if(lateJob)jobs.finish(lateJob,answer,meta).catch(e=>logline('LATE RESULT '+e.message));
      else if(!answered){answered=true;done(answer);}
    }});
    return;
  }
  if(name==='memory_lookup') return done(memoryLookup(args.topic));
  done('Unknown tool '+name);
}

function toolsEndpoint(req,res,body){
  if(LINE_KEY && req.headers['x-line-key']!==LINE_KEY){res.writeHead(401);res.end('no');return;}
  let j;try{j=JSON.parse(body);}catch(e){res.writeHead(400);res.end('bad json');return;}
  const m=j.message||{};
  const calls=(m.toolCallList||[]).map(c=>({id:c.id,name:(c.function&&c.function.name)||c.name,args:(c.function&&c.function.arguments)||c.arguments}));
  if(!calls.length){res.writeHead(200,{'Content-Type':'application/json'});res.end(JSON.stringify({results:[]}));return;}
  const results=[];let left=calls.length;
  for(const c of calls){
    let a=c.args; if(typeof a==='string'){try{a=JSON.parse(a);}catch(e){a={};}}
    handleTool(c.name,a,r=>{results.push({toolCallId:c.id,name:c.name,result:String(r)});if(--left===0){res.writeHead(200,{'Content-Type':'application/json'});res.end(JSON.stringify({results}));}}, {call:m.call||{},toolCallId:c.id,origin:'voice',recentMessages:(m.artifact?.messages||[]).filter(x=>['user','assistant'].includes(x.role)).slice(-8).map(x=>({role:x.role,content:String(x.message||x.content||'').slice(0,1200)}))});
  }
}

// POST /drop?name=<file>  (header X-Drop-Key) : a cloud session hands a file to this box (patches, reports).
const DROP_KEY=(()=>{try{return fs.readFileSync('/root/.vapi/bridge/drop.key','utf8').trim().split('=')[1];}catch(e){return '';}})();
function dropEndpoint(req,res,body){
  if(!DROP_KEY||req.headers['x-drop-key']!==DROP_KEY){res.writeHead(401);res.end('no');return;}
  const q=new URL(req.url,'http://x').searchParams; const name=(q.get('name')||'drop.bin').replace(/[^A-Za-z0-9._-]/g,'_').slice(0,80);
  if(body.length>20*1024*1024){res.writeHead(413);res.end('too big');return;}
  const f='/root/.vapi/bridge/drop/'+Date.now()+'-'+name; fs.writeFileSync(f,body,'binary'); logline('DROP '+f+' '+body.length+'B');
  res.writeHead(200,{'Content-Type':'text/plain'});res.end('saved '+name+' '+body.length+' bytes\n');
}
const server=http.createServer((req,res)=>{
  if(req.method==='GET'&&(req.url==='/jobs'||req.url.startsWith('/jobs/'))){
    if(!LINE_KEY||req.headers['x-line-key']!==LINE_KEY){res.writeHead(401);res.end('no');return;}
    try{const data=req.url==='/jobs'?jobs.list():jobs.detail(req.url.slice(6));res.writeHead(data?200:404,{'Content-Type':'application/json'});res.end(JSON.stringify(data||{error:'Job not found'}));}
    catch(e){res.writeHead(400,{'Content-Type':'application/json'});res.end(JSON.stringify({error:e.message}));}return;
  }
  if(req.method==='GET'&&req.url==='/status'){
    if(!LINE_KEY||req.headers['x-line-key']!==LINE_KEY){res.writeHead(401);res.end('no');return;}
    res.writeHead(200,{'Content-Type':'application/json'});res.end(JSON.stringify({version:'personal-assistant-v1',revision:REVISION,busy,queued:q.length,brain:roomAlive(),jobs:jobs.list()}));return;
  }
  if(req.method==='GET'){res.writeHead(200,{'Content-Type':'text/plain'});res.end('tmux brain bridge up');return;}
  let body='';req.setEncoding('binary');req.on('data',c=>body+=c);
  req.on('end',()=>{
    const path=req.url.replace(/\/+$/,'');
    if(req.method==='POST'&&(path==='/jobs'||path==='/receipts')){
      if(!LINE_KEY||req.headers['x-line-key']!==LINE_KEY){res.writeHead(401);res.end('no');return;}
      try{
        const data=JSON.parse(Buffer.from(body,'binary').toString('utf8'));
        if(path==='/receipts'){const receipt=jobs.record(data);res.writeHead(200,{'Content-Type':'application/json'});res.end(JSON.stringify(receipt));return;}
        if(!String(data.task||'').trim())throw new Error('A job needs a task');
        if(!['auto','phone','support-chat'].includes(data.channel||'auto'))throw new Error('Unknown work channel');
        queueJob(data.task,{origin:'terminal',channel:data.channel||'auto',card:data.card||null},(message,job)=>{
          res.writeHead(job?202:400,{'Content-Type':'application/json'});res.end(JSON.stringify({message,jobId:job?.id,state:job?.state}));
        });
      }catch(e){res.writeHead(400,{'Content-Type':'application/json'});res.end(JSON.stringify({error:e.message}));}return;
    }
    if(req.method==='POST'&&path.startsWith('/drop')) return dropEndpoint(req,res,body);
    if(req.method==='POST'&&path.endsWith('/tools')) return toolsEndpoint(req,res,Buffer.from(body,'binary').toString('utf8'));
    if(!(req.method==='POST'&&path.endsWith('/chat/completions'))){res.writeHead(404);res.end('not found');return;}
    let j;try{j=JSON.parse(Buffer.from(body,'binary').toString('utf8'));}catch(e){res.writeHead(400);res.end('bad json');return;}
    const msgs=j.messages||[];
    const lastUser=[...msgs].reverse().find(m=>m.role==='user');
    const userText=lastUser?(typeof lastUser.content==='string'?lastUser.content:JSON.stringify(lastUser.content)):'(call started, greet George)';
    const wantStream=j.stream!==false;
    const id='c'+Date.now(),model='claude-tmux-brain';
    logline('GEORGE: '+userText.replace(/\s+/g,' ').slice(0,300));
    const chunk=(delta,fin)=>'data: '+JSON.stringify({id,object:'chat.completion.chunk',created:Math.floor(Date.now()/1000),model,choices:[{index:0,delta,finish_reason:fin}]})+'\n\n';
    let opened=false;
    const open=()=>{if(!res.headersSent)res.writeHead(200,{'Content-Type':'text/event-stream','Cache-Control':'no-cache','Connection':'keep-alive'});if(!opened){opened=true;res.write(chunk({role:'assistant',content:''},null));}};
    if(wantStream){open();res.write(chunk({content:FILLER+' '},null));}
    enqueue({text:VOICE_TAG+userText,
      onDelta:t=>{if(!wantStream)return;open();res.write(chunk({content:t},null));},
      onDone:full=>{
        if(!wantStream){res.writeHead(200,{'Content-Type':'application/json'});res.end(JSON.stringify({id,object:'chat.completion',created:Math.floor(Date.now()/1000),model,choices:[{index:0,message:{role:'assistant',content:full},finish_reason:'stop'}]}));return;}
        open();res.write(chunk({},'stop'));res.write('data: [DONE]\n\n');res.end();
      }});
  });
});
server.listen(PORT,'127.0.0.1',()=>{
  fs.writeFileSync(__dirname+'/server.pid',String(process.pid));
  console.log('personal assistant '+REVISION+' on 127.0.0.1:'+PORT+' pid '+process.pid);
});
function shutdown(){
  server.close(()=>process.exit(0));
  setTimeout(()=>process.exit(0),3000).unref();
}
process.on('SIGTERM',shutdown);process.on('SIGINT',shutdown);
