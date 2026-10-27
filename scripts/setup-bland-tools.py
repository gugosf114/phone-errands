#!/usr/bin/env python3
"""Create or update only this personal assistant's Bland tools."""
import argparse,json
from pathlib import Path
import urllib.request,urllib.error

ROOT=Path(__file__).resolve().parents[1]
CONFIG=ROOT/'config/bland-tools.json'
BASE='https://api.bland.ai'
KEY=Path('/root/.bland/key').read_text().strip()
LINE=Path('/root/.vapi/bridge/line.key').read_text().strip().split('=',1)[1]
DOMAIN=Path('/root/.vapi/bridge/ngrok_domain.txt').read_text().strip()


def api(method,path,body=None):
 req=urllib.request.Request(BASE+path,method=method,headers={'authorization':KEY,'Content-Type':'application/json','User-Agent':'curl/8'},data=json.dumps(body).encode() if body is not None else None)
 with urllib.request.urlopen(req,timeout=30) as response:return json.load(response)


parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--apply',action='store_true');a=parser.parse_args()
config=json.loads(CONFIG.read_text()) if CONFIG.exists() else {'tools':{}}
specs=[('ask_george','Ask George privately for a missing fact or decision during this call. Use the supplied task facts first. Returns a question_id; use get_george_answer for his reply.','/bland/ask-owner',{'job_id':{'type':'string'},'question':{'type':'string'}},['job_id','question']),
 ('get_george_answer','Read George’s answer to a private question while this call continues. Use the exact question_id returned by ask_george.','/bland/owner-answer',{'job_id':{'type':'string'},'question_id':{'type':'string'}},['job_id','question_id'])]
specs.append(('handoff_to_george','For a managed conference call, bring George into this same call. Follow the returned transfer instruction when the room is being opened.','/bland/takeover',{'job_id':{'type':'string'}},['job_id']))
for name,description,endpoint,properties,required in specs:
 payload={'job_id':'{{input.job_id}}','call_id':'{{call_id}}'}
 payload.update({key:'{{input.'+key+'}}' for key in properties if key!='job_id'})
 body={'name':name,'description':description,'integration':'rest_api','action':'post',
       'input_schema':{'type':'object','properties':properties,'required':required},
       'body':{'url':'https://'+DOMAIN,'path':endpoint,'headers':[{'key':'X-Line-Key','value':LINE}],'body':payload},
       'timeout':15000,'cache':False,'public':False,'max_retries':0,
       'label':'George personal assistant — '+name,
       'response_data':[{'name':'owner_reply','data':'$.data.rest_api_post_data','context':'Private owner question status and answer'}]}
 if name=='ask_george':body['speech']='One moment while I check that.'
 if not a.apply:print(json.dumps({'name':name,'endpoint':endpoint,'existingId':config['tools'].get(name)}));continue
 old=config['tools'].get(name)
 response=api('POST','/v2/tools/'+old if old else '/v2/tools',body)
 if response.get('errors'):raise RuntimeError(json.dumps(response['errors']))
 data=response.get('data',{})
 tool_id=data.get('id') or data.get('tool_id') or old
 if not tool_id:raise RuntimeError('Tool API returned no ID')
 config['tools'][name]=tool_id
 CONFIG.write_text(json.dumps(config,indent=2)+'\n')
 print(json.dumps({'name':name,'id':tool_id,'saved':True}))
