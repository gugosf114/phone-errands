const fs=require('fs');
const ASSISTANT='4346abeb-ee9e-4b7e-a8fa-57f20a32c325';
function key(){const line=fs.readFileSync('/root/.gmail/aicalls.env','utf8').split('\n').find(l=>l.startsWith('VAPI_KEY='));if(!line)throw new Error('Vapi key unavailable');return line.slice(9).trim().replace(/^["']|["']$/g,'');}
async function call(id){
 const r=await fetch('https://api.vapi.ai/call/'+encodeURIComponent(id),{headers:{Authorization:'Bearer '+key(),'User-Agent':'curl/8'},signal:AbortSignal.timeout(10000)});
 if(!r.ok)throw new Error('Vapi call lookup HTTP '+r.status);const c=await r.json();
 if(c.id!==id||c.assistantId!==ASSISTANT)throw new Error('Personal call identity mismatch');return c;
}
async function message(id,content,triggerResponseEnabled=true){
 const c=await call(id);if(c.status!=='in-progress')return {state:'call-ended'};
 const url=new URL(c.monitor?.controlUrl||'');if(url.protocol!=='https:'||!url.hostname.endsWith('.vapi.ai'))throw new Error('Invalid Vapi control URL');
 const r=await fetch(url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({type:'add-message',message:{role:'system',content},triggerResponseEnabled}),signal:AbortSignal.timeout(10000)});
 if(!r.ok)throw new Error('Vapi context delivery HTTP '+r.status);return {state:'accepted-by-vapi'};
}
module.exports={ASSISTANT,call,message};
