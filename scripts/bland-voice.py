#!/usr/bin/env python3
"""Create an owned Bland voice or render a short sample with an existing voice ID."""
import argparse
import json
from pathlib import Path
import sys
import time
import urllib.request
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from speech_text import prepare

KEY_FILE = Path('/root/.bland/key')


def request(path, body, content_type):
    req = urllib.request.Request('https://api.bland.ai' + path, data=body,
        headers={'authorization': KEY_FILE.read_text().strip(), 'Content-Type': content_type, 'User-Agent': 'curl/8'})
    return urllib.request.urlopen(req, timeout=120)


def clone(name, audio, destination):
    # Resume by name after an interrupted response instead of creating another copy.
    req = urllib.request.Request('https://api.bland.ai/v1/voices', headers={'authorization': KEY_FILE.read_text().strip(), 'User-Agent': 'curl/8'})
    with urllib.request.urlopen(req, timeout=30) as response:
        voices = json.load(response).get('voices', [])
    for voice in voices:
        if voice.get('name') == name and voice.get('public') is False:
            result = {'name': name, 'voice_id': voice.get('voice_id') or voice.get('id'), 'existing': True}
            Path(destination).write_text(json.dumps(result, indent=2)); print(json.dumps(result)); return
    boundary = 'voice-import-' + uuid.uuid4().hex
    parts = []
    for key, value in {'name': name, 'gender': 'male', 'description': "George's own voice for his authorized phone errands", 'isBTTS_V3': 'true'}.items():
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{key}"\r\n\r\n{value}\r\n'.encode())
    parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="audio_samples"; filename="reference.wav"\r\nContent-Type: audio/wav\r\n\r\n'.encode() + Path(audio).read_bytes() + b'\r\n')
    parts.append(f'--{boundary}--\r\n'.encode())
    with request('/v1/voices/clone', b''.join(parts), 'multipart/form-data; boundary=' + boundary) as response:
        result = json.load(response)
    Path(destination).write_text(json.dumps(result, indent=2))
    print(json.dumps(result))


def speak(voice_id, text, destination):
    started = time.monotonic()
    text = prepare(text)
    body = {'voice': voice_id, 'text': text, 'audio': {'encoding': 'pcm_s16le', 'sample_rate': 48000, 'container': 'wav'}}
    with request('/v2/tts', json.dumps(body).encode(), 'application/json') as response:
        audio = response.read()
        report = {'voice_id': voice_id, 'spokenText': text, 'bytes': len(audio), 'seconds': time.monotonic()-started,
                  'model': response.headers.get('x-model'), 'cost': response.headers.get('x-cost')}
    Path(destination).parent.mkdir(parents=True, exist_ok=True)
    Path(destination).write_bytes(audio)
    Path(destination + '.json').write_text(json.dumps(report, indent=2))
    print(json.dumps(report))


parser = argparse.ArgumentParser(description=__doc__)
commands = parser.add_subparsers(dest='command', required=True)
c = commands.add_parser('clone'); c.add_argument('--name', required=True); c.add_argument('--audio', required=True); c.add_argument('--out', required=True)
s = commands.add_parser('speak'); s.add_argument('--voice', required=True); s.add_argument('--text', required=True); s.add_argument('--out', required=True)
a = parser.parse_args()
try:
    if a.command == 'clone': clone(a.name, a.audio, a.out)
    else: speak(a.voice, a.text, a.out)
except urllib.error.HTTPError as error:
    print(json.dumps({'http_status': error.code, 'response': error.read().decode()[:1500]}), file=sys.stderr)
    sys.exit(1)
