#!/usr/bin/env python3
"""Serve the original Majestic George model as Vapi mono PCM speech."""
import argparse
import hashlib
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import os
from pathlib import Path
import sys
import threading
import time

import numpy as np
import onnxruntime as ort
from piper import PiperVoice, SynthesisConfig
from piper.voice import PiperConfig

ASSETS = Path('/root/.local/share/phone-errands-voices')
MODEL = ASSETS / 'models/en_US-george-medium.onnx'
sys.path.insert(0, '/root/.local/share/phone-errands')
from speech_text import prepare_for_local

options = ort.SessionOptions()
options.intra_op_num_threads = 2
options.inter_op_num_threads = 1
voice = PiperVoice(
    config=PiperConfig.from_dict(json.loads(Path(str(MODEL) + '.json').read_text())),
    session=ort.InferenceSession(str(MODEL), sess_options=options,
                               providers=['CPUExecutionProvider']))
model_hash = hashlib.sha256(MODEL.read_bytes()).hexdigest()
lock = threading.Lock()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        if self.path != '/health':
            self.send_error(404)
            return
        data = json.dumps({'voice': 'majestic-george', 'ready': True,
                           'modelSha256': model_hash, 'voiceSettings': 'original'}).encode()
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        if self.path != '/tts':
            self.send_error(404)
            return
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length <= 65536:
                raise ValueError('Invalid request length')
            message = json.loads(self.rfile.read(length)).get('message', {})
            text = message.get('text', '')
            rate = message.get('sampleRate', 24000)
            if message.get('type') != 'voice-request':
                raise ValueError('Expected voice-request')
            if not isinstance(text, str) or not text.strip() or len(text) > 5000:
                raise ValueError('Invalid speech text')
            if rate not in [8000, 16000, 22050, 24000, 44100, 48000]:
                raise ValueError('Unsupported sample rate')
            text = prepare_for_local(text)
        except (ValueError, TypeError, AttributeError):
            self.send_error(400, 'Invalid speech request')
            return
        start = time.monotonic()
        size = 0
        first = None
        sent = False
        try:
            with lock:
                for chunk in voice.synthesize(text, SynthesisConfig()):
                    samples = np.frombuffer(chunk.audio_int16_bytes, dtype='<i2')
                    if voice.config.sample_rate != rate:
                        positions = np.linspace(0, max(0, len(samples)-1),
                                                int(len(samples)*rate/voice.config.sample_rate))
                        samples = np.interp(positions, np.arange(len(samples)), samples).astype('<i2')
                    if not sent:
                        self.send_response(200)
                        self.send_header('Content-Type', 'application/octet-stream')
                        self.send_header('Cache-Control', 'no-store')
                        self.send_header('Connection', 'close')
                        self.end_headers()
                        sent = True
                        first = time.monotonic()-start
                    data = samples.tobytes()
                    self.wfile.write(data)
                    self.wfile.flush()
                    size += len(data)
            if not sent:
                self.send_error(502, 'No speech generated')
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception as error:
            print(json.dumps({'event': 'majestic-error', 'error': type(error).__name__}), flush=True)
            if not sent:
                self.send_error(502, 'Speech generation failed')
        finally:
            self.close_connection = True
            print(json.dumps({'event': 'majestic-speech', 'textCharacters': len(text),
                              'sampleRate': rate, 'firstAudioSeconds': first,
                              'audioSeconds': size/(rate*2),
                              'elapsedSeconds': time.monotonic()-start}), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8793)
    args = parser.parse_args()
    # The bridge owns this helper. Stop after its parent goes away.
    parent = os.getppid()
    def watch_parent():
        while True:
            time.sleep(2)
            if os.getppid() != parent:
                os._exit(0)
    threading.Thread(target=watch_parent, daemon=True).start()
    print(json.dumps({'event': 'majestic-ready', 'modelSha256': model_hash}), flush=True)
    ThreadingHTTPServer(('127.0.0.1', args.port), Handler).serve_forever()
