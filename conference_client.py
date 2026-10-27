"""Use the optional conference route for handoff and return on managed phone jobs."""
import json,os,time
from pathlib import Path
from assistant_records import request,receipt

_ROOMS={}


def conference_number():
    path=Path('/root/.twilio/voice-api.json')
    if not os.environ.get('ASSISTANT_JOB_ID') or not path.exists():return None
    config=json.loads(path.read_text())
    return config.get('conferenceNumber') if config.get('enabled') else None


def preflight():
    if conference_number():
        state=request('GET','/conferences')
        if any(room['state'] not in ['ended','cancelled'] for room in state.get('rooms',[])):
            raise RuntimeError('The shared call room is already in use.')
        if not state.get('available'):raise RuntimeError('The conference account is not ready.')


def register(body,call_id,api):
    if not conference_number():return
    try:
        room=request('POST','/conferences/register',{'job_id':os.environ['ASSISTANT_JOB_ID'],'call_id':call_id,'request':body})
        _ROOMS[call_id]=room['id']
    except Exception as error:
        try:
            api('POST','/calls/'+call_id+'/stop',{})
            receipt({'channel':'phone','provider':'bland','externalId':call_id,'status':'stopped','reason':'Conference registration failed'})
        except Exception as stop_error:
            raise RuntimeError('Conference registration failed for call '+call_id+'. Stopping it also failed: '+str(stop_error)) from error
        raise RuntimeError('Call '+call_id+' stopped because its shared room could not be registered.') from error


def wait_result(call_id,legacy_wait,api):
    room_id=_ROOMS.get(call_id)
    if not room_id:return legacy_wait(call_id)
    finished_at=None
    while True:
        call=api('GET','/calls/'+call_id)
        room=request('GET','/conferences/'+room_id)
        if room['state'] in ['ended','cancelled']:
            parts=[];last=call;turns=[]
            for segment in room.get('segments',[]):
                detail=api('GET','/calls/'+segment['callId'])
                text=detail.get('concatenated_transcript') or ''
                if text:parts.append('Call segment '+segment['callId']+'\n'+text)
                turns.extend(detail.get('transcripts') or [])
                last=detail
            for summary in room.get('ownerSummaries',[]):parts.append('George’s handover summary: '+summary['text'])
            result={**call,'completed':True,'status':'completed','conference':room,'concatenated_transcript':'\n\n'.join(parts),'transcripts':turns,
                    'analysis_call_id':room['segments'][-1]['callId'],'summary':last.get('summary') or call.get('summary')}
            return result
        if room['state']=='awaiting-transfer' and call.get('completed') and not call.get('transferred_to'):
            request('POST','/conferences/cancel',{'room_id':room_id})
            return call
        if room['state']=='awaiting-transfer' and call.get('completed'):
            finished_at=finished_at or time.monotonic()
            if time.monotonic()-finished_at>45:
                request('POST','/conferences/cancel',{'room_id':room_id})
                return {**call,'conference':room,'handoffError':'The transferred call did not enter its shared room.'}
        expires=room.get('expiresAt')
        if expires:
            import datetime
            if time.time()>datetime.datetime.fromisoformat(expires.replace('Z','+00:00')).timestamp()+30:
                request('POST','/conferences/end',{'room_id':room_id})
        time.sleep(5)
