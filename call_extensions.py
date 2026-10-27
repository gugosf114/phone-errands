"""Attach the configured private-question tools to an outgoing call."""
import json
import os
from pathlib import Path
from conference_client import conference_number,preflight


def extend_request(body,preview=False):
    if not preview:preflight()
    job_id=os.environ.get('ASSISTANT_JOB_ID')
    config_file=Path(__file__).resolve().parent/'config/bland-tools.json'
    if not job_id or not config_file.exists():return body
    config=json.loads(config_file.read_text());ids=[v for k,v in config.get('tools',{}).items() if v and (k!='handoff_to_george' or conference_number())]
    if not ids:return body
    result=dict(body);result['tools']=list(dict.fromkeys(body.get('tools',[])+ids))
    result['metadata']={**body.get('metadata',{}),'assistant_job_id':job_id}
    result['task']=body['task']+'\n\nPrivate questions: Your job ID is '+job_id+'. Use the supplied facts first. If a fact or decision is missing, use ask_george with this job_id and the question. It returns a question_id. Keep the conversation flowing and use get_george_answer with that question_id to read his answer. Use the actual answer when it arrives. If it expires, report what is still needed and follow only the authority already given for the errand.'
    if conference_number():result['task']+=' If George needs to take over a resumed conference call, use handoff_to_george. Follow its instruction about the configured transfer destination.'
    return result
