// Durable questions bridge the outbound caller and George's private voice/chat.
const fs=require('fs');const path=require('path');const crypto=require('crypto');
const {spawnSync}=require('child_process');const jobs=require('./jobs.js');
const conversations=require('./conversations.js');const control=require('./vapi_control.js');
const ROOT=process.env.ASSISTANT_DATA_DIR||'/root/.local/state/phone-errands';
const DIR=path.join(ROOT,'questions');fs.mkdirSync(DIR,{recursive:true,mode:0o700});
function file(id){if(!/^[a-f0-9]{24}$/.test(String(id)))throw new Error('Invalid question ID');return path.join(DIR,id+'.json');}
function save(q){fs.writeFileSync(file(q.id)+'.tmp',JSON.stringify(q,null,2),{mode:0o600});fs.renameSync(file(q.id)+'.tmp',file(q.id));}
function delivery(id,fields){const latest=get(id);Object.assign(latest,fields);save(latest);}
function get(id){const q=JSON.parse(fs.readFileSync(file(id),'utf8'));if(q.state==='pending'&&Date.now()>Date.parse(q.expiresAt)){q.state='expired';save(q);}return q;}
function list(){return fs.readdirSync(DIR).filter(n=>n.endsWith('.json')).map(n=>get(n.slice(0,-5))).filter(q=>q.state==='pending').map(q=>({id:q.id,jobId:q.jobId,question:q.question,createdAt:q.createdAt,expiresAt:q.expiresAt}));}
function callMatches(job,providerCallId){return (job.evidence||[]).some(e=>e.provider==='bland'&&e.externalId===providerCallId);}
async function notify(q){
 const job=jobs.detail(q.jobId);const active=conversations.activeCall();
 const ownerCallId=active?.status==='in-progress'?active.id:job.callId;
 if(ownerCallId){
  try{
   delivery(q.id,{ownerCallId});
   const sent=await control.message(ownerCallId,'The outbound call has a question for George. Ask him this exact question briefly, then use answer_question with question_id '+q.id+' and his answer. This is a question, not a new task: '+q.question,true);
   delivery(q.id,{delivery:sent.state});if(sent.state==='accepted-by-vapi')return;
  }catch(e){delivery(q.id,{deliveryError:e.message});}
 }
 if(get(q.id).state!=='pending')return;
 // The notification is on George's own phone. The answer command is available in any chat.
 const result=spawnSync('/data/data/com.termux/files/usr/bin/termux-notification',['--id','personal-assistant-question','--title','Your call needs an answer','--content',q.question+'  Answer with: assistant answer '+q.id+' "your answer"'],{timeout:8000,stdio:'ignore'});
 delivery(q.id,{delivery:result.status===0?'phone-notification':'saved-for-owner'});
}
function create(data){
 const job=jobs.detail(data.job_id);if(!job)throw new Error('Job not found');
 const providerCallId=String(data.call_id||'');if(!callMatches(job,providerCallId))throw new Error('This call is not linked to the job');
 const question=String(data.question||'').trim();if(!question||question.length>1500)throw new Error('Use a short question');
 const id=crypto.createHash('sha256').update(data.job_id+':'+providerCallId+':'+question).digest('hex').slice(0,24);
 if(fs.existsSync(file(id)))return publicReply(get(id));
 const pending=list().find(q=>q.jobId===job.id);if(pending)return publicReply(get(pending.id));
 const q={id,jobId:job.id,providerCallId,question,state:'pending',createdAt:new Date().toISOString(),expiresAt:new Date(Date.now()+120000).toISOString(),delivery:'pending'};
 save(q);void notify(q).catch(e=>delivery(q.id,{delivery:'saved-for-owner',deliveryError:e.message}));return publicReply(q);
}
function publicReply(q){return {question_id:q.id,state:q.state,question:q.question,answer:q.state==='answered'?q.answer:null,instruction:q.state==='pending'?'George has been asked privately. Keep the conversation going and check get_george_answer for his reply. His reply may arrive while you are talking.':q.state==='expired'?'George has not answered in time. Report the unanswered point and use only the authority already given for this errand.':'Use George’s actual answer for this errand.'};}
function poll(data){const q=get(data.question_id);if(q.providerCallId!==String(data.call_id)||q.jobId!==data.job_id)throw new Error('Question and call do not match');return publicReply(q);}
function answer(id,text,source={}){
 const q=get(id);if(q.state!=='pending')throw new Error('Question is '+q.state);
 if(source.callId&&q.ownerCallId&&source.callId!==q.ownerCallId)throw new Error('Answer must come from the owner’s question call');
 const response=String(text||'').trim();if(!response)throw new Error('An answer is required');
 q.state='answered';q.answer=response;q.answeredAt=new Date().toISOString();q.answerSource=source;save(q);
 jobs.record({receiptId:'owner-answer-'+q.id,jobId:q.jobId,evidence:{channel:'owner-answer',question:q.question,answer:response,questionId:q.id}});
 return {question_id:q.id,state:q.state};
}
module.exports={create,poll,answer,list,get};
