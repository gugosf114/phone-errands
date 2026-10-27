"""Shared personal facts, account facts, and behavior for phone and browser errands."""
import copy
import datetime
import json
import os
from pathlib import Path
import re
import sys
from gap_learning import requirements
from conference_client import conference_number

ROOT = Path(__file__).resolve().parent
DATA = Path(os.environ.get('ASSISTANT_PROFILE_DIR', '/root/.local/state/phone-errands'))
BASIC = ['preferred_name', 'legal_name', 'email', 'phone']
VERIFY = BASIC + ['address', 'date_of_birth', 'ssn_last4']
LABELS = {'preferred_name':'preferred name', 'legal_name':'legal name', 'email':'email',
          'phone':'phone number', 'address':'address', 'date_of_birth':'date of birth',
          'ssn_last4':'last four of my social'}


def behavior():
    return json.loads((ROOT / 'config/behavior.json').read_text())


def load():
    path = DATA / 'profile.json'
    return json.loads(path.read_text()) if path.exists() else {'schemaVersion':1, 'identity':{}, 'sources':{}}


def save_identity(source):
    data=json.loads(Path(source).read_text())
    changes=data.get('identity',data)
    if not isinstance(changes,dict) or any(key not in VERIFY for key in changes):
        raise ValueError('Use supported identity field names.')
    if changes.get('ssn_last4') is not None and not re.fullmatch(r'\d{4}',str(changes['ssn_last4'])):
        raise ValueError('Last four must contain exactly four digits.')
    if changes.get('phone') and not re.fullmatch(r'\+[1-9]\d{6,14}',changes['phone']):
        raise ValueError('Use the full phone number beginning with +.')
    data=load();data.setdefault('identity',{}).update(changes)
    data['updatedAt']=datetime.datetime.now(datetime.timezone.utc).isoformat()
    for key in changes:data.setdefault('sources',{})[key]='Imported from file: '+str(Path(source).resolve())
    DATA.mkdir(parents=True,exist_ok=True,mode=0o700)
    path=DATA/'profile.json'
    fd=os.open(str(path)+'.tmp',os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
    with os.fdopen(fd,'w') as stream:json.dump(data,stream,indent=2)
    os.replace(str(path)+'.tmp',path)
    return {'updatedFields':list(changes)}


def account(key):
    if not re.fullmatch(r'[a-z0-9][a-z0-9_-]{0,63}', key):
        raise ValueError('Use an account key made of lowercase letters, numbers, hyphens, or underscores.')
    path = DATA / 'accounts' / (key + '.json')
    if not path.exists():
        raise ValueError('Account details are missing: ' + key)
    return json.loads(path.read_text())


def accounts():
    found = []
    for path in sorted((DATA / 'accounts').glob('*.json')):
        item = json.loads(path.read_text())
        found.append({'key':path.stem, 'company':item.get('company'), 'fields':list(item.get('facts', {}))})
    return found


def save_account(key, source):
    if not re.fullmatch(r'[a-z0-9][a-z0-9_-]{0,63}', key):
        raise ValueError('Invalid account key')
    data = json.loads(Path(source).read_text())
    if not data.get('company') or not isinstance(data.get('facts', {}), dict):
        raise ValueError('An account file needs company and a facts object.')
    folder = DATA / 'accounts'; folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    path = folder / (key + '.json')
    fd = os.open(str(path)+'.tmp', os.O_WRONLY|os.O_CREAT|os.O_TRUNC, 0o600)
    with os.fdopen(fd,'w') as stream:
        json.dump(data,stream,indent=2)
    os.replace(str(path)+'.tmp',path)
    return {'account':key,'company':data['company'],'fields':list(data.get('facts',{}))}


def context(card=None, verification=False):
    card = card or {}; profile = load(); identity = copy.deepcopy(profile.get('identity', {}))
    company = account(card['account']) if card.get('account') else None
    if company:
        identity.update(company.get('identity', {}))
    identity.update(card.get('identity', {}))
    fields = card.get('profile_fields') or (VERIFY if verification or company else BASIC)
    if isinstance(fields,str): fields=[part.strip() for part in fields.split(',') if part.strip()]
    selected = {key:identity[key] for key in fields if identity.get(key) not in (None,'')}
    sources={key:profile.get('sources',{}).get(key,'Saved personal profile') for key in selected}
    if company:
        for key in company.get('identity',{}):
            if key in selected:sources[key]='Account '+card['account']+' identity override'
    for key in card.get('identity',{}):
        if key in selected:sources[key]='Current goal card identity override'
    learned=requirements(card.get('account') or re.sub(r'[^a-z0-9]+','-',str(card.get('who') or '').lower()).strip('-')[:64])
    return {'identity':selected,'sources':sources,'learnedRequirements':learned,'missingFields':[key for key in fields if identity.get(key) in (None,'')],
            'account':company,'behavior':behavior()}


def as_fact(key, value):
    if isinstance(value,dict):
        value=', '.join(str(value[k]) for k in ['street','city','state','postal_code','country'] if value.get(k))
    elif isinstance(value,list):value='; '.join(map(str,value))
    return LABELS.get(key,key.replace('_',' '))+': '+str(value)


def enrich(card, verification=True):
    result=copy.deepcopy(card);ctx=context(result,verification)
    facts=list(result.get('facts',[]))
    facts.extend(as_fact(k,v) for k,v in ctx['identity'].items())
    if ctx['account']:
        facts.extend(as_fact(k,v) for k,v in ctx['account'].get('facts',{}).items())
    result['facts']=list(dict.fromkeys(facts))
    if ctx['account']:
        result.setdefault('who',ctx['account'].get('company'))
        contact=ctx['account'].get('contact',{})
        if contact.get('phone'):result.setdefault('number',contact['phone'])
        if contact.get('support_url'):result.setdefault('url',contact['support_url'])
    return result,ctx


def handoff():
    rules=behavior();phone=load().get('identity',{}).get('phone')
    if rules['phoneStage']=='automated-systems':
        if rules.get('humanHandoff')!='transfer':raise ValueError('Set the configured human handoff before using the phone stage.')
        if not phone:raise ValueError('The shared profile needs the handoff phone number.')
        text=('Current phone stage: handle automated menus and AI agents. Determine from the greeting whether the other side is automated or a live person. '
              'If unclear, ask one brief question. When a live person answers, say exactly: "'+rules['handoffLine']+'" '
              'Then use the configured transfer action immediately so George takes over. '
              'This handoff takes precedence over continuing the questions or errand with the person.')
        return {'transfer_phone_number':conference_number() or phone},text
    return {},'Phone conversations may continue with automated systems and people.'


if __name__=='__main__':
    try:
        payload=json.load(sys.stdin)
        print(json.dumps(context(payload.get('card'),payload.get('verification',False)),ensure_ascii=False))
    except Exception as error:
        print(json.dumps({'error':str(error)}));sys.exit(1)
