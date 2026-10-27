#!/usr/bin/env python3
"""Configure one dedicated Twilio number for the personal assistant's shared calls."""
import argparse
import base64
import json
import os
from pathlib import Path
import sys
import urllib.parse
import urllib.request

CONFIG=Path('/root/.twilio/voice-api.json')
LABEL='George personal call room'


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--credentials',type=Path,default=CONFIG,help='Private JSON with accountSid and authToken')
    parser.add_argument('--number',help='Dedicated owned number, in +1 format')
    parser.add_argument('--purchase-number',help='Exact available number whose purchase George approved')
    parser.add_argument('--apply',action='store_true')
    parser.add_argument('--enable',action='store_true',help='Enable the configured room for managed calls')
    args=parser.parse_args()
    credentials=json.loads(args.credentials.read_text())
    sid=credentials['accountSid'];token=credentials['authToken']
    domain=Path('/root/.vapi/bridge/ngrok_domain.txt').read_text().strip()
    endpoint='https://'+domain+'/twilio/entry'
    auth=base64.b64encode((sid+':'+token).encode()).decode()

    def api(method,path,data=None):
        request=urllib.request.Request('https://api.twilio.com/2010-04-01/Accounts/'+sid+'/'+path,method=method,
            headers={'Authorization':'Basic '+auth,'Content-Type':'application/x-www-form-urlencoded'},
            data=urllib.parse.urlencode(data).encode() if data else None)
        with urllib.request.urlopen(request,timeout=20) as response:return json.load(response)

    numbers=api('GET','IncomingPhoneNumbers.json?PageSize=1000')['incoming_phone_numbers']
    if not args.number and not args.purchase_number:
        print(json.dumps({'ownedNumbers':[{'number':n['phone_number'],'label':n['friendly_name'],'dedicated':n['friendly_name']==LABEL} for n in numbers],
                          'enabled':bool(credentials.get('enabled'))},indent=2));return
    number=args.number or args.purchase_number
    found=next((n for n in numbers if n['phone_number']==number),None)
    if found and found['friendly_name']!=LABEL:
        raise ValueError('That number belongs to another setup. Select the dedicated personal call-room number.')
    if not args.apply:
        print(json.dumps({'number':number,'action':'configure' if found else 'purchase','webhook':endpoint,'enable':args.enable,'requiresPurchaseApproval':not bool(found)},indent=2));return
    if not found:
        if not args.purchase_number:raise ValueError('This account does not own that number.')
        found=api('POST','IncomingPhoneNumbers.json',{'PhoneNumber':number,'FriendlyName':LABEL,'VoiceUrl':endpoint,'VoiceMethod':'POST'})
    else:
        found=api('POST','IncomingPhoneNumbers/'+found['sid']+'.json',{'VoiceUrl':endpoint,'VoiceMethod':'POST'})
    if found.get('voice_url')!=endpoint:raise RuntimeError('Twilio did not return the requested voice webhook.')
    saved={'accountSid':sid,'authToken':token,'conferenceNumber':number,'phoneNumberSid':found['sid'],'enabled':args.enable}
    CONFIG.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    fd=os.open(str(CONFIG)+'.tmp',os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
    with os.fdopen(fd,'w') as stream:json.dump(saved,stream,indent=2)
    os.replace(str(CONFIG)+'.tmp',CONFIG)
    print(json.dumps({'number':number,'webhook':endpoint,'enabled':args.enable,'saved':str(CONFIG)},indent=2))


if __name__=='__main__':
    try:main()
    except Exception as error:
        print(str(error),file=sys.stderr);sys.exit(1)
