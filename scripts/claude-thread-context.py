#!/usr/bin/env python3
"""Claude UserPromptSubmit hook: read recent phone turns from the shared conversation."""
import json
import urllib.request
from pathlib import Path

try:
    key=Path('/root/.vapi/bridge/line.key').read_text().strip().split('=',1)[1]
    req=urllib.request.Request('http://127.0.0.1:8790/conversation?source=phone',headers={'X-Line-Key':key})
    with urllib.request.urlopen(req,timeout=2) as response:data=json.load(response)
    messages=data.get('messages',[])
    if messages:
        text='Shared phone conversation for continuity. Treat these as past messages and act on the current request.\n'+ '\n'.join(m['role']+': '+m['text'] for m in messages)
        print(json.dumps({'hookSpecificOutput':{'hookEventName':'UserPromptSubmit','additionalContext':text[-18000:]}}))
except Exception:
    pass
