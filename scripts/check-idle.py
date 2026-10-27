#!/usr/bin/env python3
"""Read active personal calls before replacing the personal bridge."""
import json
from pathlib import Path
import urllib.request
import urllib.parse

lines = Path('/root/.gmail/aicalls.env').read_text().splitlines()
key = next(line.split('=', 1)[1].strip().strip('"').strip("'") for line in lines if line.startswith('VAPI_KEY='))
query = urllib.parse.urlencode({'assistantId': '4346abeb-ee9e-4b7e-a8fa-57f20a32c325', 'limit': 20})
req = urllib.request.Request('https://api.vapi.ai/call?' + query,
    headers={'Authorization': 'Bearer ' + key, 'User-Agent': 'curl/8'})
with urllib.request.urlopen(req, timeout=20) as response:
    calls = json.load(response)
active = [call for call in calls if call.get('status') in ['queued', 'ringing', 'in-progress', 'forwarding']]
if active:
    raise SystemExit('A personal phone call is active. Finish it before replacing the bridge.')
print('Personal line is idle.')
