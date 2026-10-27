#!/usr/bin/env python3
"""Apply or read back the versioned settings for George's personal Vapi assistant."""
import argparse
import copy
import json
from pathlib import Path
import urllib.request

REPO = Path(__file__).resolve().parents[1]
CONFIG = json.loads((REPO / 'config/personal-assistant.json').read_text())
PERSONAL_ID = '4346abeb-ee9e-4b7e-a8fa-57f20a32c325'
PERSONAL_NUMBER_ID = '4077477e-40b4-4974-8e43-ad5ff10511fc'
assert CONFIG['assistantId'] == PERSONAL_ID
assert CONFIG['phoneNumberId'] == PERSONAL_NUMBER_ID


def api(path, method='GET', body=None):
    lines = Path('/root/.gmail/aicalls.env').read_text().splitlines()
    key = next(line.split('=', 1)[1].strip().strip('"').strip("'") for line in lines if line.startswith('VAPI_KEY='))
    req = urllib.request.Request('https://api.vapi.ai/' + path, method=method,
        headers={'Authorization': 'Bearer ' + key, 'Content-Type': 'application/json', 'User-Agent': 'curl/8'},
        data=json.dumps(body).encode() if body is not None else None)
    with urllib.request.urlopen(req, timeout=30) as response:
        return json.load(response)


def desired(live):
    model = copy.deepcopy(live['model'])
    model.update(CONFIG['model'])
    model['messages'] = [{'role': 'system', 'content': (REPO / 'prompts/voice.txt').read_text().strip()}]
    key = Path('/root/.vapi/bridge/line.key').read_text().strip().split('=', 1)[1]
    tools = []
    for source in CONFIG['tools']:
        tool = copy.deepcopy(source)
        timeout = tool.pop('serverTimeoutSeconds', 15)
        tool['server'] = {'url': 'https://' + CONFIG['tunnelDomain'] + '/tools',
                          'timeoutSeconds': timeout, 'headers': {'X-Line-Key': key}}
        tools.append(tool)
    model['tools'] = tools
    return {**CONFIG['settings'], 'model': model}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    phone = api('phone-number/' + PERSONAL_NUMBER_ID)
    if phone.get('assistantId') != PERSONAL_ID:
        raise RuntimeError('The personal number currently points to another assistant.')
    live = api('assistant/' + PERSONAL_ID)
    patch = desired(live)
    if args.apply:
        api('assistant/' + PERSONAL_ID, 'PATCH', patch)
        live = api('assistant/' + PERSONAL_ID)
    differences = [key for key, value in patch.items() if live.get(key) != value]
    print(json.dumps({'assistantId': PERSONAL_ID, 'matches': not differences,
                      'differentFields': differences, 'version': live.get('latestVersion')}, indent=2))
    if differences:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
