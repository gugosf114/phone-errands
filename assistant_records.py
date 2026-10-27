"""One local job ledger for voice requests, terminal requests, calls, and support chats."""
import json
import os
from pathlib import Path
import urllib.request
import uuid

BRIDGE_DIR = Path(os.environ.get('ASSISTANT_BRIDGE_DIR', '/root/.vapi/bridge'))
BRIDGE_URL = os.environ.get('ASSISTANT_BRIDGE_URL', 'http://127.0.0.1:8790').rstrip('/')
OUTBOX = Path(os.environ.get('ASSISTANT_OUTBOX', '/root/.local/state/phone-errands/receipt-outbox'))


def request(method, path, body=None):
    key = (BRIDGE_DIR / 'line.key').read_text().strip().split('=', 1)[1]
    req = urllib.request.Request(BRIDGE_URL + path, method=method,
        headers={'X-Line-Key': key, 'Content-Type': 'application/json'},
        data=json.dumps(body).encode() if body is not None else None)
    with urllib.request.urlopen(req, timeout=30 if path.startswith('/conferences/') else 10) as response:
        return json.load(response)


def read_card(path):
    text = Path(path).read_text()
    if text.lstrip().startswith('{'):
        card = json.loads(text)
    else:
        card = {'facts': [], 'limits': []}
        section = None
        for raw in text.splitlines():
            line = raw.strip()
            if not line:
                continue
            if line.startswith('- ') and section:
                card[section].append(line[2:])
            elif ':' in line:
                key, value = line.split(':', 1)
                key, value = key.strip().lower(), value.strip()
                if key in ('facts', 'limits'):
                    section = key
                    if value:
                        card[key].append(value)
                else:
                    section = None
                    card[key] = value
    if not isinstance(card, dict) or not card.get('goal'):
        raise ValueError('The card needs a goal.')
    return card


def receipt(data, job_id=None):
    envelope = {'receiptId': str(uuid.uuid4()),
                'jobId': job_id or os.environ.get('ASSISTANT_JOB_ID'), 'evidence': data}
    try:
        return request('POST', '/receipts', envelope)
    except Exception:
        OUTBOX.mkdir(parents=True, exist_ok=True, mode=0o700)
        path = OUTBOX / (envelope['receiptId'] + '.json')
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'w') as stream:
            json.dump(envelope, stream, indent=2)
        return {'savedLocally': str(path)}


def flush():
    sent = 0
    for path in sorted(OUTBOX.glob('*.json')):
        request('POST', '/receipts', json.loads(path.read_text()))
        path.unlink()
        sent += 1
    return sent
