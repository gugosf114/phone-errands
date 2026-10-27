#!/usr/bin/env python3
"""Confirm the installed revision is serving both the local and public personal line."""
import json
from pathlib import Path
import time
import urllib.request

bridge = Path('/root/.vapi/bridge')
expected = (bridge / 'REVISION').read_text().strip()
key = (bridge / 'line.key').read_text().strip().split('=', 1)[1]
domain = (bridge / 'ngrok_domain.txt').read_text().strip()
last_error = ''
for attempt in range(20):
    try:
        results = {}
        for label, url in [('local', 'http://127.0.0.1:8790/status'), ('public', 'https://' + domain + '/status')]:
            req = urllib.request.Request(url, headers={'X-Line-Key': key, 'User-Agent': 'curl/8'})
            with urllib.request.urlopen(req, timeout=4) as response:
                status = json.load(response)
            if status.get('revision') != expected or status.get('version') != 'personal-assistant-v1' or not status.get('brain'):
                raise RuntimeError(label + ' has not reached the installed revision with a live brain')
            results[label] = {'revision': status['revision'], 'brain': status['brain']}
        print(json.dumps({'verified': results}, indent=2))
        break
    except Exception as error:
        last_error = str(error)
        time.sleep(1)
else:
    raise SystemExit('Runtime verification failed: ' + last_error)
