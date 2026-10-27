#!/usr/bin/env python3
"""Render Majestic George locally using the imported Piper model."""
import argparse
import json
import os
from pathlib import Path
import sys
import time
import wave
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from speech_text import prepare_for_local
import numpy as np
import onnxruntime as ort
from piper import PiperVoice, SynthesisConfig
from piper.voice import PiperConfig

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--text', required=True)
parser.add_argument('--out', required=True)
parser.add_argument('--assets', default='/root/.local/share/phone-errands-voices')
parser.add_argument('--sample-rate', type=int, default=24000)
args = parser.parse_args()
model = Path(args.assets) / 'models/en_US-george-medium.onnx'
options = ort.SessionOptions(); options.intra_op_num_threads = 2; options.inter_op_num_threads = 1
voice = PiperVoice(config=PiperConfig.from_dict(json.loads(Path(str(model)+'.json').read_text())),
    session=ort.InferenceSession(str(model), sess_options=options, providers=['CPUExecutionProvider']))
text = prepare_for_local(args.text)
start = time.monotonic(); first = None; audio = []
for chunk in voice.synthesize(text, SynthesisConfig()):
    if first is None:
        first = time.monotonic()-start
    raw = chunk.audio_int16_bytes
    samples = np.frombuffer(raw, dtype='<i2')
    if voice.config.sample_rate != args.sample_rate:
        positions = np.linspace(0, max(0,len(samples)-1), int(len(samples)*args.sample_rate/voice.config.sample_rate))
        samples = np.interp(positions, np.arange(len(samples)), samples).astype('<i2')
    audio.append(samples.tobytes())
path = Path(args.out); path.parent.mkdir(parents=True, exist_ok=True)
with wave.open(str(path), 'wb') as wav:
    wav.setparams((1,2,args.sample_rate,0,'NONE','not compressed')); wav.writeframes(b''.join(audio))
print(json.dumps({'voice':'majestic-george','spokenText':text,'firstAudioSeconds':first,'renderSeconds':time.monotonic()-start,'audioSeconds':sum(map(len,audio))/(args.sample_rate*2),'output':str(path)}))
