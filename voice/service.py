#!/usr/bin/env python3
"""Manage the personal bridge process, including a child left behind by a PRoot restart."""
import json
import os
from pathlib import Path
import signal
import sys
import time
import urllib.request

BRIDGE = Path('/root/.vapi/bridge')
SOCKET = '/data/data/com.termux/files/usr/var/run/tmux-10435/vapi-line'


def status():
    key = (BRIDGE / 'line.key').read_text().strip().split('=', 1)[1]
    req = urllib.request.Request('http://127.0.0.1:8790/status', headers={'X-Line-Key': key})
    with urllib.request.urlopen(req, timeout=3) as response:
        return json.load(response)


def owned_processes():
    found = []
    for proc in Path('/proc').iterdir():
        if not proc.name.isdigit():
            continue
        try:
            args = proc.joinpath('cmdline').read_bytes().split(b'\0')
            if len(args) < 2 or args[0].split(b'/')[-1] != b'node' or args[1].split(b'/')[-1] != b'server_tmux.js':
                continue
            env = dict(item.split(b'=', 1) for item in proc.joinpath('environ').read_bytes().split(b'\0') if b'=' in item)
            if env.get(b'PERSONAL_ASSISTANT_BRIDGE') == b'1' or env.get(b'TMUX', b'').startswith(SOCKET.encode() + b','):
                found.append(int(proc.name))
        except (FileNotFoundError, PermissionError, ProcessLookupError):
            continue
    return found


def stop():
    try:
        live = status()
        if live.get('busy') or live.get('queued'):
            raise RuntimeError('The personal brain has work in progress. Finish that work before restarting.')
    except (OSError, ValueError):
        pass
    pids = owned_processes()
    for pid in pids:
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    end = time.monotonic() + 6
    while time.monotonic() < end:
        if not set(pids).intersection(owned_processes()):
            return
        time.sleep(0.1)
    raise RuntimeError('The old bridge process is still running.')


if __name__ == '__main__':
    try:
        command = sys.argv[1] if len(sys.argv) > 1 else 'status'
        if command == 'stop':
            stop()
        elif command == 'healthy':
            live = status()
            expected = (BRIDGE / 'REVISION').read_text().strip()
            if live.get('revision') != expected or not owned_processes():
                sys.exit(1)
        else:
            print(json.dumps(status(), indent=2))
    except Exception as error:
        print(str(error), file=sys.stderr)
        sys.exit(1)
