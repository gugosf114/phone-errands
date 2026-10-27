"""Named voices shared by both outgoing calling commands."""
import json
import os
from pathlib import Path


def catalog():
    return json.loads((Path(__file__).resolve().parent / 'config/voices.json').read_text())


def resolve_call_voice(requested=None):
    data = catalog()
    name = requested or os.environ.get('ASSISTANT_CALL_VOICE') or data['defaultCallVoice']
    voice = data['voices'].get(name)
    if voice is None:
        return name
    if not voice.get('blandId'):
        raise ValueError('This voice needs its Bland voice ID before it can be used on an outgoing call: ' + name)
    return voice['blandId']
