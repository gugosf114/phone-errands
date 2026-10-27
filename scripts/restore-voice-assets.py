#!/usr/bin/env python3
"""Restore the private voice asset archive and verify its saved hashes."""
import argparse
import hashlib
import json
from pathlib import Path
import tarfile

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('archive')
parser.add_argument('--destination', default='/root/.local/share/phone-errands-voices')
a = parser.parse_args()
target = Path(a.destination).resolve(); target.mkdir(parents=True, exist_ok=True)
with tarfile.open(a.archive, 'r:gz') as archive:
    for member in archive.getmembers():
        destination = (target / member.name).resolve()
        if not destination.is_relative_to(target) or member.issym() or member.islnk():
            raise ValueError('Unexpected asset path: ' + member.name)
    archive.extractall(target, filter='data')
manifest = json.loads((target / 'manifest.json').read_text())
for asset in manifest['assets']:
    path = target / asset['path']
    if hashlib.sha256(path.read_bytes()).hexdigest() != asset['sha256']:
        raise ValueError('Asset hash mismatch: ' + asset['path'])
reference = manifest['reference']
if hashlib.sha256((target / reference['path']).read_bytes()).hexdigest() != reference['sha256']:
    raise ValueError('Reference sample hash mismatch')
print(json.dumps({'restored': str(target), 'verifiedAssets': len(manifest['assets']) + 1}))
