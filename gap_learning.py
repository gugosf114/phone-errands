"""Learn which facts a later errand should prepare, using actual unanswered questions."""
import datetime
import json
import os
from pathlib import Path
import re

DATA=Path(os.environ.get('ASSISTANT_PROFILE_DIR','/root/.local/state/phone-errands'))
FIELDS=[
 ('account_number',r'account (?:number|id)|customer (?:number|id)|member(?:ship)? (?:number|id)'),
 ('service_address',r'service address|address on (?:the |your )?account|billing address'),
 ('account_phone',r'phone number|callback number|number on (?:the |your )?account'),
 ('account_email',r'e.?mail (?:address|on)|address.*e.?mail'),
 ('date_of_birth',r'date of birth|birth ?date'),
 ('ssn_last4',r'(?:social|ssn).*last (?:four|4)|last (?:four|4).*(?:social|ssn)'),
 ('verification_last4',r'last four|last 4'),
 ('plan_name',r'which plan|plan name|type of (?:plan|service)'),
 ('desired_date',r'what date|which day|what day|preferred date'),
 ('reference_number',r'confirmation (?:number|code)|reference (?:number|code)|case number')]
DEFER=re.compile(r"i (?:do not|don't) (?:have|know)|need to (?:check|ask)|check with george|missing (?:detail|information)|cannot confirm|can send it in writing",re.I)


def turns(call):
    rows=call.get('transcripts') or call.get('transcript')
    if isinstance(rows,list):
        result=[]
        for row in rows:
            role=str(row.get('user') or row.get('role') or row.get('speaker') or '').lower()
            result.append(('agent' if role in ['assistant','agent','bot'] else 'other',str(row.get('text') or row.get('content') or '')))
        return result
    text=call.get('concatenated_transcript') or (rows if isinstance(rows,str) else '')
    result=[]
    for line in text.splitlines():
        match=re.match(r'\s*(Agent|Assistant|User|Human|Customer|Callee):\s*(.*)',line,re.I)
        if match:result.append(('agent' if match[1].lower() in ['agent','assistant'] else 'other',match[2]))
        elif result:result[-1]=(result[-1][0],result[-1][1]+' '+line.strip())
    return result


def learn(call, account=None, company=None):
    call_id=str(call.get('call_id') or call.get('id') or '')
    if not call_id:return {'added':[]}
    key=account or re.sub(r'[^a-z0-9]+','-',str(company or 'general').lower()).strip('-')[:64] or 'general'
    if not re.fullmatch(r'[a-z0-9][a-z0-9_-]{0,63}',key):raise ValueError('Use a short account key with letters, numbers, dashes, or underscores.')
    directory=DATA/'requirements';directory.mkdir(parents=True,exist_ok=True,mode=0o700)
    file=directory/(key+'.json')
    state=json.loads(file.read_text()) if file.exists() else {'key':key,'company':company,'calls':[],'fields':{}}
    if call_id in state['calls']:return {'added':[],'alreadyReviewed':True}
    questions=[];previous=None
    for role,text in turns(call):
        if role=='other':previous=text
        elif previous:
            if DEFER.search(text):questions.append(previous)
            previous=None
    custom=(call.get('call_analysis') or {}).get('custom_analysis_data',{}) or {}
    unanswered=custom.get('unanswered_questions',[])
    if isinstance(unanswered,str):unanswered=[unanswered]
    questions.extend(q for q in unanswered if isinstance(q,str))
    for saved in (DATA/'questions').glob('*.json'):
        question=json.loads(saved.read_text())
        if question.get('providerCallId')==call_id:
            questions.append(question['question'])
    added=[]
    for question in questions:
        for field,pattern in FIELDS:
            if re.search(pattern,question,re.I):
                record=state['fields'].setdefault(field,{'count':0,'examples':[]})
                if any(e['callId']==call_id and e['question']==question for e in record['examples']):break
                record['count']+=1;record['examples'].append({'callId':call_id,'question':question[:700]})
                added.append(field);break
    state['calls'].append(call_id);state['updatedAt']=datetime.datetime.now(datetime.timezone.utc).isoformat()
    fd=os.open(str(file)+'.tmp',os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
    with os.fdopen(fd,'w') as stream:json.dump(state,stream,indent=2)
    os.replace(str(file)+'.tmp',file)
    return {'account':key,'added':list(dict.fromkeys(added))}


def requirements(account):
    if not account or not re.fullmatch(r'[a-z0-9][a-z0-9_-]{0,63}',account):return {}
    file=DATA/'requirements'/(account+'.json')
    return json.loads(file.read_text()).get('fields',{}) if file.exists() else {}


def learn_safely(call, **context):
    try:return learn(call, **context)
    except Exception as error:return {'added':[], 'error':str(error)}
