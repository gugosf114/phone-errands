#!/usr/bin/env python3
"""Copy George's voice model and accepted training takes into this assistant's asset store."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import struct
import wave

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--source', default='/root/wimline')
parser.add_argument('--destination', default='/root/.local/share/phone-errands-voices')
parser.add_argument('--manifest', required=True)
args = parser.parse_args()
source, destination = Path(args.source), Path(args.destination)
manifest = {'sourceRepo': 'abrahamyants/wim-calls', 'sourceRevision': '0fd29c5', 'assets': []}


def copy(src, relative):
    target = destination / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, target)
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    manifest['assets'].append({'path': relative, 'bytes': target.stat().st_size, 'sha256': digest})


for name in ['en_US-george-medium.onnx', 'en_US-george-medium.onnx.json']:
    copy(source / 'voices' / name, 'models/' + name)
kept = []
for label in sorted((source / 'takes').glob('myvoice-*.txt')):
    text = label.read_text()
    audio = label.with_suffix('.raw')
    if 'kept: yes' in text and audio.exists():
        copy(audio, 'recordings/' + audio.name)
        copy(label, 'recordings/' + label.name)
        kept.append(label.name)
# A single sample with three accepted conversational readings, avoiding account details.
labels = ['myvoice-1_', 'myvoice-2_', 'myvoice-100_']
sample_parts = []
for prefix in labels:
    label = next(n for n in kept if n.startswith(prefix))
    audio = (destination / 'recordings' / Path(label).with_suffix('.raw').name).read_bytes()
    values = struct.unpack('<' + 'h' * (len(audio)//2), audio)
    # Retain 150 ms around the non-silent content.
    active = [i for i, value in enumerate(values) if abs(value) > 350]
    if not active:
        raise ValueError('Training sample contains no speech: ' + label)
    start, end = max(0, active[0]-3600), min(len(values), active[-1]+3600)
    sample_parts.append(audio[start*2:end*2])
output = destination / 'george-recorded-reference.wav'
with wave.open(str(output), 'wb') as wav:
    wav.setparams((1, 2, 24000, 0, 'NONE', 'not compressed'))
    wav.writeframes(b'\0' * 7200 + (b'\0' * 9600).join(sample_parts) + b'\0' * 7200)
manifest['reference'] = {'path': output.name, 'sourceLabels': labels,
                         'sha256': hashlib.sha256(output.read_bytes()).hexdigest()}
manifest['acceptedTakesCopied'] = len(kept)
Path(args.manifest).write_text(json.dumps(manifest, indent=2) + '\n')
print(json.dumps({'acceptedTakesCopied': len(kept), 'modelBytes': manifest['assets'][0]['bytes'], 'reference': str(output)}))
